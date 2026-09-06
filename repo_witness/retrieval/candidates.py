from __future__ import annotations

from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import Path

from ..evidence import TEXT_EXTENSIONS
from ..ingest import MAX_FILE_BYTES, should_ignore

CHUNK_LINES = 10
CHUNK_STRIDE = 5
MAX_CHUNK_CHARS = 2000
EXTENSIONLESS_NAMES = {"dockerfile", "makefile"}


@dataclass(frozen=True)
class EvidenceChunk:
    """A bounded, line-anchored window of a repository text file."""

    path: str
    start_line: int
    end_line: int
    text: str


def _is_eligible(path: Path) -> bool:
    return (
        path.suffix.lower() in TEXT_EXTENSIONS
        or path.name.lower() in EXTENSIONLESS_NAMES
    )


def _read_lines(path: Path) -> list[str] | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw:
        return None
    return raw.decode("utf-8", errors="ignore").splitlines()


def _windows(line_count: int) -> Iterator[tuple[int, int]]:
    start = 0
    while start < line_count:
        yield start, min(line_count, start + CHUNK_LINES)
        if start + CHUNK_LINES >= line_count:
            return
        start += CHUNK_STRIDE


def build_candidates(
    root: Path,
    excluded_paths: Collection[str] | None = None,
) -> list[EvidenceChunk]:
    """Build deterministic, line-anchored evidence chunks for a repository.

    Traversal order, the extension allowlist, path normalization, excluded-path
    matching, and lenient UTF-8 decoding intentionally mirror
    ``repo_witness.evidence.retrieve_evidence``. That duplication is deliberate
    technical debt: sharing the code would mean editing the frozen lexical
    retriever, so the two implementations are kept in step by the parity tests
    in ``tests/test_retrieval_parity.py`` instead.

    Three checks are stricter here than in the lexical retriever, and are kept
    stricter on purpose rather than being pushed back into it:

    * ``ingest.should_ignore`` rejects vendored, virtual-environment, secret and
      binary-suffix paths.
    * Files above the ingestion per-file size limit are skipped.
    * A file containing a NUL byte is treated as binary and never chunked.

    Uploaded repositories are already filtered by ingestion, so these checks
    diverge from lexical eligibility only for directory trees that never passed
    through ``extract_repository`` -- the checked-in fixtures and ``sample_repo``
    -- where the parity tests confirm both retrievers see the same files.
    """
    excluded = {path.replace("\\", "/").casefold() for path in (excluded_paths or ())}
    chunks: list[EvidenceChunk] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not _is_eligible(path):
            continue
        relative = path.relative_to(root).as_posix()
        if relative.casefold() in excluded:
            continue
        if should_ignore(Path(relative)):
            continue
        lines = _read_lines(path)
        if not lines:
            continue
        for start, end in _windows(len(lines)):
            text = "\n".join(lines[start:end]).strip()
            if not text:
                continue
            chunks.append(
                EvidenceChunk(
                    path=relative,
                    start_line=start + 1,
                    end_line=end,
                    text=text[:MAX_CHUNK_CHARS],
                )
            )
    return chunks
