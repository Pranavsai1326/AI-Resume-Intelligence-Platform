"""LLM provider abstraction (AI_ARCHITECTURE.md section 2).

Every AI-backed feature calls through this interface; a vendor SDK is imported nowhere else in
the codebase. ``NullLLMProvider`` is a first-class provider, not a fallback hack - with no API
key configured, every call returns ``None`` (honest unavailability) rather than failing
unpredictably or fabricating output. Matches the pattern already used for OCR
(``app.documents.extract.ocr``) and embeddings (``app.matching.embeddings``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.config import Settings, is_configured_api_key
from app.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from anthropic import AsyncAnthropic
    from google.genai import Client as GenAIClient

logger = get_logger(__name__)


@dataclass(slots=True)
class LLMResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMProvider(Protocol):
    def is_available(self) -> bool: ...

    async def complete(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.3
    ) -> LLMResponse | None:
        """Return the completion, or ``None`` if the call could not be made or failed."""


class NullLLMProvider:
    def is_available(self) -> bool:
        return False

    async def complete(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.3
    ) -> LLMResponse | None:
        return None


class AnthropicProvider:
    """Real provider. The vendor SDK import is confined to this class."""

    __slots__ = ("_api_key", "_client", "_model", "_timeout_seconds")

    def __init__(self, api_key: str, model: str, timeout_seconds: int) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client: AsyncAnthropic | None = None

    def _get_client(self) -> AsyncAnthropic:
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key, timeout=self._timeout_seconds)
        return self._client

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def complete(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.3
    ) -> LLMResponse | None:
        if not self.is_available():
            return None
        try:
            client = self._get_client()
            # `temperature` is not a typed kwarg on this SDK version's `create()`, but the
            # Messages API itself accepts it as a top-level request field; `extra_body` merges
            # into the raw JSON body regardless of what the Python wrapper's stub exposes.
            response = await client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                extra_body={"temperature": temperature},
            )
        except Exception:
            logger.warning("ai.completion_failed", model=self._model)
            return None

        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
        )


class GeminiProvider:
    """Real provider using Google's official GenAI SDK. Vendor SDK import confined here, same as
    ``AnthropicProvider`` - features call through ``LLMProvider``, never this class or the SDK
    directly (Feature -> LLMProvider -> GeminiProvider -> Gemini API, per Phase 9F's requirement).
    """

    __slots__ = ("_api_key", "_client", "_model", "_timeout_seconds")

    def __init__(self, api_key: str, model: str, timeout_seconds: int) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client: GenAIClient | None = None

    def _get_client(self) -> GenAIClient:
        if self._client is None:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=self._timeout_seconds * 1000),
            )
        return self._client

    def is_available(self) -> bool:
        return is_configured_api_key(self._api_key)

    async def complete(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.3
    ) -> LLMResponse | None:
        if not self.is_available():
            return None
        try:
            from google.genai import types

            client = self._get_client()
            response = await client.aio.models.generate_content(
                model=self._model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
        except Exception:
            # Deliberately broad, matching AnthropicProvider: an invalid key, a rate limit, a
            # timeout, or a network failure all resolve the same way from the caller's
            # perspective - honest unavailability, never a fabricated response.
            logger.warning("ai.completion_failed", model=self._model, provider="gemini")
            return None

        text = response.text or ""
        usage = response.usage_metadata
        return LLMResponse(
            text=text,
            input_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
            output_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
        )


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic" and is_configured_api_key(settings.anthropic_api_key):
        return AnthropicProvider(
            settings.anthropic_api_key, settings.llm_model_reasoning, settings.llm_timeout_seconds
        )
    if settings.llm_provider == "gemini" and is_configured_api_key(settings.gemini_api_key):
        return GeminiProvider(
            settings.gemini_api_key, settings.llm_model_gemini, settings.llm_timeout_seconds
        )
    return NullLLMProvider()
