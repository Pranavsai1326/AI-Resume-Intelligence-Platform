"""Embedding provider abstraction (AI_ARCHITECTURE.md section 8, ADR-0005).

The default provider runs a small ONNX model in-process (fastembed / bge-small-en-v1.5): resume
and job-description text never leaves the server for semantic matching, and no API key is
required. The provider is still feature-detected rather than assumed - the model is downloaded
to a local cache on first use, which can fail (no network, disk full, first run not yet
warmed up), and a provider that cannot load must report itself unavailable rather than crash a
request or silently fall back to keyword matching pretending to be semantic. Matches the same
honest-unavailable pattern as ``app.documents.extract.ocr``.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

from app.config import Settings
from app.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only; fastembed has no type stubs
    from fastembed import TextEmbedding

logger = get_logger(__name__)


class EmbeddingProvider(Protocol):
    def is_available(self) -> bool: ...
    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Return one embedding vector per input text, or ``None`` if embedding failed."""


class NullEmbeddingProvider:
    def is_available(self) -> bool:
        return False

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        return None


class FastEmbedProvider:
    """Local ONNX embeddings via fastembed. Lazily loads the model once per process."""

    __slots__ = ("_load_failed", "_model", "_model_name")

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: TextEmbedding | None = None
        self._load_failed = False

    def _get_model(self) -> TextEmbedding | None:
        if self._model is not None or self._load_failed:
            return self._model
        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        except Exception:
            logger.warning("embeddings.model_load_failed", model=self._model_name)
            self._load_failed = True
            self._model = None
        return self._model

    def is_available(self) -> bool:
        return self._get_model() is not None

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        model = self._get_model()
        if model is None or not texts:
            return None
        try:
            return [vector.tolist() for vector in model.embed(texts)]
        except Exception:
            logger.warning("embeddings.embed_failed", count=len(texts))
            return None


@lru_cache(maxsize=1)
def _fastembed_singleton(model_name: str) -> FastEmbedProvider:
    """One model instance per process - reloading per request would be needlessly slow."""
    return FastEmbedProvider(model_name)


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_backend == "fastembed":
        return _fastembed_singleton(settings.embedding_model)
    return NullEmbeddingProvider()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
