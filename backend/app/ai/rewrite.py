"""AI-assisted rewriting of a single bullet or summary.

A proposal, never a mutation: the caller decides whether to accept it (AI_ARCHITECTURE.md
section 5 - "AI never mutates content in place"). Every proposal is fact-guarded before it is
returned; a proposal that fails the guard is still returned (the user should be able to see what
the model produced) but flagged, never silently discarded or silently accepted.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.ai.fact_guard import FactIndex, check
from app.ai.prompts import REWRITE_BULLET, REWRITE_SUMMARY, PromptSpec
from app.ai.providers import LLMProvider
from app.resume.models import Resume


class RewriteProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before: str
    after: str | None
    fact_guard_findings: list[str] = []
    available: bool
    #: Present only when `available` is False.
    unavailable_reason: str | None = None
    #: Total tokens spent on this call (0 when unavailable) - a count, never content, for
    #: session-level cost tracking (SECURITY.md section 4).
    tokens_used: int = 0


async def _rewrite(
    text: str, spec: PromptSpec, provider: LLMProvider, index: FactIndex
) -> RewriteProposal:
    if not provider.is_available():
        return RewriteProposal(
            before=text,
            after=None,
            fact_guard_findings=[],
            available=False,
            unavailable_reason="AI writing is not configured on this deployment.",
        )

    truncated = text[: spec.max_input_chars]
    response = await provider.complete(
        system=spec.system,
        user=truncated,
        max_tokens=spec.max_output_tokens,
        temperature=spec.temperature,
    )
    if response is None or not response.text.strip():
        return RewriteProposal(
            before=text,
            after=None,
            fact_guard_findings=[],
            available=False,
            unavailable_reason="The AI provider did not return a usable response.",
        )

    after = response.text.strip()
    findings = check(after, index)
    return RewriteProposal(
        before=text,
        after=after,
        fact_guard_findings=[f.message for f in findings],
        available=True,
        tokens_used=(response.input_tokens or 0) + (response.output_tokens or 0),
    )


async def rewrite_bullet(text: str, resume: Resume, provider: LLMProvider) -> RewriteProposal:
    return await _rewrite(text, REWRITE_BULLET, provider, FactIndex.build(resume))


async def rewrite_summary(text: str, resume: Resume, provider: LLMProvider) -> RewriteProposal:
    return await _rewrite(text, REWRITE_SUMMARY, provider, FactIndex.build(resume))
