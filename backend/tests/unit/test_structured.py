"""Unit tests for app.ai.structured (JSON-in-prompt structured output + bounded repair)."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from app.ai.prompts import PromptSpec
from app.ai.providers import NullLLMProvider
from app.ai.structured import complete_structured
from tests.ai_fakes import FailingLLMProvider, FakeLLMProvider

_SPEC = PromptSpec(
    id="test_spec",
    version="1.0.0",
    system="test",
    max_input_chars=1000,
    max_output_tokens=100,
    temperature=0.3,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    count: int


async def test_returns_none_when_provider_unavailable() -> None:
    result = await complete_structured(
        NullLLMProvider(), spec=_SPEC, user="hello", schema=_Schema
    )
    assert result is None


async def test_returns_none_when_provider_fails() -> None:
    result = await complete_structured(
        FailingLLMProvider(), spec=_SPEC, user="hello", schema=_Schema
    )
    assert result is None


async def test_parses_valid_json_on_first_try() -> None:
    fake = FakeLLMProvider(response_text=json.dumps({"name": "widget", "count": 3}))
    result = await complete_structured(fake, spec=_SPEC, user="hello", schema=_Schema)
    assert result == _Schema(name="widget", count=3)
    assert len(fake.calls) == 1


async def test_strips_markdown_code_fence() -> None:
    fake = FakeLLMProvider(
        response_text='```json\n{"name": "widget", "count": 3}\n```'
    )
    result = await complete_structured(fake, spec=_SPEC, user="hello", schema=_Schema)
    assert result == _Schema(name="widget", count=3)


async def test_extracts_json_object_surrounded_by_prose() -> None:
    fake = FakeLLMProvider(
        response_text='Sure, here you go: {"name": "widget", "count": 3} hope that helps!'
    )
    result = await complete_structured(fake, spec=_SPEC, user="hello", schema=_Schema)
    assert result == _Schema(name="widget", count=3)


async def test_repairs_invalid_json_on_second_attempt() -> None:
    responses = iter(["not json at all", json.dumps({"name": "widget", "count": 3})])

    fake = FakeLLMProvider(transform=lambda _user: next(responses))
    result = await complete_structured(fake, spec=_SPEC, user="hello", schema=_Schema)
    assert result == _Schema(name="widget", count=3)
    assert len(fake.calls) == 2
    assert "could not be used" in fake.calls[1]["user"]  # type: ignore[operator]


async def test_gives_up_after_one_failed_repair_attempt() -> None:
    fake = FakeLLMProvider(response_text="still not json")
    result = await complete_structured(fake, spec=_SPEC, user="hello", schema=_Schema)
    assert result is None
    assert len(fake.calls) == 2  # original attempt + exactly one repair, never more


async def test_schema_mismatch_is_treated_as_a_failure_too() -> None:
    fake = FakeLLMProvider(response_text=json.dumps({"name": "widget"}))  # missing "count"
    result = await complete_structured(fake, spec=_SPEC, user="hello", schema=_Schema)
    assert result is None
    assert len(fake.calls) == 2
