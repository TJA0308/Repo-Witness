from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .ingest import MAX_FILE_BYTES, should_ignore


README_NAMES = {"readme", "readme.md", "readme.rst", "readme.txt"}
IMPLEMENTATION_VERBS = re.compile(
    r"\b(uses?|supports?|includes?|provides?|implements?|deploys?|stores?|caches?|publishes?|validates?|runs?|integrates?|built with)\b",
    re.IGNORECASE,
)
TECHNICAL_SECTIONS = re.compile(r"\b(features?|architecture|technology|technologies|capabilities|what it does|design)\b", re.IGNORECASE)
EXCLUDED_SECTIONS = re.compile(r"\b(installation|install|setup|getting started|contributing|contribution|license|development)\b", re.IGNORECASE)
COMMAND_PREFIXES = re.compile(r"^(\$|>|pip\s+install|npm\s+(install|run)|yarn\s+|pnpm\s+|git\s+clone|docker\s+run|python\s+-m|streamlit\s+run)", re.IGNORECASE)
VAGUE_MARKETING = re.compile(r"\b(revolutionary|game[- ]changing|best[- ]in[- ]class|cutting[- ]edge|next[- ]generation|world[- ]class)\b", re.IGNORECASE)
MAX_CLAIMS = 10


@dataclass(frozen=True)
class ReadmeDocument:
    path: str
    text: str


def discover_readmes(root: Path) -> list[ReadmeDocument]:
    """Return safely extracted README documents, preferring repository-root files."""
    documents: list[ReadmeDocument] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink() or path.name.lower() not in README_NAMES:
            continue
        relative = path.relative_to(root).as_posix()
        relative_path = Path(relative)
        if should_ignore(relative_path):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw:
            continue
        text = raw.decode("utf-8", errors="ignore")
        documents.append(ReadmeDocument(path=relative, text=text))
    return sorted(documents, key=lambda item: (len(Path(item.path).parts) != 1, len(Path(item.path).parts), item.path.lower()))


def extract_candidate_claims(text: str, limit: int = MAX_CLAIMS) -> list[str]:
    """Extract conservative, explainable technical claim suggestions from README text."""
    if not text.strip():
        return []

    lines = text.splitlines()
    candidates: list[tuple[int, int, str]] = []
    in_fence = False
    current_section = ""

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence or not stripped:
            continue

        markdown_heading = re.match(r"^#{1,6}\s+(.+?)\s*#*$", stripped)
        if markdown_heading:
            current_section = markdown_heading.group(1).strip()
            continue
        if index + 1 < len(lines) and re.fullmatch(r"[=\-~^]{3,}", lines[index + 1].strip()):
            current_section = stripped
            continue
        if re.fullmatch(r"[=\-~^]{3,}", stripped):
            continue
        if EXCLUDED_SECTIONS.search(current_section):
            continue
        if _is_excluded_line(raw_line, stripped):
            continue

        bullet = bool(re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)", stripped))
        cleaned = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", stripped)
        cleaned = _clean_markdown(cleaned)
        for sentence in re.split(r"(?<=[.!?])\s+", cleaned):
            claim = sentence.strip(" \t-*_")
            if not _is_candidate(claim, bullet, current_section):
                continue
            score = 3 if IMPLEMENTATION_VERBS.search(claim) else 1
            score += 1 if bullet else 0
            score += 1 if TECHNICAL_SECTIONS.search(current_section) else 0
            candidates.append((score, index, claim))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    unique: list[str] = []
    for _, _, claim in candidates:
        if any(_near_duplicate(claim, existing) for existing in unique):
            continue
        unique.append(claim)
        if len(unique) >= limit:
            break
    return unique


def _is_excluded_line(raw_line: str, stripped: str) -> bool:
    lower = stripped.lower()
    if raw_line.startswith("    ") or COMMAND_PREFIXES.search(stripped):
        return True
    if "http://" in lower or "https://" in lower or "www." in lower:
        return True
    if "![" in stripped or "[![" in stripped or "<img" in lower or "shields.io" in lower:
        return True
    if "|" in stripped or stripped.startswith(("<!--", ":::")):
        return True
    return False


def _clean_markdown(value: str) -> str:
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[`*_~]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _is_candidate(claim: str, bullet: bool, section: str) -> bool:
    if len(claim) < 24 or len(claim) > 220:
        return False
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+#.-]*", claim)
    if len(words) < 4 or len(words) > 36:
        return False
    if VAGUE_MARKETING.search(claim):
        return False
    has_implementation_verb = bool(IMPLEMENTATION_VERBS.search(claim))
    in_technical_section = bool(TECHNICAL_SECTIONS.search(section))
    return has_implementation_verb or (bullet and in_technical_section and len(words) >= 5)


def _near_duplicate(left: str, right: str) -> bool:
    normalized_left = re.sub(r"[^a-z0-9]+", " ", left.lower()).strip()
    normalized_right = re.sub(r"[^a-z0-9]+", " ", right.lower()).strip()
    if normalized_left == normalized_right:
        return True
    sequence_ratio = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    left_terms, right_terms = set(normalized_left.split()), set(normalized_right.split())
    union = left_terms | right_terms
    jaccard = len(left_terms & right_terms) / len(union) if union else 1.0
    return sequence_ratio >= 0.88 or jaccard >= 0.82
