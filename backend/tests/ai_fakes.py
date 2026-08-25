"""Deterministic fake LLM provider for AI/tailor tests.

No real model, no network, no API key required. Mirrors the shape of ``FakeEmbeddingProvider``
in ``tests/matching_fakes.py``: a small, explicit fake that implements the real ``LLMProvider``
protocol so tests exercise the actual call sites rather than a parallel code path.
"""

from __future__ import annotations

from collections.abc import Callable

from app.ai.providers import LLMResponse


class FakeLLMProvider:
    """Returns a scripted or transform-based completion; never touches the network."""

    def __init__(
        self,
        *,
        available: bool = True,
        response_text: str | None = None,
        transform: Callable[[str], str] | None = None,
    ) -> None:
        self._available = available
        self._response_text = response_text
        self._transform = transform
        self.calls: list[dict[str, object]] = []

    def is_available(self) -> bool:
        return self._available

    async def complete(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.3
    ) -> LLMResponse | None:
        self.calls.append(
            {"system": system, "user": user, "max_tokens": max_tokens, "temperature": temperature}
        )
        if not self._available:
            return None
        if self._transform is not None:
            text = self._transform(user)
        elif self._response_text is not None:
            text = self._response_text
        else:
            text = f"Rewritten: {user}"
        return LLMResponse(text=text, input_tokens=10, output_tokens=10)


class FailingLLMProvider:
    """Available, but every call fails to return usable output (empty/None)."""

    def is_available(self) -> bool:
        return True

    async def complete(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.3
    ) -> LLMResponse | None:
        return None
