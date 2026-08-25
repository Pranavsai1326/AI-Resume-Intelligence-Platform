"""Recruiter screening endpoints: bulk candidate ingest, async status, ranking, comparison,
shortlist.

One job description, many candidate resumes. Each candidate is its own queue job
(``app.queue.inprocess``); the bulk-upload endpoint reads and size-bounds every file at request
time (an ``UploadFile`` cannot survive past the request) and returns immediately with the job ids
to poll, while ``app.screening.pipeline.process_candidate`` - validate, extract, structure,
redact, match - runs in the background. Candidate identity is redacted before matching and before
storage (PRD section 8): the *only* resume ever stored per candidate is the redacted one, so
there is no unredacted version anywhere in the session for a ranking or comparison view to
accidentally surface - blind review by construction, not a display-time filter a future endpoint
could forget to apply.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from functools import partial

from fastapi import APIRouter, File, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.core.deps import (
    ActiveSessionDep,
    JobQueueDep,
    RateLimiterDep,
    SessionManagerDep,
    SettingsDep,
)
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.ratelimit import RateLimitRule
from app.documents.tempfile_scope import read_upload_bounded
from app.jobs.models import JobDescription
from app.logging import get_logger
from app.queue.base import JobState
from app.screening.compare import ComparisonResult, compare_candidates
from app.screening.models import (
    CandidateResult,
    CandidateStatus,
    ScreeningContext,
    ScreeningStatusSummary,
)
from app.screening.pipeline import process_candidate
from app.screening.rank import RankedPage, rank_candidates
from app.sessions.manager import SessionManager
from app.sessions.models import SessionMeta

logger = get_logger(__name__)
router = APIRouter(prefix="/screening", tags=["screening"])

CANDIDATE_TTL_SECONDS = 3600


def _candidate_key(screening_id: str, candidate_id: str) -> str:
    return f"{screening_id}:{candidate_id}"


async def _get_context(
    manager: SessionManager, session: SessionMeta, screening_id: str
) -> ScreeningContext:
    raw = await manager.get_object(session, "screening", screening_id)
    if raw is None:
        raise NotFoundError("No screening context with that id exists in this session.")
    return ScreeningContext.model_validate_json(raw)


async def _get_job(manager: SessionManager, session: SessionMeta, job_id: str) -> JobDescription:
    raw = await manager.get_object(session, "job", job_id)
    if raw is None:
        raise NotFoundError("No job description with that id exists in this session.")
    return JobDescription.model_validate_json(raw)


async def _get_candidate(
    manager: SessionManager, session: SessionMeta, screening_id: str, candidate_id: str
) -> CandidateResult:
    raw = await manager.get_object(
        session, "screening_candidate", _candidate_key(screening_id, candidate_id)
    )
    if raw is None:
        raise NotFoundError("No completed candidate with that id exists in this screening.")
    return CandidateResult.model_validate_json(raw)


async def _run_and_store(
    *,
    raw: bytes,
    job: JobDescription,
    candidate_id: str,
    screening_id: str,
    settings: Settings,
    manager: SessionManager,
    session: SessionMeta,
) -> None:
    result = await process_candidate(raw, job, candidate_id, settings)
    await manager.put_object(
        session,
        "screening_candidate",
        _candidate_key(screening_id, candidate_id),
        result.model_dump_json(),
        ttl_seconds=CANDIDATE_TTL_SECONDS,
    )


class CreateScreeningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ScreeningContext)
async def create_screening(
    payload: CreateScreeningRequest, session: ActiveSessionDep, manager: SessionManagerDep
) -> ScreeningContext:
    await _get_job(manager, session, payload.job_id)  # 404s if the job doesn't exist yet

    context = ScreeningContext(
        screening_id=secrets.token_hex(10),
        job_id=payload.job_id,
        created_at=datetime.now(UTC),
    )
    await manager.put_object(session, "screening", context.screening_id, context.model_dump_json())
    logger.info("screening.created", job_id=payload.job_id)
    return context


class UploadCandidatesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ids: list[str] = Field(default_factory=list)


@router.post(
    "/{screening_id}/candidates",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadCandidatesResponse,
)
async def upload_candidates(
    screening_id: str,
    session: ActiveSessionDep,
    manager: SessionManagerDep,
    settings: SettingsDep,
    limiter: RateLimiterDep,
    queue: JobQueueDep,
    files: list[UploadFile] = File(...),
) -> UploadCandidatesResponse:
    context = await _get_context(manager, session, screening_id)
    job = await _get_job(manager, session, context.job_id)

    if not files:
        raise ValidationFailedError("At least one resume file is required.")
    remaining_budget = settings.max_bulk_resumes - len(context.candidate_ids)
    if len(files) > remaining_budget:
        raise ValidationFailedError(
            f"This screening already has {len(context.candidate_ids)} candidates; at most "
            f"{settings.max_bulk_resumes} are allowed per session."
        )

    await limiter.enforce(
        RateLimitRule("document_upload", settings.rate_limit_uploads_per_hour, 3600),
        session.session_id,
    )

    candidate_ids: list[str] = []
    for upload in files:
        raw = await read_upload_bounded(upload, settings)
        candidate_id = secrets.token_hex(10)
        candidate_ids.append(candidate_id)
        work = partial(
            _run_and_store,
            raw=raw,
            job=job,
            candidate_id=candidate_id,
            screening_id=screening_id,
            settings=settings,
            manager=manager,
            session=session,
        )
        await queue.enqueue(candidate_id, work, session_id=session.session_id)

    context.candidate_ids.extend(candidate_ids)
    await manager.put_object(session, "screening", screening_id, context.model_dump_json())
    await manager.increment_counter(session, "documents", by=len(candidate_ids))

    logger.info("screening.candidates_enqueued", count=len(candidate_ids))
    return UploadCandidatesResponse(candidate_ids=candidate_ids)


@router.get("/{screening_id}/status", response_model=ScreeningStatusSummary)
async def get_status(
    screening_id: str, session: ActiveSessionDep, manager: SessionManagerDep, queue: JobQueueDep
) -> ScreeningStatusSummary:
    context = await _get_context(manager, session, screening_id)

    statuses: list[CandidateStatus] = []
    for candidate_id in context.candidate_ids:
        job = queue.get_state(candidate_id)
        state = job.state if job is not None else JobState.PENDING
        error = job.error if job is not None else None
        statuses.append(CandidateStatus(candidate_id=candidate_id, state=state, error=error))

    return ScreeningStatusSummary(
        screening_id=screening_id,
        total=len(statuses),
        pending=sum(1 for s in statuses if s.state == JobState.PENDING),
        processing=sum(1 for s in statuses if s.state in (JobState.PROCESSING, JobState.RETRYING)),
        completed=sum(1 for s in statuses if s.state == JobState.COMPLETED),
        failed=sum(1 for s in statuses if s.state == JobState.FAILED),
        candidates=statuses,
    )


@router.get("/{screening_id}/ranking", response_model=RankedPage)
async def get_ranking(
    screening_id: str,
    session: ActiveSessionDep,
    manager: SessionManagerDep,
    min_score: float | None = None,
    limit: int = 20,
    offset: int = 0,
    descending: bool = True,
) -> RankedPage:
    context = await _get_context(manager, session, screening_id)

    results: list[CandidateResult] = []
    for candidate_id in context.candidate_ids:
        raw = await manager.get_object(
            session, "screening_candidate", _candidate_key(screening_id, candidate_id)
        )
        if raw is not None:
            results.append(CandidateResult.model_validate_json(raw))

    return rank_candidates(
        results, min_score=min_score, descending=descending, limit=limit, offset=offset
    )


@router.get("/{screening_id}/candidates/{candidate_id}", response_model=CandidateResult)
async def get_candidate(
    screening_id: str, candidate_id: str, session: ActiveSessionDep, manager: SessionManagerDep
) -> CandidateResult:
    await _get_context(manager, session, screening_id)
    return await _get_candidate(manager, session, screening_id, candidate_id)


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ids: list[str]


@router.post("/{screening_id}/compare", response_model=ComparisonResult)
async def compare(
    screening_id: str,
    payload: CompareRequest,
    session: ActiveSessionDep,
    manager: SessionManagerDep,
) -> ComparisonResult:
    await _get_context(manager, session, screening_id)
    results = [
        await _get_candidate(manager, session, screening_id, candidate_id)
        for candidate_id in payload.candidate_ids
    ]
    return compare_candidates(results)


class ShortlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    shortlisted: bool


@router.post("/{screening_id}/shortlist", response_model=CandidateResult)
async def shortlist(
    screening_id: str,
    payload: ShortlistRequest,
    session: ActiveSessionDep,
    manager: SessionManagerDep,
) -> CandidateResult:
    await _get_context(manager, session, screening_id)
    result = await _get_candidate(manager, session, screening_id, payload.candidate_id)
    updated = result.model_copy(update={"shortlisted": payload.shortlisted})
    await manager.put_object(
        session,
        "screening_candidate",
        _candidate_key(screening_id, payload.candidate_id),
        updated.model_dump_json(),
        ttl_seconds=CANDIDATE_TTL_SECONDS,
    )
    logger.info("screening.shortlist_updated", shortlisted=payload.shortlisted)
    return updated
