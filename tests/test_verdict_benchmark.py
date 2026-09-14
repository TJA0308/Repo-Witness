import json

import pytest

from repo_witness.models import ClaimAudit, Verdict
from repo_witness.verdict_benchmark import (
    DEFAULT_DATASET,
    format_results,
    load_verdict_cases,
    run_verdict_benchmark,
)


def _case(**updates):
    case = {
        "id": "case-1",
        "claim": "Uses pytest for automated testing.",
        "evidence": [
            {
                "path": "tests/test_auth.py",
                "start_line": 1,
                "end_line": 1,
                "excerpt": "1: import pytest",
            }
        ],
        "expected_verdict": "VERIFIED",
        "case_tags": ["implementation-support"],
        "rationale": "A test module imports the claimed tool.",
    }
    case.update(updates)
    return case


def _write_dataset(tmp_path, cases):
    tmp_path.mkdir(parents=True, exist_ok=True)
    dataset = tmp_path / "cases.json"
    dataset.write_text(json.dumps({"version": 2, "cases": cases}), encoding="utf-8")
    return dataset


def _always(verdict):
    def classifier(claim, evidence):
        return ClaimAudit(
            claim=claim,
            verdict=verdict,
            confidence=0.5,
            evidence=list(evidence),
            reasoning="fixture",
            corrected_wording=claim,
        )

    return classifier


def test_checked_in_verdict_dataset_loads_and_covers_every_verdict():
    cases = load_verdict_cases()
    labelled = {case["expected_verdict"] for case in cases}
    assert len(cases) >= 20
    assert labelled == set(Verdict)
    assert len({case["id"] for case in cases}) == len(cases)


def test_every_checked_in_case_carries_a_rationale_and_at_least_one_tag():
    for case in load_verdict_cases():
        assert case["rationale"].strip()
        assert case["case_tags"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda case: case.pop("claim"), "missing fields"),
        (lambda case: case.update(surprise=1), "unknown fields"),
        (lambda case: case.update(expected_verdict="MAYBE"), "unknown expected verdict"),
        (lambda case: case.update(case_tags=[]), "at least one case tag"),
        (lambda case: case.update(evidence="nope"), "must be a list"),
        (lambda case: case.update(rationale="  "), "must be a nonempty string"),
        (lambda case: case.update(evidence=[], expected_verdict="VERIFIED"), "cannot expect VERIFIED"),
    ],
)
def test_schema_validation_rejects_invalid_verdict_cases(tmp_path, mutate, message):
    case = _case()
    mutate(case)
    dataset = _write_dataset(tmp_path, [case])
    with pytest.raises(ValueError, match=message):
        load_verdict_cases(dataset)


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ({"path": "../escape.py", "start_line": 1, "end_line": 1, "excerpt": "1: x"}, "unsafe path"),
        ({"path": "/abs.py", "start_line": 1, "end_line": 1, "excerpt": "1: x"}, "unsafe path"),
        ({"path": "a.py", "start_line": 0, "end_line": 1, "excerpt": "1: x"}, "positive integer"),
        ({"path": "a.py", "start_line": 5, "end_line": 2, "excerpt": "1: x"}, "ends before it starts"),
        ({"path": "a.py", "start_line": 1, "end_line": 1}, "missing fields"),
        ({"path": "a.py", "start_line": 1, "end_line": 1, "excerpt": "1: x", "extra": 1}, "unknown fields"),
    ],
)
def test_schema_validation_rejects_invalid_evidence_snippets(tmp_path, snippet, message):
    dataset = _write_dataset(tmp_path, [_case(evidence=[snippet])])
    with pytest.raises(ValueError, match=message):
        load_verdict_cases(dataset)


