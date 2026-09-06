from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from pathlib import Path

from ..evidence import MAX_CANDIDATES, MAX_EXCERPT_CHARS
from ..models import EvidenceSnippet
from .candidates import EvidenceChunk, build_candidates
from .embeddings import EmbeddingProvider, InMemoryEmbeddingCache


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Cosine similarity requires vectors of equal length")
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


TRUNCATION_MARKER = "\n[excerpt truncated]"


def _excerpt(root: Path, chunk: EvidenceChunk) -> str:
    """Render a chunk's exact lines, marking truncation rather than hiding it.

    An excerpt longer than the shared excerpt cap is cut, but the cut is stated
    explicitly so the reported line range is never silently wider than the text.
    """
    lines = (root / chunk.path).read_text(encoding="utf-8", errors="ignore").splitlines()
    numbered = "\n".join(
        f"{number + 1}: {lines[number]}"
        for number in range(chunk.start_line - 1, min(chunk.end_line, len(lines)))
    )
    if len(numbered) <= MAX_EXCERPT_CHARS:
        return numbered
    return numbered[: MAX_EXCERPT_CHARS - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER


class SemanticRetrievalStrategy:
    """Rank deterministic evidence chunks by embedding cosine similarity.

    The strategy depends only on an embedding provider contract; it never loads
    a model itself and never calls a language model. It is an experimental
    strategy and is not the production default.
    """

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._cache = InMemoryEmbeddingCache(provider)

    @property
    def model_id(self) -> str:
        return self._cache.model_id

    @property
    def cache(self) -> InMemoryEmbeddingCache:
        return self._cache

    def retrieve(
        self,
        root: Path,
        claim: str,
        limit: int = MAX_CANDIDATES,
        excluded_paths: Collection[str] | None = None,
    ) -> list[EvidenceSnippet]:
        if limit <= 0 or not claim.strip():
            return []
        chunks = build_candidates(root, excluded_paths)
        if not chunks:
            return []
        claim_vector = self._cache.embed([claim])[0]
        chunk_vectors = self._cache.embed([chunk.text for chunk in chunks])
        scored = [
            (cosine_similarity(claim_vector, vector), chunk)
            for vector, chunk in zip(chunk_vectors, chunks)
        ]
        scored.sort(key=lambda item: (-item[0], item[1].path, item[1].start_line))
        return [
            EvidenceSnippet(
                path=chunk.path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                excerpt=_excerpt(root, chunk),
                relevance=f"Semantic cosine similarity {score:.4f}; model {self.model_id}",
            )
            for score, chunk in scored[:limit]
        ]
