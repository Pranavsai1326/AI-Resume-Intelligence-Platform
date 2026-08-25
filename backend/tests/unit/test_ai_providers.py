"""Unit tests for app.ai.providers."""

from __future__ import annotations

from app.ai.providers import AnthropicProvider, NullLLMProvider, get_llm_provider
from app.config import Settings
from tests.ai_fakes import FakeLLMProvider


def _settings(**overrides: object) -> Settings:
    return Settings(app_env="development", **overrides)  # type: ignore[arg-type]


async def test_null_provider_is_never_available() -> None:
    provider = NullLLMProvider()
    assert provider.is_available() is False


async def test_null_provider_complete_always_returns_none() -> None:
    provider = NullLLMProvider()
    result = await provider.complete(system="sys", user="hello", max_tokens=50)
    assert result is None


def test_get_llm_provider_defaults_to_null_when_unconfigured() -> None:
    settings = _settings(llm_provider="null")
    provider = get_llm_provider(settings)
    assert isinstance(provider, NullLLMProvider)


def test_get_llm_provider_returns_null_when_anthropic_selected_without_key() -> None:
    settings = _settings(llm_provider="anthropic", anthropic_api_key="")
    provider = get_llm_provider(settings)
    assert isinstance(provider, NullLLMProvider)


def test_get_llm_provider_returns_anthropic_provider_when_configured() -> None:
    settings = _settings(llm_provider="anthropic", anthropic_api_key="sk-test-key")
    provider = get_llm_provider(settings)
    assert isinstance(provider, AnthropicProvider)
    assert provider.is_available() is True


async def test_fake_provider_records_calls_and_honours_availability() -> None:
    fake = FakeLLMProvider(available=False)
    assert fake.is_available() is False
    result = await fake.complete(system="sys", user="hi", max_tokens=10)
    assert result is None
    assert fake.calls  # call is still recorded even though nothing was "returned"


async def test_fake_provider_returns_scripted_text() -> None:
    fake = FakeLLMProvider(available=True, response_text="Improved bullet text.")
    result = await fake.complete(system="sys", user="hi", max_tokens=10)
    assert result is not None
    assert result.text == "Improved bullet text."