def test_validation_rejects_duplicate_case_ids_and_bad_envelopes(tmp_path):
    duplicate = _write_dataset(tmp_path / "duplicate", [_case(), _case()])
    with pytest.raises(ValueError, match="Duplicate verdict case id"):
        load_verdict_cases(duplicate)

    version = tmp_path / "version"
    version.mkdir()
    bad = version / "cases.json"
    bad.write_text(json.dumps({"version": 1, "cases": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="version 2"):
        load_verdict_cases(bad)


def test_confusion_matrix_contains_every_verdict_pair_even_with_zero_counts(tmp_path):
    dataset = _write_dataset(tmp_path, [_case()])
    matrix = run_verdict_benchmark(dataset)["metrics"]["confusion_matrix"]
    assert set(matrix) == {verdict.value for verdict in Verdict}
    assert all(set(row) == {verdict.value for verdict in Verdict} for row in matrix.values())
    assert matrix["VERIFIED"]["VERIFIED"] == 1
    assert matrix["CONTRADICTED"]["VERIFIED"] == 0


def test_per_class_precision_and_recall_are_none_when_the_class_never_appears(tmp_path):
    dataset = _write_dataset(tmp_path, [_case()])
    per_class = run_verdict_benchmark(dataset)["metrics"]["per_class"]
    assert per_class["VERIFIED"]["precision"] == 1.0
    assert per_class["CONTRADICTED"]["precision"] is None
    assert per_class["CONTRADICTED"]["recall"] is None


def test_false_verification_rate_counts_only_cases_not_labelled_verified(tmp_path):
    cases = [
        _case(id="a", expected_verdict="VERIFIED"),
        _case(id="b", expected_verdict="CONTRADICTED"),
        _case(id="c", expected_verdict="INSUFFICIENT_EVIDENCE"),
    ]
    dataset = _write_dataset(tmp_path, cases)
    metrics = run_verdict_benchmark(dataset, classifier=_always(Verdict.VERIFIED))["metrics"]
    assert metrics["denominators"]["cases_not_labelled_verified"] == 2
    assert metrics["false_verification_rate"] == 1.0
    assert metrics["false_verification_cases"] == ["b", "c"]
    assert metrics["overall_accuracy"] == pytest.approx(1 / 3)


def test_a_classifier_that_never_verifies_records_a_zero_false_verification_rate(tmp_path):
    dataset = _write_dataset(tmp_path, [_case(id="a", expected_verdict="CONTRADICTED")])
    metrics = run_verdict_benchmark(
        dataset, classifier=_always(Verdict.INSUFFICIENT_EVIDENCE)
    )["metrics"]
    assert metrics["false_verification_rate"] == 0.0
    assert metrics["overall_accuracy"] == 0.0


def test_per_tag_accuracy_is_reported_for_every_tag_present(tmp_path):
    cases = [
        _case(id="a", case_tags=["alpha"]),
        _case(id="b", case_tags=["alpha", "beta"], expected_verdict="CONTRADICTED"),
    ]
    dataset = _write_dataset(tmp_path, cases)
    per_tag = run_verdict_benchmark(dataset, classifier=_always(Verdict.VERIFIED))["metrics"]["per_tag"]
    assert per_tag["alpha"] == {"case_count": 2, "accuracy": 0.5}
    assert per_tag["beta"] == {"case_count": 1, "accuracy": 0.0}


def test_checked_in_dataset_keeps_the_false_verification_rate_low():
    metrics = run_verdict_benchmark()["metrics"]
    assert metrics["total_cases"] >= 20
    assert metrics["false_verification_rate"] <= 0.10
    assert metrics["overall_accuracy"] >= 0.80


def test_every_remaining_failure_is_a_case_tagged_as_known_hard():
    result = run_verdict_benchmark()
    failures = [case for case in result["cases"] if not case["correct"]]
    assert all("known-hard" in case["case_tags"] for case in failures)


def test_verdict_benchmark_output_is_deterministic_and_json_serializable():
    assert format_results(run_verdict_benchmark()) == format_results(run_verdict_benchmark())
    json.loads(format_results(run_verdict_benchmark()))


def test_checked_in_dataset_path_is_a_sibling_of_the_retrieval_benchmark():
    assert DEFAULT_DATASET.is_file()
    assert DEFAULT_DATASET.parent.name == "verdict_cases"
    assert "lexical_evidence" not in DEFAULT_DATASET.parts
