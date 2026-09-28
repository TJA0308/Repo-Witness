from __future__ import annotations
import re
from collections.abc import Collection, Mapping
from pathlib import Path
from .models import EvidenceSnippet

MAX_CANDIDATES = 6
MAX_EXCERPT_CHARS = 1200
PYTHON_VERSION_CONFIG_BONUS = 12
TEXT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".md", ".txt", ".sh", ".sql"}

def _terms(claim: str) -> list[str]:
    words = []
    for word in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_+.#-]{2,}", claim):
        normalized = word.lower().rstrip(".")
        # `3.9+` is prose for a minimum version; manifests write `>=3.9`.
        if re.fullmatch(r"\d+(?:\.\d+)+\+", normalized):
            normalized = normalized[:-1]
        words.append(normalized)
    return list(dict.fromkeys(word for word in words if len(word) >= 3 and word not in {"the", "and", "with", "uses", "has", "for"}))


def read_repository(root: Path) -> dict[str, list[str]]:
    """Read eligible text once per audit. No repository code is executed."""
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if path.name.casefold() in {"changelog.md", "history.md", "changes.md", "news.md"}:
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS and path.name.lower() not in {"dockerfile", "makefile"}:
            continue
        try:
            files[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
    return files

def retrieve_evidence(
    root: Path,
    claim: str,
    limit: int = MAX_CANDIDATES,
    excluded_paths: Collection[str] | None = None,
    *,
    repository_files: Mapping[str, list[str]] | None = None,
) -> list[EvidenceSnippet]:
    terms = _terms(claim)
    if not terms or limit <= 0:
        return []
    excluded = {path.replace("\\", "/").casefold() for path in (excluded_paths or ())}
    scored = []
    files = read_repository(root) if repository_files is None else repository_files
    for relative, lines in sorted(files.items()):
        if relative.casefold() in excluded:
            continue
        for idx, line in enumerate(lines):
            low = line.lower()
            hits = [t for t in terms if t in low]
            if hits:
                score = len(set(hits)) * 10 + sum(low.count(t) for t in set(hits))
                if (relative.casefold() == "pyproject.toml"
                        and re.search(r"\bpython\s+\d+\.\d+\+", claim, re.I)
                        and "requires-python" in low):
                    score += PYTHON_VERSION_CONFIG_BONUS
                scored.append((score, relative, idx + 1, [*dict.fromkeys(hits)]))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    results, seen = [], set()
    for score, rel, line, hits in scored:
        lines = files[rel]
        start, end = max(0, line - 3), min(len(lines), line + 2)
        # Merge overlapping windows, preserving their text (including conflicts).
        # Ten lines keeps one busy file from turning into an unbounded excerpt.
        overlapping = next((item for item in results if item.path == rel
                            and start < item.end_line and end >= item.start_line
                            and max(end, item.end_line) - min(start, item.start_line - 1) <= 10), None)
        if overlapping is not None:
            start = min(start, overlapping.start_line - 1)
            end = max(end, overlapping.end_line)
        elif (rel, start, end) in seen:
            continue
        seen.add((rel, start, end))
        excerpt = "\n".join(f"{n + 1}: {lines[n]}" for n in range(start, end))
        if len(excerpt) > MAX_EXCERPT_CHARS:
            excerpt = excerpt[:MAX_EXCERPT_CHARS - 20] + "\n[excerpt truncated]"
        if overlapping is not None:
            overlapping.start_line, overlapping.end_line, overlapping.excerpt = start + 1, end, excerpt
        else:
            results.append(EvidenceSnippet(path=rel, start_line=start + 1, end_line=end, excerpt=excerpt, relevance=f"Matched: {', '.join(hits)}; score {score}"))
        if len(results) >= limit:
            break
    return results
