from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from ..evidence import MAX_CANDIDATES
from ..models import EvidenceSnippet
from .base import RetrievalStrategy
from .lexical import LexicalRetrievalStrategy

__all__ = [
    "LexicalRetrievalStrategy",
    "RetrievalStrategy",
    "retrieve_evidence_with_strategy",
]


def retrieve_evidence_with_strategy(
    strategy: RetrievalStrategy,
    root: Path,
    claim: str,
    limit: int = MAX_CANDIDATES,
    excluded_paths: Collection[str] | None = None,
) -> list[EvidenceSnippet]:
    return strategy.retrieve(
        root,
        claim,
        limit=limit,
        excluded_paths=excluded_paths,
    )
