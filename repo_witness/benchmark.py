from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .evidence import retrieve_evidence

PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "benchmarks" / "lexical_evidence" / "cases.json"
DEFAULT_REPOSITORY = PROJECT_ROOT / "benchmarks" / "lexical_evidence" / "repository"


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


def load_cases(dataset_path: Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Benchmark dataset must contain a 'cases' list")
    return cases


def _first_expected_rank(retrieved_paths: Sequence[str], expected_paths: set[str]) -> int | None:
    return next(
        (rank for rank, path in enumerate(retrieved_paths, start=1) if path in expected_paths),
        None,
    )


def run_benchmark(
    dataset_path: Path = DEFAULT_DATASET,
    repository_root: Path = DEFAULT_REPOSITORY,
) -> dict[str, Any]:
    case_results = []
    for case in load_cases(dataset_path):
        expected_paths = set(case["expected_paths"])
        excluded_source = case.get("excluded_source_path")
        excluded_paths = (excluded_source,) if excluded_source else ()
        evidence = retrieve_evidence(
            repository_root,
            case["claim"],
            excluded_paths=excluded_paths,
        )
        retrieved_paths = [snippet.path for snippet in evidence]
        case_results.append(
            {
                "id": case["id"],
                "claim": case["claim"],
                "expected_paths": sorted(expected_paths),
                "excluded_source_path": excluded_source,
                "first_expected_rank": _first_expected_rank(retrieved_paths, expected_paths),
                "retrieved_paths": retrieved_paths,
            }
        )

    metrics = calculate_metrics(result["first_expected_rank"] for result in case_results)
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
