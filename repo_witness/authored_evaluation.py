"""Compare five authored labels with static audits of pinned repository archives.

Repository code is never executed. These selected cases are illustrative, not
an independent accuracy benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .analyzer import analyze_demo
from .ingest import cleanup_repository, extract_repository

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "benchmarks/real_repository_cases/cases.json"


def validate_excerpt(root: Path, citation: dict, *, numbered: bool = False) -> None:
    source = (root / citation["path"]).resolve()
    if root.resolve() not in source.parents:
        raise ValueError("Citation escapes the repository")
    lines = source.read_text(encoding="utf-8", errors="ignore").splitlines()
    start, end = citation["start_line"], citation["end_line"]
    if not 1 <= start <= end <= len(lines):
        raise ValueError(f"Invalid citation range: {citation['path']}")
    excerpt = "\n".join(f"{i + 1}: {lines[i]}" if numbered else lines[i]
                        for i in range(start - 1, end))
    if numbered and len(excerpt) > 1200:
        excerpt = excerpt[:1180] + "\n[excerpt truncated]"
    if citation["excerpt"] != excerpt:
        raise ValueError(f"Citation text differs from source: {citation['path']}")


def evaluate(archive_dir: Path, cases_path: Path = DEFAULT_CASES) -> dict:
    dataset = json.loads(cases_path.read_text(encoding="utf-8"))
    results = []
    for case in dataset["cases"]:
        name = case["repository"]
        data = (archive_dir / f"{name}.zip").read_bytes()
        if hashlib.sha256(data).hexdigest() != case["archive_sha256"]:
            raise ValueError(f"Archive hash differs from the reviewed snapshot: {name}")
        extracted = extract_repository(data)
        try:
            root = extracted / f"{name}-{case['commit']}"
            if not root.is_dir():
                raise ValueError(f"Pinned commit directory missing: {name}")
            validate_excerpt(root, case["review_source"])
            claim = case["claim"]
            audit = analyze_demo(root, [claim], {claim: case["excluded_path"]}).audits[0]
            for evidence in audit.evidence:
                validate_excerpt(root, evidence.model_dump(), numbered=True)
                if evidence.path == case["excluded_path"]:
                    raise ValueError("Originating document appeared in evidence")
            results.append({**case, "matches_label": audit.verdict.value == case["expected_verdict"],
                            "actual": audit.model_dump(mode="json")})
        finally:
            cleanup_repository(extracted)
    return {"label_status": dataset["label_status"],
            "method": "Deterministic static checks; README excluded; archive hashes and citation text validated",
            "interpretation": "Selected authored examples, not general accuracy or independent validation",
            "agreement": {"matching": sum(case["matches_label"] for case in results), "total": len(results)},
            "cases": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_dir", type=Path)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, help="Save UTF-8 JSON instead of printing it")
    args = parser.parse_args()
    result = json.dumps(evaluate(args.archive_dir, args.cases), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
