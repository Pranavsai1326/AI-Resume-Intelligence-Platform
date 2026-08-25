"""Unit tests for GeminiProvider (Phase 9F).

No real Gemini request is made anywhere in this file - the SDK's async client is monkeypatched
so request construction, response parsing, and failure handling can all be verified without a
network call or a real API key. Live-response verification is intentionally out of scope here;
see PROJECT_STATUS.md for what stays PENDING until a real GEMINI_API_KEY is provided.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from app.ai.providers import GeminiProvider, NullLLMProvider, get_llm_provider
from app.config import Settings, is_configured_api_key


def _settings(**overrides: object) -> Settings:
    return Settings(app_env="development", **overrides)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Placeholder-key detection (spec section 4: a copied .env.example must never be treated as real)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["YOUR_GEMINI_API_KEY_HERE", "your_gemini_api_key_here", "  YOUR_GEMINI_API_KEY_HERE  ", ""],
)
def test_placeholder_values_are_not_configured(value: str) -> None:
    assert is_configured_api_key(value) is False


def test_a_real_looking_key_is_configured() -> None:
    assert is_configured_api_key("AIzaSyD-not-a-real-key-but-not-a-placeholder-either") is True


class TestProviderSelection:
    def test_gemini_selected_with_placeholder_key_falls_back_to_null(self) -> None:
        settings = _settings(llm_provider="gemini", gemini_api_key="YOUR_GEMINI_API_KEY_HERE")
        provider = get_llm_provider(settings)
        assert isinstance(provider, NullLLMProvider)

    def test_gemini_selected_without_key_falls_back_to_null(self) -> None:
        settings = _settings(llm_provider="gemini", gemini_api_key="")
        provider = get_llm_provider(settings)
        assert isinstance(provider, NullLLMProvider)

    def test_gemini_selected_with_real_looking_key_returns_gemini_provider(self) -> None:
        settings = _settings(llm_provider="gemini", gemini_api_key="a-real-looking-key")
        provider = get_llm_provider(settings)
        assert isinstance(provider, GeminiProvider)
        assert provider.is_available() is True

    def test_gemini_capability_is_false_with_placeholder(self) -> None:
        settings = _settings(llm_provider="gemini", gemini_api_key="YOUR_GEMINI_API_KEY_HERE")
        assert settings.capabilities()["llm"] is False

    def test_gemini_capability_is_true_with_real_looking_key(self) -> None:
        settings = _settings(llm_provider="gemini", gemini_api_key="a-real-looking-key")
        assert settings.capabilities()["llm"] is True

    def test_gemini_model_is_configurable(self) -> None:
        settings = _settings(
            llm_provider="gemini",
            gemini_api_key="a-real-looking-key",
            llm_model_gemini="gemini-3.0-flash",
        )
        provider = get_llm_provider(settings)
        assert isinstance(provider, GeminiProvider)


# ---------------------------------------------------------------------------
# GeminiProvider.complete() - request construction, response parsing, failure handling
# ---------------------------------------------------------------------------


@dataclass
class _FakeUsage:
    prompt_token_count: int
    candidates_token_count: int


class _FakeModels:
    def __init__(self, response: object | None = None, exc: Exception | None = None) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


class _FakeAio:
    def __init__(self, models: _FakeModels) -> None:
        self.models = models


class _FakeClient:
    def __init__(self, models: _FakeModels) -> None:
        self.aio = _FakeAio(models)


async def test_complete_returns_none_when_key_is_a_placeholder() -> None:
    provider = GeminiProvider("YOUR_GEMINI_API_KEY_HERE", "gemini-2.5-flash", 30)
    result = await provider.complete(system="sys", user="hello", max_tokens=50)
    assert result is None


async def test_complete_constructs_the_request_and_parses_a_successful_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_response = SimpleNamespace(
        text="Reduced latency by tuning the query planner.",
        usage_metadata=_FakeUsage(prompt_token_count=120, candidates_token_count=18),
    )
    models = _FakeModels(response=fake_response)
    provider = GeminiProvider("a-real-looking-key", "gemini-2.5-flash", 30)
    monkeypatch.setattr(GeminiProvider, "_get_client", lambda self: _FakeClient(models))

    result = await provider.complete(
        system="You are a resume writer.", user="Rewrite: did stuff", max_tokens=200
    )

    assert result is not None
    assert result.text == "Reduced latency by tuning the query planner."
    assert result.input_tokens == 120
    assert result.output_tokens == 18

    assert len(models.calls) == 1
    call = models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["contents"] == "Rewrite: did stuff"
    assert call["config"].system_instruction == "You are a resume writer."
    assert call["config"].max_output_tokens == 200


async def test_complete_handles_an_empty_text_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_response = SimpleNamespace(text=None, usage_metadata=None)
    models = _FakeModels(response=fake_response)
    provider = GeminiProvider("a-real-looking-key", "gemini-2.5-flash", 30)
    monkeypatch.setattr(GeminiProvider, "_get_client", lambda self: _FakeClient(models))

    result = await provider.complete(system="sys", user="hi", max_tokens=50)
    assert result is not None
    assert result.text == ""
    assert result.input_tokens is None
    assert result.output_tokens is None


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("invalid api key"),
        TimeoutError("request timed out"),
        RuntimeError("429 rate limit exceeded"),
        ConnectionError("network unreachable"),
    ],
)
async def test_complete_returns_none_honestly_on_any_provider_failure(
    exc: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid key, timeout, rate limit, and network failure all resolve the same way from the
    caller's perspective - honest unavailability, never a fabricated response (AI_ARCHITECTURE.md
    section 5), matching the existing AnthropicProvider behaviour."""
    models = _FakeModels(exc=exc)
    provider = GeminiProvider("a-real-looking-key", "gemini-2.5-flash", 30)
    monkeypatch.setattr(GeminiProvider, "_get_client", lambda self: _FakeClient(models))

    result = await provider.complete(system="sys", user="hi", max_tokens=50)
    assert result is None


async def test_complete_never_leaks_the_api_key_into_the_response_or_an_exception(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    models = _FakeModels(exc=RuntimeError("boom"))
    secret = "AIzaSy-super-secret-value-should-never-appear-anywhere"
    provider = GeminiProvider(secret, "gemini-2.5-flash", 30)
    monkeypatch.setattr(GeminiProvider, "_get_client", lambda self: _FakeClient(models))

    result = await provider.complete(system="sys", user="hi", max_tokens=50)
    assert result is None
    assert secret not in caplog.text
