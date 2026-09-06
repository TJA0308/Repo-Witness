from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
FAKE_EMBEDDING_DIMENSIONS = 64
_FAKE_TOKEN = re.compile(r"[a-zA-Z0-9]+")


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


class DeterministicFakeEmbeddingProvider:
    """Offline, dependency-free provider used by the test suite.

    Tokens are hashed into a fixed number of dimensions, so the same text always
    produces the same vector and no model download or network access is needed.
    """

    def __init__(
        self,
        model_id: str = "fake/deterministic-hashing-v1",
        dimensions: int = FAKE_EMBEDDING_DIMENSIONS,
    ) -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        self._model_id = model_id
        self._dimensions = dimensions

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self._dimensions
            for token in _FAKE_TOKEN.findall(text.lower()):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                vector[digest[0] % self._dimensions] += 1.0
            vectors.append(_normalize(vector))
        return vectors


class SentenceTransformerEmbeddingProvider:
    """Local CPU sentence-transformer provider.

    The model is loaded lazily on first use so importing this module never pulls
    in heavy dependencies. The model runs locally; no API key is used.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model = None

    @property
    def model_id(self) -> str:
        return self._model_name

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        encoded = model.encode(
            list(texts),
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return [[float(value) for value in row] for row in encoded]


class InMemoryEmbeddingCache:
    """Content-addressed in-memory embedding cache.

    The key combines the provider identity with a SHA-256 digest of the exact
    text, so changed content produces a different key and can never reuse a
    stale vector. The cache is process-local and is not persisted: it is not a
    repository index and it cannot speed up a fresh process invocation.

    A provider failure propagates and stores nothing, so a failed call never
    poisons the cache with a partial or placeholder vector.
    """

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider
        self._entries: dict[tuple[str, str], list[float]] = {}
        self.hits = 0
        self.misses = 0

    @property
    def model_id(self) -> str:
        return self._provider.model_id

    def _key(self, text: str) -> tuple[str, str]:
        return (
            self._provider.model_id,
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        keys = [self._key(text) for text in texts]
        missing: list[str] = []
        missing_keys: list[tuple[str, str]] = []
        pending: set[tuple[str, str]] = set()
        for text, key in zip(texts, keys):
            if key in self._entries or key in pending:
                continue
            pending.add(key)
            missing.append(text)
            missing_keys.append(key)
        if missing:
            computed = self._provider.embed(missing)
            if len(computed) != len(missing):
                raise ValueError("Embedding provider returned an unexpected vector count")
            self._entries.update(zip(missing_keys, computed))
        self.hits += len(keys) - len(missing_keys)
        self.misses += len(missing_keys)
        return [self._entries[key] for key in keys]
