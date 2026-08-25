"""Resume tailoring endpoints.

Generates proposals from a job's skill gaps (app.matching.gaps, Phase 4) and, separately, applies
whichever ones the user accepted as a new resume version - two explicit steps, never one implicit
mutation (AI_ARCHITECTURE.md section 5).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from app.ai.providers import get_llm_provider
from app.ai.tailor import TailorProposal, apply_proposals, generate_tailor_proposals
from app.core.deps import ActiveSessionDep, RateLimiterDep, SessionManagerDep, SettingsDep
from app.core.errors import NotFoundError
from app.core.ratelimit import RateLimitRule, enforce_session_ai_token_budget
from app.jobs.models import JobDescription
from app.logging import get_logger
from app.matching.embeddings import get_embedding_provider
from app.matching.gaps import compute_skill_gaps
from app.resume.version_store import add_version, get_version_or_original
from app.resume.versions import ResumeVersion, VersionSource, new_version_id
from app.sessions.manager import SessionManager
from app.sessions.models import SessionMeta

logger = get_logger(__name__)
router = APIRouter(prefix="/tailor", tags=["tailor"])


async def _get_job(manager: SessionManager, session: SessionMeta, job_id: str) -> JobDescription:
    raw = await manager.get_object(session, "job", job_id)
    if raw is None:
        raise NotFoundError("No job description with that id exists in this session.")
    return JobDescription.model_validate_json(raw)


class GenerateTailorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    job_id: str
    version_id: str | None = None


@router.post("", response_model=list[TailorProposal])
async def generate(
    payload: GenerateTailorRequest,
    session: ActiveSessionDep,
    manager: SessionManagerDep,
    settings: SettingsDep,
    limiter: RateLimiterDep,
) -> list[TailorProposal]:
    version = await get_version_or_original(
        manager, session, payload.document_id, payload.version_id
    )
    job = await _get_job(manager, session, payload.job_id)

    embedding_provider = get_embedding_provider(settings)
    gaps = compute_skill_gaps(job, version.resume, embedding_provider)

    llm_provider = get_llm_provider(settings)
    if llm_provider.is_available():
        # Only the AI-assisted path draws on the shared AI budget - deterministic tailoring
        # (skill reordering, requirement reminders) costs nothing and stays unbounded by it.
        await limiter.enforce(
            RateLimitRule("ai_calls", settings.rate_limit_ai_calls_per_hour, 3600),
            session.session_id,
        )
        enforce_session_ai_token_budget(session, settings.rate_limit_ai_tokens_per_session)
    proposals = await generate_tailor_proposals(version.resume, gaps, llm_provider)

    ai_proposal_count = sum(1 for p in proposals if p.requires_ai)
    if ai_proposal_count:
        updated = await manager.increment_counter(session, "ai_calls", by=ai_proposal_count)
        tokens_used = sum(p.tokens_used for p in proposals if p.requires_ai)
        if tokens_used:
            await manager.increment_counter(updated, "ai_tokens", by=tokens_used)

    logger.info("tailor.proposals_generated", count=len(proposals))
    return proposals


class ApplyTailorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    version_id: str | None = None
    label: str = "Tailored"
    proposals: list[TailorProposal]


@router.post("/apply", status_code=status.HTTP_201_CREATED, response_model=ResumeVersion)
async def apply(
    payload: ApplyTailorRequest, session: ActiveSessionDep, manager: SessionManagerDep
) -> ResumeVersion:
    base_version = await get_version_or_original(
        manager, session, payload.document_id, payload.version_id
    )
    updated_resume = apply_proposals(base_version.resume, payload.proposals)

    new_version = ResumeVersion(
        version_id=new_version_id(),
        document_id=payload.document_id,
        label=payload.label,
        source=VersionSource.AI_TAILORED,
        resume=updated_resume,
        created_at=datetime.now(UTC),
        based_on_version_id=base_version.version_id,
    )
    await add_version(manager, session, new_version)

    logger.info("tailor.applied", proposal_count=len(payload.proposals))
    return new_version
