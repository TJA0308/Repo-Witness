import json
from copy import deepcopy
from pathlib import Path

import pytest

import repo_witness.benchmark as benchmark
from repo_witness.benchmark import (
    DEFAULT_DATASET,
    DEFAULT_REPOSITORY,
    calculate_metrics,
    format_results,
    load_cases,
    run_benchmark,
)
from repo_witness.models import EvidenceSnippet


def _case(**updates):
    case = {
        "id": "case-1",
        "repository": "fixture",
        "claim": "alpha evidence",
        "expected_paths": ["expected.py"],
        "excluded_source_paths": [],
        "case_tags": ["exact-lexical"],
        "supported": True,
    }
    case.update(updates)
    return case


def _write_dataset(tmp_path, cases, files=None):
    repository_root = tmp_path / "repositories"
    repository = repository_root / "fixture"
    repository.mkdir(parents=True)
    paths = set(files or {"expected.py", "noise.py", "README.md"})
    for case in cases:
        for field in (
            "expected_paths",
            "excluded_source_paths",
            "hard_negative_paths",
        ):
            referenced_paths = case.get(field, [])
            if isinstance(referenced_paths, list):
                paths.update(referenced_paths)
    for relative in paths:
        if ".." in relative or "\\" in relative:
            continue
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("alpha evidence\n", encoding="utf-8")
    dataset = tmp_path / "cases.json"
    dataset.write_text(
        json.dumps({"version": 2, "cases": cases}),
        encoding="utf-8",
    )
    return dataset, repository_root


def _snippet(path, line=1):
    return EvidenceSnippet(
        path=path,
        start_line=line,
        end_line=line,
        excerpt=f"{line}: evidence",
        relevance="fixture",
    )


def _fake_retrieval(monkeypatch, paths_by_claim):
    def fake(root, claim, limit=6, excluded_paths=None):
        return [_snippet(path, index) for index, path in enumerate(paths_by_claim[claim], 1)]

    monkeypatch.setattr(benchmark, "retrieve_evidence", fake)


def test_metric_calculations():
    metrics = calculate_metrics([1, 2, 5, None])
    assert metrics == {
        "hit_rate_recall_at_1": 0.25,
        "recall_at_3": 0.5,
        "recall_at_5": 0.75,
        "mean_reciprocal_rank": pytest.approx((1 + 1 / 2 + 1 / 5) / 4),
        "evaluated_cases": 4,
    }
    assert calculate_metrics([])["evaluated_cases"] == 0


def test_checked_in_schema_and_fixture_repositories_are_valid():
    cases = load_cases()
    assert len(cases) == 40
    assert {case["repository"] for case in cases} == {
        "api_service",
        "worker_service",
        "data_pipeline",
        "release_tool",
    }
    assert len({case["id"] for case in cases}) == len(cases)
    event_schema = next(case for case in cases if case["id"] == "data-event-schema")
    assert "ineligible-extension" in event_schema["case_tags"]
    assert event_schema["expected_paths"] == ["schema/events.sql"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda case: case.pop("claim"), "missing fields"),
        (lambda case: case.update(supported="yes"), "must be a boolean"),
        (lambda case: case.update(expected_paths="expected.py"), "must be a list"),
        (lambda case: case.update(case_tags=[]), "at least one case tag"),
        (
            lambda case: case.update(supported=False),
            "Unsupported case",
        ),
        (
            lambda case: case.update(
                required_evidence_groups=[["expected.py"]]
            ),
            "at least two evidence groups",
        ),
    ],
)
def test_schema_validation_rejects_invalid_cases(tmp_path, mutate, message):
    case = _case()
    mutate(case)
    dataset, repository_root = _write_dataset(tmp_path, [case])
    with pytest.raises(ValueError, match=message):
        load_cases(dataset, repository_root)


