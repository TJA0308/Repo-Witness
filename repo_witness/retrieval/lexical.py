from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from ..evidence import MAX_CANDIDATES, retrieve_evidence
from ..models import EvidenceSnippet


class LexicalRetrievalStrategy:
    def retrieve(
        self,
        root: Path,
        claim: str,
        limit: int = MAX_CANDIDATES,
        excluded_paths: Collection[str] | None = None,
    ) -> list[EvidenceSnippet]:
        return retrieve_evidence(
            root,
            claim,
            limit=limit,
            excluded_paths=excluded_paths,
        )
