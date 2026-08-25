"""Resume<->job matching endpoint.

Computes all six match components plus the skill-gap breakdown in a single pass. API.md's Phase 0
sketch had two endpoints (a match score, and a separate gap-analysis call); consolidated to one
once it was clear gap analysis reuses the exact same deterministic checks the component scores
already compute - a second request would only mean doing that work twice.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from app.core.deps import ActiveSessionDep, SessionManagerDep, SettingsDep
from app.core.errors import NotFoundError, ValidationFailedError
from app.documents.storage import StoredDocument
from app.jobs.models import JobDescription
from app.logging import get_logger
from app.matching.engine import compute_job_match
from app.matching.models import JobMatchResult

logger = get_logger(__name__)
router = APIRouter(prefix="/match", tags=["match"])

MATCH_TTL_SECONDS = 3600


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    job_id: str


def _match_object_id(document_id: str, job_id: str) -> str:
    return f"{document_id}:{job_id}"


@router.post("", status_code=status.HTTP_201_CREATED, response_model=JobMatchResult)
async def match_resume_to_job(
    payload: MatchRequest,
    session: ActiveSessionDep,
    manager: SessionManagerDep,
    settings: SettingsDep,
) -> JobMatchResult:
    object_id = _match_object_id(payload.document_id, payload.job_id)
    cached = await manager.get_object(session, "match", object_id)
    if cached:
        return JobMatchResult.model_validate_json(cached)

    document_raw = await manager.get_object(session, "document", payload.document_id)
    if document_raw is None:
        raise NotFoundError("No document with that id exists in this session.")
    stored = StoredDocument.model_validate_json(document_raw)
    if stored.resume is None:
        raise ValidationFailedError("This document has no structured resume to match.")

    job_raw = await manager.get_object(session, "job", payload.job_id)
    if job_raw is None:
        raise NotFoundError("No job description with that id exists in this session.")
    job = JobDescription.model_validate_json(job_raw)

    result = compute_job_match(stored.resume, job, settings)

    await manager.put_object(
        session, "match", object_id, result.model_dump_json(), ttl_seconds=MATCH_TTL_SECONDS
    )
    await manager.increment_counter(session, "analyses")

    logger.info("match.completed", overall=result.overall, degraded=result.degraded)
    return result