def test_validation_rejects_unsafe_paths_and_duplicate_ids(tmp_path):
    unsafe = _case(expected_paths=["../escape.py"])
    dataset, repository_root = _write_dataset(tmp_path / "unsafe", [unsafe])
    with pytest.raises(ValueError, match="unsafe path"):
        load_cases(dataset, repository_root)

    first = _case()
    second = deepcopy(first)
    dataset, repository_root = _write_dataset(
        tmp_path / "duplicate",
        [first, second],
    )
    with pytest.raises(ValueError, match="Duplicate benchmark case id"):
        load_cases(dataset, repository_root)


def test_validation_rejects_missing_repositories_files_and_invalid_groups(tmp_path):
    missing_repository = _case(repository="missing")
    dataset, repository_root = _write_dataset(
        tmp_path / "repository",
        [missing_repository],
    )
    with pytest.raises(ValueError, match="missing fixture repository"):
        load_cases(dataset, repository_root)

    missing_file = _case(expected_paths=["missing.py"])
    dataset, repository_root = _write_dataset(
        tmp_path / "file",
        [missing_file],
        files={"noise.py"},
    )
    (repository_root / "fixture" / "missing.py").unlink()
    with pytest.raises(ValueError, match="missing file"):
        load_cases(dataset, repository_root)

    invalid_groups = _case(
        expected_paths=["first.py", "second.py"],
        required_evidence_groups=[["first.py"], ["not-expected.py"]],
    )
    dataset, repository_root = _write_dataset(
        tmp_path / "groups",
        [invalid_groups],
    )
    with pytest.raises(ValueError, match="only expected paths"):
        load_cases(dataset, repository_root)

    incomplete_groups = _case(
        expected_paths=["first.py", "second.py", "third.py"],
        required_evidence_groups=[["first.py"], ["second.py"]],
    )
    dataset, repository_root = _write_dataset(
        tmp_path / "incomplete-groups",
        [incomplete_groups],
    )
    with pytest.raises(ValueError, match="cover every expected path"):
        load_cases(dataset, repository_root)


def test_multiple_valid_paths_use_the_first_retrieved_alternative(tmp_path, monkeypatch):
    case = _case(expected_paths=["first.py", "second.py"])
    dataset, repository_root = _write_dataset(tmp_path, [case])
    _fake_retrieval(monkeypatch, {case["claim"]: ["noise.py", "second.py"]})

    result = run_benchmark(dataset, repository_root)

    assert result["cases"][0]["first_expected_rank"] == 2
    assert result["metrics"]["recall_at_3"] == 1.0


def test_distributed_evidence_requires_every_group(tmp_path, monkeypatch):
    case = _case(
        expected_paths=["source.py", "config.toml"],
        required_evidence_groups=[["source.py"], ["config.toml"]],
        case_tags=["distributed-evidence"],
    )
    dataset, repository_root = _write_dataset(tmp_path, [case])
    _fake_retrieval(
        monkeypatch,
        {case["claim"]: ["source.py", "noise.py", "config.toml"]},
    )

    result = run_benchmark(dataset, repository_root)
    metrics = result["metrics"]

    assert result["cases"][0]["first_expected_rank"] == 1
    assert result["cases"][0]["evaluation_rank"] == 3
    assert metrics["evidence_group_coverage_at_1"] == 0.5
    assert metrics["all_required_groups_success_at_1"] == 0.0
    assert metrics["evidence_group_coverage_at_3"] == 1.0
    assert metrics["all_required_groups_success_at_3"] == 1.0


def test_unique_file_ranking_and_repeated_file_occupancy(tmp_path, monkeypatch):
    case = _case(expected_paths=["expected.py"])
    dataset, repository_root = _write_dataset(tmp_path, [case])
    _fake_retrieval(
        monkeypatch,
        {case["claim"]: ["noise.py", "noise.py", "expected.py"]},
    )

    result = run_benchmark(dataset, repository_root)
    case_result = result["cases"][0]

    assert case_result["first_expected_rank"] == 3
    assert case_result["first_expected_unique_file_rank"] == 2
    assert result["metrics"]["repeated_file_occupancy_rate"] == pytest.approx(1 / 3)
    assert "duplicate_snippet_rate" not in result["metrics"]
    assert result["metrics"]["unique_file_recall_at_3"] == 1.0


