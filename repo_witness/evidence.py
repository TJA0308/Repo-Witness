from __future__ import annotations
import re
from pathlib import Path
from .models import EvidenceSnippet

MAX_CANDIDATES = 6
MAX_EXCERPT_CHARS = 1200
TEXT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".md", ".txt", ".sh"}

def _terms(claim: str) -> list[str]:
    return [x.lower() for x in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_+.#-]{2,}", claim) if x.lower() not in {"the", "and", "with", "uses", "has", "for"}]

def retrieve_evidence(root: Path, claim: str, limit: int = MAX_CANDIDATES) -> list[EvidenceSnippet]:
    terms = _terms(claim)
    if not terms:
        return []
    scored = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or (path.suffix.lower() not in TEXT_EXTENSIONS and path.name.lower() not in {"dockerfile", "makefile"}):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines):
            low = line.lower()
            hits = [t for t in terms if t in low]
            if hits:
                score = len(set(hits)) * 10 + sum(low.count(t) for t in set(hits))
                scored.append((score, path.relative_to(root).as_posix(), idx + 1, [*dict.fromkeys(hits)]))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    results, seen = [], set()
    for score, rel, line, hits in scored:
        if (rel, line) in seen:
            continue
        seen.add((rel, line))
        lines = (root / rel).read_text(encoding="utf-8", errors="ignore").splitlines()
        start, end = max(0, line - 3), min(len(lines), line + 2)
        excerpt = "\n".join(f"{n + 1}: {lines[n]}" for n in range(start, end))[:MAX_EXCERPT_CHARS]
        results.append(EvidenceSnippet(path=rel, start_line=start + 1, end_line=end, excerpt=excerpt, relevance=f"Matched: {', '.join(hits)}; score {score}"))
        if len(results) >= limit:
            break
    return results

