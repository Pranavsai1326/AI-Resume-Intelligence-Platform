"""Career intelligence endpoints: cover letters, interview prep, learning priorities.

All three build on Phase 4's job/matching work and Phase 5's versioned resumes and LLM provider
abstraction - no new persistence, no new session-storage kind. Cover letters and interview
questions are Layer 3 (LLM, honestly unavailable with no key configured); learning priorities are
pure Layer 1, reordering data the skill-gap computation already produces.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.ai.cover_letter import CoverLetterProposal, generate_cover_letter
from app.ai.interview import InterviewPrepProposal, generate_interview_questions
from app.ai.providers import get_llm_provider
from app.core.deps import ActiveSessionDep, SessionManagerDep, SettingsDep
from app.core.errors import NotFoundError
from app.jobs.models import JobDescription
from app.logging import get_logger
from app.matching.embeddings import get_embedding_provider
from app.matching.gaps import compute_skill_gaps
from app.matching.learning_priorities import LearningPriorityResult, compute_learning_priorities
from app.resume.version_store import get_version_or_original
from app.sessions.manager import SessionManager
from app.sessions.models import SessionMeta

logger = get_logger(__name__)
router = APIRouter(tags=["career"])


async def _get_job(manager: SessionManager, session: SessionMeta, job_id: str) -> JobDescription:
    raw = await manager.get_object(session, "job", job_id)
    if raw is None:
        raise NotFoundError("No job description with that id exists in this session.")
    return JobDescription.model_validate_json(raw)


class CareerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    job_id: str
    version_id: str | None = None


@router.post("/cover-letter", response_model=CoverLetterProposal)
async def cover_letter(
    payload: CareerRequest,
    session: ActiveSessionDep,
    manager: SessionManagerDep,
    settings: SettingsDep,
) -> CoverLetterProposal:
    version = await get_version_or_original(
        manager, session, payload.document_id, payload.version_id
    )
    job = await _get_job(manager, session, payload.job_id)

    provider = get_llm_provider(settings)
    proposal = await generate_cover_letter(version.resume, job, provider)

    if proposal.available:
        await manager.increment_counter(session, "ai_calls")
    logger.info("career.cover_letter_requested", available=proposal.available)
    return proposal


@router.post("/interview/questions", response_model=InterviewPrepProposal)
async def interview_questions(
    payload: CareerRequest,
    session: ActiveSessionDep,
    manager: SessionManagerDep,
    settings: SettingsDep,
) -> InterviewPrepProposal:
    version = await get_version_or_original(
        manager, session, payload.document_id, payload.version_id
    )
    job = await _get_job(manager, session, payload.job_id)

    provider = get_llm_provider(settings)
    proposal = await generate_interview_questions(version.resume, job, provider)

    if proposal.available:
        await manager.increment_counter(session, "ai_calls")
    logger.info("career.interview_questions_requested", available=proposal.available)
    return proposal


@router.post("/learning-priorities", response_model=LearningPriorityResult)
async def learning_priorities(
    payload: CareerRequest,
    session: ActiveSessionDep,
    manager: SessionManagerDep,
    settings: SettingsDep,
) -> LearningPriorityResult:
    version = await get_version_or_original(
        manager, session, payload.document_id, payload.version_id
    )
    job = await _get_job(manager, session, payload.job_id)

    embedding_provider = get_embedding_provider(settings)
    gaps = compute_skill_gaps(job, version.resume, embedding_provider)
    result = compute_learning_priorities(gaps)

    logger.info("career.learning_priorities_requested", count=len(result.priorities))
    return result
