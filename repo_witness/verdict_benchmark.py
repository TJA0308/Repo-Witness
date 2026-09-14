"""Verdict evaluation over labelled evidence.

The retrieval benchmark in ``repo_witness.benchmark`` measures whether the right
file was ranked highly. It contains no verdict labels and cannot say whether a
conclusion is correct. This benchmark answers the separate question: given
evidence, does the classifier reach the verdict a careful reviewer would reach?

Evidence here is stored inline in the dataset rather than retrieved from fixture
repositories. That is deliberate: it isolates verdict accuracy from retrieval
quality, so a change in ranking can never move these numbers.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .analyzer import demo_classify
from .benchmark import _rate, _require_string, _require_string_list, format_results
from .models import ClaimAudit, EvidenceSnippet, Verdict

PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "benchmarks" / "verdict_cases" / "cases.json"
REQUIRED_CASE_FIELDS = {
    "id",
    "claim",
    "evidence",
    "expected_verdict",
    "case_tags",
    "rationale",
}
REQUIRED_EVIDENCE_FIELDS = {"path", "start_line", "end_line", "excerpt"}
VERDICT_ORDER = [
    Verdict.VERIFIED,
    Verdict.PARTIALLY_VERIFIED,
    Verdict.CONTRADICTED,
    Verdict.INSUFFICIENT_EVIDENCE,
]

Classifier = Callable[[str, list[EvidenceSnippet]], ClaimAudit]


def _require_snippet(raw: Any, index: int, case_id: str) -> EvidenceSnippet:
    field = f"evidence[{index}]"
    if not isinstance(raw, dict):
        raise ValueError(f"Case {case_id!r} field {field!r} must be an object")
    missing = REQUIRED_EVIDENCE_FIELDS - raw.keys()
    unknown = raw.keys() - REQUIRED_EVIDENCE_FIELDS
    if missing:
        raise ValueError(
            f"Case {case_id!r} field {field!r} is missing fields: {sorted(missing)}"
        )
    if unknown:
        raise ValueError(
            f"Case {case_id!r} field {field!r} has unknown fields: {sorted(unknown)}"
        )
    path = _require_string(raw["path"], f"{field}.path", case_id)
    if path.startswith("/") or "\\" in path or ".." in path.split("/"):
        raise ValueError(f"Case {case_id!r} field {field!r} contains unsafe path {path!r}")
    _require_string(raw["excerpt"], f"{field}.excerpt", case_id)
    for bound in ("start_line", "end_line"):
        value = raw[bound]
        if type(value) is not int or value < 1:
            raise ValueError(
                f"Case {case_id!r} field {field!r} bound {bound!r} must be a positive integer"
            )
    if raw["end_line"] < raw["start_line"]:
        raise ValueError(f"Case {case_id!r} field {field!r} ends before it starts")
    return EvidenceSnippet(
        path=path,
        start_line=raw["start_line"],
        end_line=raw["end_line"],
        excerpt=raw["excerpt"],
    )


def load_verdict_cases(dataset_path: Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 2:
        raise ValueError("Verdict dataset must be an object with version 2")
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Verdict dataset must contain a 'cases' list")

    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_case in enumerate(cases):
        if not isinstance(raw_case, dict):
            raise ValueError(f"Verdict case at index {index} must be an object")
        missing = REQUIRED_CASE_FIELDS - raw_case.keys()
        unknown = raw_case.keys() - REQUIRED_CASE_FIELDS
        if missing:
            raise ValueError(f"Verdict case at index {index} is missing fields: {sorted(missing)}")
        if unknown:
            raise ValueError(f"Verdict case at index {index} has unknown fields: {sorted(unknown)}")

        case_id = _require_string(raw_case["id"], "id", f"index {index}")
        if case_id in seen_ids:
            raise ValueError(f"Duplicate verdict case id: {case_id!r}")
        seen_ids.add(case_id)

        claim = _require_string(raw_case["claim"], "claim", case_id)
        _require_string(raw_case["rationale"], "rationale", case_id)
        tags = _require_string_list(raw_case["case_tags"], "case_tags", case_id)
        if not tags:
            raise ValueError(f"Case {case_id!r} must have at least one case tag")

        expected = _require_string(raw_case["expected_verdict"], "expected_verdict", case_id)
        if expected not in Verdict.__members__:
            raise ValueError(f"Case {case_id!r} has unknown expected verdict {expected!r}")

        raw_evidence = raw_case["evidence"]
        if not isinstance(raw_evidence, list):
            raise ValueError(f"Case {case_id!r} field 'evidence' must be a list")
        evidence = [
            _require_snippet(item, position, case_id)
            for position, item in enumerate(raw_evidence)
        ]
        if expected == Verdict.VERIFIED.value and not evidence:
            raise ValueError(f"Case {case_id!r} cannot expect VERIFIED with no evidence")

        validated.append(
            {
                "id": case_id,
                "claim": claim,
                "evidence": evidence,
                "expected_verdict": Verdict(expected),
                "case_tags": tags,
                "rationale": raw_case["rationale"],
            }
        )
    return validated


def _confusion_matrix(case_results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    matrix = {
        expected.value: {predicted.value: 0 for predicted in VERDICT_ORDER}
        for expected in VERDICT_ORDER
    }
    for result in case_results:
        matrix[result["expected_verdict"].value][result["actual_verdict"].value] += 1
    return matrix


def _per_class_metrics(case_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for verdict in VERDICT_ORDER:
        labelled = [r for r in case_results if r["expected_verdict"] == verdict]
        predicted = [r for r in case_results if r["actual_verdict"] == verdict]
        correct = sum(r["expected_verdict"] == r["actual_verdict"] for r in labelled)
        metrics[verdict.value] = {
            "labelled_cases": len(labelled),
            "predicted_cases": len(predicted),
            "precision": _rate(correct, len(predicted)) if predicted else None,
            "recall": _rate(correct, len(labelled)) if labelled else None,
        }
    return metrics


def _per_tag_accuracy(case_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    tags = sorted({tag for result in case_results for tag in result["case_tags"]})
    summary: dict[str, dict[str, Any]] = {}
    for tag in tags:
        tagged = [r for r in case_results if tag in r["case_tags"]]
        correct = sum(r["expected_verdict"] == r["actual_verdict"] for r in tagged)
        summary[tag] = {
            "case_count": len(tagged),
            "accuracy": _rate(correct, len(tagged)) if tagged else None,
        }
    return summary


def run_verdict_benchmark(
    dataset_path: Path = DEFAULT_DATASET,
    classifier: Classifier | None = None,
) -> dict[str, Any]:
    """Evaluate a claim classifier against the labelled verdict cases.

    Passing no classifier evaluates the production deterministic classifier.
    A classifier is used exactly as given and never falls back to another.
    """
    classify = classifier if classifier is not None else demo_classify
    case_results: list[dict[str, Any]] = []
    for case in load_verdict_cases(dataset_path):
        audit = classify(case["claim"], list(case["evidence"]))
        case_results.append(
            {
                "id": case["id"],
                "claim": case["claim"],
                "case_tags": case["case_tags"],
                "rationale": case["rationale"],
                "expected_verdict": case["expected_verdict"],
                "actual_verdict": audit.verdict,
                "confidence": audit.confidence,
                "correct": case["expected_verdict"] == audit.verdict,
                "evidence_paths": [snippet.path for snippet in case["evidence"]],
                "evidence_categories": [snippet.relevance for snippet in audit.evidence],
            }
        )

    correct = sum(result["correct"] for result in case_results)
    not_verified = [
        result
        for result in case_results
        if result["expected_verdict"] != Verdict.VERIFIED
    ]
    false_verifications = [
        result for result in not_verified if result["actual_verdict"] == Verdict.VERIFIED
    ]
    metrics = {
        "total_cases": len(case_results),
        "correct_cases": correct,
        "overall_accuracy": _rate(correct, len(case_results)),
        "false_verification_rate": _rate(len(false_verifications), len(not_verified)),
        "false_verification_cases": sorted(result["id"] for result in false_verifications),
        "failed_cases": sorted(
            result["id"] for result in case_results if not result["correct"]
        ),
        "confusion_matrix": _confusion_matrix(case_results),
        "per_class": _per_class_metrics(case_results),
        "per_tag": _per_tag_accuracy(case_results),
        "denominators": {
            "labelled_cases": len(case_results),
            "cases_not_labelled_verified": len(not_verified),
        },
    }
    serializable = [
        {
            **result,
            "expected_verdict": result["expected_verdict"].value,
            "actual_verdict": result["actual_verdict"].value,
        }
        for result in case_results
    ]
    return {"metrics": metrics, "cases": serializable}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a repository claim classifier")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args(argv)
    print(format_results(run_verdict_benchmark(args.dataset)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
