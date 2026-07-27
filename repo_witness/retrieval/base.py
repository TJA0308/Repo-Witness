from __future__ import annotations

from collections.abc import Collection
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..models import EvidenceSnippet


@runtime_checkable
class RetrievalStrategy(Protocol):
    def retrieve(
        self,
        root: Path,
        claim: str,
        limit: int,
        excluded_paths: Collection[str] | None = None,
    ) -> list[EvidenceSnippet]: ...
