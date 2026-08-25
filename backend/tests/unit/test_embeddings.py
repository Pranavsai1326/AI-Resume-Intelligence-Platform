"""Real fastembed model behaviour.

Deliberately separate from the fast, hermetic default suite (tests/matching_fakes.py covers the
mechanics everywhere else): this exercises the actual ONNX model, which downloads to a local
cache on first use. Skips gracefully rather than failing when the model cannot load (offline
environment, first run with no cache yet, disk constraints) - the same honest-unavailable
contract the provider itself implements, applied to its own test.
"""

from __future__ import annotations

import pytest

from app.matching.embeddings import FastEmbedProvider, NullEmbeddingProvider, cosine_similarity

MODEL_NAME = "BAAI/bge-small-en-v1.5"


@pytest.fixture(scope="module")
def provider() -> FastEmbedProvider:
    instance = FastEmbedProvider(MODEL_NAME)
    if not instance.is_available():
        pytest.skip("fastembed model could not be loaded (offline or not yet cached)")
    return instance


def test_null_provider_is_never_available() -> None:
    assert NullEmbeddingProvider().is_available() is False
    assert NullEmbeddingProvider().embed(["anything"]) is None


def test_real_provider_embeds_text(provider: FastEmbedProvider) -> None:
    vectors = provider.embed(["Python backend engineer"])
    assert vectors is not None
    assert len(vectors) == 1
    assert len(vectors[0]) == 384  # bge-small-en-v1.5 output dimension


def test_related_texts_score_higher_than_unrelated(provider: FastEmbedProvider) -> None:
    vectors = provider.embed(
        [
            "Python backend engineer with Kubernetes experience",
            "Experienced Python developer working on cloud infrastructure",
            "Award-winning chef specialising in French pastry",
        ]
    )
    assert vectors is not None
    related = cosine_similarity(vectors[0], vectors[1])
    unrelated = cosine_similarity(vectors[0], vectors[2])
    assert related > unrelated
    assert related > 0.7
    assert unrelated < 0.6


def test_empty_input_returns_empty_list(provider: FastEmbedProvider) -> None:
    assert provider.embed([]) is None


def test_repeated_calls_reuse_the_loaded_model(provider: FastEmbedProvider) -> None:
    """The model is loaded once (see FastEmbedProvider._get_model); a second call is fast and
    produces identical output for identical input."""
    first = provider.embed(["consistent text"])
    second = provider.embed(["consistent text"])
    assert first == second