def test_hard_negative_retrieval_rate_is_case_based(tmp_path, monkeypatch):
    case = _case(hard_negative_paths=["negative.md"])
    dataset, repository_root = _write_dataset(tmp_path, [case])
    _fake_retrieval(
        monkeypatch,
        {case["claim"]: ["negative.md", "expected.py"]},
    )

    metrics = run_benchmark(dataset, repository_root)["metrics"]

    assert metrics["hard_negative_retrieval_rate_at_1"] == 1.0
    assert metrics["hard_negative_retrieval_rate_at_3"] == 1.0
    assert metrics["denominators"]["hard_negative_cases"] == 1


def test_unsupported_claims_are_excluded_from_recall_and_mrr(tmp_path, monkeypatch):
    retrieved = _case(
        id="unsupported-retrieved",
        claim="unsupported one",
        expected_paths=[],
        supported=False,
        case_tags=["unsupported"],
    )
    empty = _case(
        id="unsupported-empty",
        claim="unsupported two",
        expected_paths=[],
        supported=False,
        case_tags=["unsupported"],
    )
    dataset, repository_root = _write_dataset(tmp_path, [retrieved, empty])
    _fake_retrieval(
        monkeypatch,
        {
            retrieved["claim"]: ["noise.py"],
            empty["claim"]: [],
        },
    )

    metrics = run_benchmark(dataset, repository_root)["metrics"]

    assert metrics["evaluated_cases"] == 0
    assert metrics["mean_reciprocal_rank"] == 0.0
    assert metrics["unsupported_claim_retrieval_rate_at_3"] == 0.5
    assert metrics["per_category"]["unsupported"]["recall_at_3"] is None


def test_per_category_metrics_use_only_supported_cases(tmp_path, monkeypatch):
    hit = _case(id="hit", claim="hit", case_tags=["category"])
    miss = _case(id="miss", claim="miss", case_tags=["category"])
    unsupported = _case(
        id="unsupported",
        claim="unsupported",
        expected_paths=[],
        supported=False,
        case_tags=["category", "unsupported"],
    )
    dataset, repository_root = _write_dataset(tmp_path, [hit, miss, unsupported])
    _fake_retrieval(
        monkeypatch,
        {
            hit["claim"]: ["expected.py"],
            miss["claim"]: [],
            unsupported["claim"]: ["noise.py"],
        },
    )

    category = run_benchmark(dataset, repository_root)["metrics"]["per_category"][
        "category"
    ]

    assert category == {
        "case_count": 3,
        "recall_eligible_cases": 2,
        "recall_at_3": 0.5,
        "mean_reciprocal_rank": 0.5,
    }


def test_provenance_exclusions_never_appear_in_results(tmp_path):
    case = _case(excluded_source_paths=["README.md"])
    dataset, repository_root = _write_dataset(tmp_path, [case])

    result = run_benchmark(dataset, repository_root)

    assert "README.md" not in result["cases"][0]["retrieved_paths"]
    assert result["metrics"]["provenance_exclusion_violations"] == 0


def test_benchmark_output_is_deterministic():
    assert format_results(run_benchmark()) == format_results(run_benchmark())


def test_checked_in_dataset_uses_only_relative_existing_paths():
    for case in load_cases(DEFAULT_DATASET, DEFAULT_REPOSITORY):
        repository = DEFAULT_REPOSITORY / case["repository"]
        paths = [
            *case["expected_paths"],
            *case["excluded_source_paths"],
            *case["hard_negative_paths"],
        ]
        assert all(not Path(path).is_absolute() for path in paths)
        assert all((repository / path).is_file() for path in paths)
