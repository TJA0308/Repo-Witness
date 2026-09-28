"""Reproduce the small public-repository smoke test from pinned ZIP archives.

This records outputs, not accuracy: these README claims have no independent
end-to-end verdict labels. The repository snapshots are never executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from .analyzer import analyze_demo
from .ingest import cleanup_repository, extract_repository
from .readme_claims import extract_candidate_claims

REPOSITORIES = {
    "click": ("pallets", "06b2a678741131fd577ce170e23e5ca0aeba0309"),
    "httpx": ("encode", "b5addb64f0161ff6bfe94c124ef76f6a1fba5254"),
    "requests": ("psf", "611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60"),
}


def evaluate(archive_dir: Path) -> dict:
    repositories = []
    for name, (owner, commit) in REPOSITORIES.items():
        data = (archive_dir / f"{name}.zip").read_bytes()
        extracted = extract_repository(data)
        try:
            root = extracted / f"{name}-{commit}"
            if not root.is_dir():
                raise ValueError(f"{name}.zip does not contain the pinned commit directory")
            readme = (root / "README.md").read_text(encoding="utf-8", errors="replace")
            claims = extract_candidate_claims(readme)
            audits = analyze_demo(root, claims, {claim: "README.md" for claim in claims}).audits
            cases = []
            for audit in audits:
                citations = []
                for evidence in audit.evidence:
                    source = root / evidence.path
                    if not source.is_file() or evidence.end_line > len(source.read_text(encoding="utf-8", errors="ignore").splitlines()):
                        raise ValueError(f"Invalid citation in {name}: {evidence.path}")
                    citations.append({"path": evidence.path, "start_line": evidence.start_line,
                                      "end_line": evidence.end_line})
                cases.append({"claim": audit.claim, "verdict": audit.verdict.value,
                              "citations": citations})
            repositories.append({
                "name": name, "commit": commit,
                "source": f"https://github.com/{owner}/{name}/tree/{commit}",
                "archive_sha256": hashlib.sha256(data).hexdigest(),
                "verdict_counts": dict(sorted(Counter(case["verdict"] for case in cases).items())),
                "cases": cases,
            })
        finally:
            cleanup_repository(extracted)
    return {"method": "README suggestions, originating README excluded, deterministic mode",
            "interpretation": "Output distribution only; no independent accuracy labels",
            "repositories": repositories}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_dir", type=Path, help="Directory containing click.zip, httpx.zip, requests.zip")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.archive_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
