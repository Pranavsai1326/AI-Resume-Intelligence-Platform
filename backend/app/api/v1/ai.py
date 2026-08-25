"""AI-assisted writing endpoints.

Every response is a proposal, never a mutation (AI_ARCHITECTURE.md section 5) - the caller
decides whether to save it as a new resume version via `POST /v1/resume/versions`. With no LLM
configured, `available: false` is returned rather than a fabricated rewrite or an error that
looks like a bug.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.ai.providers import get_llm_provider
from app.ai.rewrite import RewriteProposal, rewrite_bullet, rewrite_summary
from app.core.deps import ActiveSessionDep, RateLimiterDep, SessionManagerDep, SettingsDep
from app.core.errors import NotFoundError
from app.core.ratelimit import RateLimitRule
from app.documents.storage import StoredDocument
from app.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])


class RewriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    kind: Literal["bullet", "summary"]
    text: str


@router.post("/rewrite", response_model=RewriteProposal)
async def rewrite(
    payload: RewriteRequest,
    session: ActiveSessionDep,
    manager: SessionManagerDep,
    settings: SettingsDep,
    limiter: RateLimiterDep,
) -> RewriteProposal:
    await limiter.enforce(
        RateLimitRule("ai_calls", settings.rate_limit_ai_calls_per_hour, 3600), session.session_id
    )
    document_raw = await manager.get_object(session, "document", payload.document_id)
    if document_raw is None:
        raise NotFoundError("No document with that id exists in this session.")
    stored = StoredDocument.model_validate_json(document_raw)
    if stored.resume is None:
        raise NotFoundError("This document has no structured resume.")

    provider = get_llm_provider(settings)
    if payload.kind == "bullet":
        proposal = await rewrite_bullet(payload.text, stored.resume, provider)
    else:
        proposal = await rewrite_summary(payload.text, stored.resume, provider)

    if provider.is_available():
        # Each increment_counter call returns the updated SessionMeta and must be chained into
        # the next one - passing the same stale `session` twice would make the second call
        # overwrite the store with a copy that never saw the first increment.
        updated = await manager.increment_counter(session, "ai_calls")
        if proposal.tokens_used:
            await manager.increment_counter(updated, "ai_tokens", by=proposal.tokens_used)
    logger.info("ai.rewrite_requested", kind=payload.kind, available=proposal.available)
    return proposal
