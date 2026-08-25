"""Deterministic fake embedding provider for matching tests.

No real model, no network, no ~130MB download in the general test suite. Similarity is driven by
shared marker words between texts, which is enough to exercise the mechanics (rescaling, best-
match selection, the unavailable/degrade path) without asserting on real model output, which
would be fragile across model versions. Real-model behaviour is covered separately and only in
``tests/unit/test_embeddings.py``, which skips gracefully if the model cannot load.
"""

from __future__ import annotations

_MARKERS = (
    "python", "kubernetes", "backend", "chef", "pastry", "communication", "aws", "docker",
    "terraform", "billing", "distributed",
)


def _marker_vector(text: str) -> list[float]:
    lowered = text.lower()
    return [1.0 if marker in lowered else 0.0 for marker in _MARKERS]


class FakeEmbeddingProvider:
    """Cosine similarity of two texts equals the fraction of shared marker words."""

    def __init__(self, *, available: bool = True, fails_at_runtime: bool = False) -> None:
        self._available = available
        self._fails_at_runtime = fails_at_runtime

    def is_available(self) -> bool:
        return self._available

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self._available or self._fails_at_runtime:
            return None
        return [_marker_vector(text) for text in texts]
