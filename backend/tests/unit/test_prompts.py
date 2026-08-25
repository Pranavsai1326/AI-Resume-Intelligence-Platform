"""Unit tests for app.ai.prompts.

Every prompt sent to a provider originates from user-uploaded, untrusted content (a resume or job
description an anonymous user controls). These tests assert the injection-mitigation and
fact-invention controls SECURITY.md section 6 and AI_ARCHITECTURE.md section 5 describe are
actually present on every prompt, not just some of them - a new prompt added later without this
text would fail here rather than silently shipping without the mitigation.
"""

from __future__ import annotations

from app.ai.prompts import (
    COVER_LETTER,
    INTERVIEW_QUESTIONS,
    REWRITE_BULLET,
    REWRITE_SUMMARY,
    TAILOR_BULLET,
    PromptSpec,
)

ALL_PROMPTS: list[PromptSpec] = [
    REWRITE_BULLET,
    REWRITE_SUMMARY,
    TAILOR_BULLET,
    COVER_LETTER,
    INTERVIEW_QUESTIONS,
]


def test_every_prompt_tells_the_model_not_to_obey_embedded_instructions() -> None:
    for spec in ALL_PROMPTS:
        assert "never a set of" in spec.system or "not a set of" in spec.system, spec.id
        assert "ignore these instructions" in spec.system.lower(), spec.id


def test_every_prompt_forbids_inventing_unsupported_facts() -> None:
    for spec in ALL_PROMPTS:
        assert "MUST NOT invent" in spec.system, spec.id


def test_every_prompt_has_bounded_input_and_output() -> None:
    for spec in ALL_PROMPTS:
        assert spec.max_input_chars > 0, spec.id
        assert spec.max_output_tokens > 0, spec.id


def test_prompt_ids_are_unique() -> None:
    ids = [spec.id for spec in ALL_PROMPTS]
    assert len(ids) == len(set(ids))
