from pathlib import Path

import pytest

from repo_witness.benchmark import (
    DEFAULT_DATASET,
    DEFAULT_REPOSITORY,
    calculate_metrics,
    format_results,
    load_cases,
    run_benchmark,
)


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


def test_benchmark_output_is_deterministic():
    assert format_results(run_benchmark()) == format_results(run_benchmark())


def test_excluded_sources_never_count_as_evidence():
    cases = {case["id"]: case for case in load_cases()}
    results = {case["id"]: case for case in run_benchmark()["cases"]}
    for case_id, case in cases.items():
        excluded = case.get("excluded_source_path")
        if excluded:
            assert excluded not in results[case_id]["retrieved_paths"]


def test_missing_expected_evidence_is_handled_gracefully(tmp_path):
    dataset = tmp_path / "cases.json"
    dataset.write_text(
        '{"cases": [{"id": "missing", "claim": "Uses PostgreSQL", '
        '"expected_paths": ["src/database.py"]}]}',
        encoding="utf-8",
    )
    result = run_benchmark(dataset, DEFAULT_REPOSITORY)
    assert result["cases"][0]["first_expected_rank"] is None
    assert result["metrics"] == {
        "hit_rate_recall_at_1": 0.0,
        "recall_at_3": 0.0,
        "recall_at_5": 0.0,
        "mean_reciprocal_rank": 0.0,
        "evaluated_cases": 1,
    }


def test_checked_in_dataset_uses_only_relative_existing_paths():
    for case in load_cases(DEFAULT_DATASET):
        paths = [*case["expected_paths"]]
        if case.get("excluded_source_path"):
            paths.append(case["excluded_source_path"])
        assert all(not Path(path).is_absolute() for path in paths)
        assert all((DEFAULT_REPOSITORY / path).is_file() for path in paths)
