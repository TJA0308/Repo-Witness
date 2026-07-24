from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .evidence import retrieve_evidence

PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "benchmarks" / "lexical_evidence" / "cases.json"
DEFAULT_REPOSITORY = PROJECT_ROOT / "benchmarks" / "lexical_evidence" / "repositories"
REQUIRED_CASE_FIELDS = {
    "id",
    "repository",
    "claim",
    "expected_paths",
    "excluded_source_paths",
    "case_tags",
    "supported",
}
OPTIONAL_CASE_FIELDS = {"hard_negative_paths", "required_evidence_groups"}
REPOSITORY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def calculate_metrics(ranks: Iterable[int | None]) -> dict[str, int | float]:
    values = list(ranks)
    count = len(values)

    def recall_at(k: int) -> float:
        if not count:
            return 0.0
        return sum(rank is not None and rank <= k for rank in values) / count

    return {
        "hit_rate_recall_at_1": recall_at(1),
        "recall_at_3": recall_at(3),
        "recall_at_5": recall_at(5),
        "mean_reciprocal_rank": (
            sum(1 / rank for rank in values if rank is not None) / count if count else 0.0
        ),
        "evaluated_cases": count,
    }


def _require_string(value: Any, field: str, case_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Case {case_id!r} field {field!r} must be a nonempty string")
    return value


def _require_string_list(value: Any, field: str, case_id: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"Case {case_id!r} field {field!r} must be a list of nonempty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"Case {case_id!r} field {field!r} contains duplicates")
    return value


def _safe_relative_path(value: str, field: str, case_id: str) -> PurePosixPath:
    raw_parts = value.split("/")
    path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (
        "\\" in value
        or path.is_absolute()
        or bool(windows_path.drive)
        or any(part in {"", ".", ".."} for part in raw_parts)
        or path.as_posix() != value
    ):
        raise ValueError(
            f"Case {case_id!r} field {field!r} contains unsafe path {value!r}"
        )
    return path


def _validate_existing_paths(
    paths: list[str],
    field: str,
    case_id: str,
    repository_root: Path,
) -> None:
    for value in paths:
        path = _safe_relative_path(value, field, case_id)
        if not (repository_root / Path(*path.parts)).is_file():
            raise ValueError(
                f"Case {case_id!r} field {field!r} references missing file {value!r}"
            )


def load_cases(
    dataset_path: Path = DEFAULT_DATASET,
    repository_root: Path = DEFAULT_REPOSITORY,
) -> list[dict[str, Any]]:
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 2:
        raise ValueError("Benchmark dataset must be an object with version 2")
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Benchmark dataset must contain a 'cases' list")

    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_case in enumerate(cases):
        if not isinstance(raw_case, dict):
            raise ValueError(f"Benchmark case at index {index} must be an object")
        missing = REQUIRED_CASE_FIELDS - raw_case.keys()
        unknown = raw_case.keys() - REQUIRED_CASE_FIELDS - OPTIONAL_CASE_FIELDS
        if missing:
            raise ValueError(f"Benchmark case at index {index} is missing fields: {sorted(missing)}")
        if unknown:
            raise ValueError(f"Benchmark case at index {index} has unknown fields: {sorted(unknown)}")

        case_id = _require_string(raw_case["id"], "id", f"index {index}")
        if case_id in seen_ids:
            raise ValueError(f"Duplicate benchmark case id: {case_id!r}")
        seen_ids.add(case_id)

        repository = _require_string(raw_case["repository"], "repository", case_id)
        if not REPOSITORY_ID.fullmatch(repository):
            raise ValueError(f"Case {case_id!r} has invalid repository identifier")
        case_repository = repository_root / repository
        if not case_repository.is_dir():
            raise ValueError(
                f"Case {case_id!r} references missing fixture repository {repository!r}"
            )

        claim = _require_string(raw_case["claim"], "claim", case_id)
        expected_paths = _require_string_list(
            raw_case["expected_paths"], "expected_paths", case_id
        )
        excluded_paths = _require_string_list(
            raw_case["excluded_source_paths"], "excluded_source_paths", case_id
        )
        tags = _require_string_list(raw_case["case_tags"], "case_tags", case_id)
        if not tags:
            raise ValueError(f"Case {case_id!r} must have at least one case tag")
        hard_negatives = _require_string_list(
            raw_case.get("hard_negative_paths", []), "hard_negative_paths", case_id
        )
        supported = raw_case["supported"]
        if type(supported) is not bool:
            raise ValueError(f"Case {case_id!r} field 'supported' must be a boolean")
        if supported and not expected_paths:
            raise ValueError(f"Supported case {case_id!r} must contain expected evidence")
        if not supported and expected_paths:
            raise ValueError(f"Unsupported case {case_id!r} cannot contain expected evidence")

        groups = raw_case.get("required_evidence_groups", [])
        if not isinstance(groups, list):
            raise ValueError(
                f"Case {case_id!r} field 'required_evidence_groups' must be a list"
            )
        validated_groups: list[list[str]] = []
        for group_index, group in enumerate(groups):
            group_paths = _require_string_list(
                group,
                f"required_evidence_groups[{group_index}]",
                case_id,
            )
            if not group_paths:
                raise ValueError(f"Case {case_id!r} contains an empty evidence group")
            if any(path not in expected_paths for path in group_paths):
                raise ValueError(
                    f"Case {case_id!r} evidence groups must contain only expected paths"
                )
            validated_groups.append(group_paths)
        if not supported and validated_groups:
            raise ValueError(f"Unsupported case {case_id!r} cannot require evidence groups")
        if validated_groups and len(validated_groups) < 2:
            raise ValueError(
                f"Distributed case {case_id!r} must contain at least two evidence groups"
            )
        grouped_paths = [path for group in validated_groups for path in group]
        if len(grouped_paths) != len(set(grouped_paths)):
            raise ValueError(
                f"Case {case_id!r} evidence groups must be path-disjoint"
            )
        if validated_groups and set(grouped_paths) != set(expected_paths):
            raise ValueError(
                f"Case {case_id!r} evidence groups must cover every expected path"
            )

        expected_set = set(expected_paths)
        excluded_set = set(excluded_paths)
        hard_negative_set = set(hard_negatives)
        if expected_set & excluded_set:
            raise ValueError(f"Case {case_id!r} cannot exclude expected evidence")
        if expected_set & hard_negative_set:
            raise ValueError(f"Case {case_id!r} cannot label expected evidence as hard negative")

        _validate_existing_paths(expected_paths, "expected_paths", case_id, case_repository)
        _validate_existing_paths(
            excluded_paths, "excluded_source_paths", case_id, case_repository
        )
        _validate_existing_paths(
            hard_negatives, "hard_negative_paths", case_id, case_repository
        )

        validated.append(
            {
                "id": case_id,
                "repository": repository,
                "claim": claim,
                "expected_paths": expected_paths,
                "excluded_source_paths": excluded_paths,
                "case_tags": tags,
                "supported": supported,
                "hard_negative_paths": hard_negatives,
                "required_evidence_groups": validated_groups,
            }
        )
    return validated


def _first_expected_rank(
    retrieved_paths: Sequence[str], expected_paths: set[str]
) -> int | None:
    return next(
        (
            rank
            for rank, path in enumerate(retrieved_paths, start=1)
            if path in expected_paths
        ),
        None,
    )


def _unique_paths(paths: Sequence[str]) -> list[str]:
    return [*dict.fromkeys(paths)]


def _relevant_rank(
    retrieved_paths: Sequence[str],
    expected_paths: set[str],
    required_groups: list[list[str]],
) -> int | None:
    if not required_groups:
        return _first_expected_rank(retrieved_paths, expected_paths)
    group_ranks = [
        _first_expected_rank(retrieved_paths, set(group))
        for group in required_groups
    ]
    if any(rank is None for rank in group_ranks):
        return None
    return max(rank for rank in group_ranks if rank is not None)


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _group_metrics(case_results: list[dict[str, Any]], k: int) -> tuple[float, float]:
    grouped = [result for result in case_results if result["required_evidence_groups"]]
    total_groups = sum(len(result["required_evidence_groups"]) for result in grouped)
    represented_groups = 0
    complete_cases = 0
    for result in grouped:
        top_paths = set(result["retrieved_paths"][:k])
        represented = [
            any(path in top_paths for path in group)
            for group in result["required_evidence_groups"]
        ]
        represented_groups += sum(represented)
        complete_cases += bool(represented) and all(represented)
    return _rate(represented_groups, total_groups), _rate(complete_cases, len(grouped))


def _per_category_metrics(case_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    categories: dict[str, dict[str, Any]] = {}
    tags = sorted({tag for result in case_results for tag in result["case_tags"]})
    for tag in tags:
        tagged = [result for result in case_results if tag in result["case_tags"]]
        recall_eligible = [result for result in tagged if result["supported"]]
        ranks = [result["evaluation_rank"] for result in recall_eligible]
        categories[tag] = {
            "case_count": len(tagged),
            "recall_eligible_cases": len(recall_eligible),
            "recall_at_3": (
                _rate(sum(rank is not None and rank <= 3 for rank in ranks), len(ranks))
                if ranks
                else None
            ),
            "mean_reciprocal_rank": (
                sum(1 / rank for rank in ranks if rank is not None) / len(ranks)
                if ranks
                else None
            ),
        }
    return categories


def run_benchmark(
    dataset_path: Path = DEFAULT_DATASET,
    repository_root: Path = DEFAULT_REPOSITORY,
) -> dict[str, Any]:
    case_results: list[dict[str, Any]] = []
    for case in load_cases(dataset_path, repository_root):
        expected_paths = set(case["expected_paths"])
        evidence = retrieve_evidence(
            repository_root / case["repository"],
            case["claim"],
            excluded_paths=case["excluded_source_paths"],
        )
        retrieved_paths = [snippet.path for snippet in evidence]
        unique_paths = _unique_paths(retrieved_paths)
        case_results.append(
            {
                **case,
                "first_expected_rank": _first_expected_rank(
                    retrieved_paths,
                    expected_paths,
                ),
                "first_expected_unique_file_rank": _first_expected_rank(
                    unique_paths,
                    expected_paths,
                ),
                "evaluation_rank": _relevant_rank(
                    retrieved_paths,
                    expected_paths,
                    case["required_evidence_groups"],
                ),
                "unique_file_evaluation_rank": _relevant_rank(
                    unique_paths,
                    expected_paths,
                    case["required_evidence_groups"],
                ),
                "retrieved_paths": retrieved_paths,
                "unique_retrieved_paths": unique_paths,
            }
        )

    supported = [result for result in case_results if result["supported"]]
    unsupported = [result for result in case_results if not result["supported"]]
    ranks = [result["evaluation_rank"] for result in supported]
    unique_ranks = [
        result["unique_file_evaluation_rank"] for result in supported
    ]
    metrics = calculate_metrics(ranks)
    metrics.update(
        {
            "total_cases": len(case_results),
            "supported_cases": len(supported),
            "unsupported_cases": len(unsupported),
            "unique_file_recall_at_1": _rate(
                sum(rank is not None and rank <= 1 for rank in unique_ranks),
                len(unique_ranks),
            ),
            "unique_file_recall_at_3": _rate(
                sum(rank is not None and rank <= 3 for rank in unique_ranks),
                len(unique_ranks),
            ),
            "unique_file_recall_at_5": _rate(
                sum(rank is not None and rank <= 5 for rank in unique_ranks),
                len(unique_ranks),
            ),
        }
    )

    total_snippets = sum(len(result["retrieved_paths"]) for result in case_results)
    repeated_file_positions = sum(
        len(result["retrieved_paths"]) - len(result["unique_retrieved_paths"])
        for result in case_results
    )
    metrics["repeated_file_occupancy_rate"] = _rate(
        repeated_file_positions,
        total_snippets,
    )

    grouped = [result for result in case_results if result["required_evidence_groups"]]
    hard_negative_cases = [
        result for result in case_results if result["hard_negative_paths"]
    ]
    for k in (1, 3, 5):
        coverage, complete = _group_metrics(case_results, k)
        metrics[f"evidence_group_coverage_at_{k}"] = coverage
        metrics[f"all_required_groups_success_at_{k}"] = complete
        metrics[f"hard_negative_retrieval_rate_at_{k}"] = _rate(
            sum(
                bool(set(result["retrieved_paths"][:k]) & set(result["hard_negative_paths"]))
                for result in hard_negative_cases
            ),
            len(hard_negative_cases),
        )
        metrics[f"unsupported_claim_retrieval_rate_at_{k}"] = _rate(
            sum(bool(result["retrieved_paths"][:k]) for result in unsupported),
            len(unsupported),
        )

    metrics["provenance_exclusion_violations"] = sum(
        path.casefold()
        in {
            excluded.replace("\\", "/").casefold()
            for excluded in result["excluded_source_paths"]
        }
        for result in case_results
        for path in result["retrieved_paths"]
    )
    metrics["per_category"] = _per_category_metrics(case_results)
    metrics["denominators"] = {
        "ordinary_recall_and_mrr_cases": len(supported),
        "unique_file_recall_cases": len(supported),
        "returned_positions_for_repeated_file_occupancy_rate": total_snippets,
        "required_evidence_groups": sum(
            len(result["required_evidence_groups"]) for result in grouped
        ),
        "distributed_evidence_cases": len(grouped),
        "hard_negative_cases": len(hard_negative_cases),
        "unsupported_cases": len(unsupported),
    }
    return {"metrics": metrics, "cases": case_results}


def format_results(results: dict[str, Any]) -> str:
    return json.dumps(results, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the lexical evidence retriever")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--repository", type=Path, default=DEFAULT_REPOSITORY)
    args = parser.parse_args(argv)
    print(format_results(run_benchmark(args.dataset, args.repository)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
