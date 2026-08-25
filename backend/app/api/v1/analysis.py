"""Resume analysis endpoints.

Analysing a document is itself compute-once (AI_ARCHITECTURE.md section 6): the result is cached
in the session keyed by `document_id`, so re-requesting analysis of the same document is a cache
hit rather than re-running six scoring passes.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.analysis.engine import compute_resume_health
from app.analysis.models import ResumeHealthResult
from app.core.deps import ActiveSessionDep, SessionManagerDep
from app.core.errors import NotFoundError, ValidationFailedError
from app.documents.storage import StoredDocument
from app.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/analysis", tags=["analysis"])

ANALYSIS_TTL_SECONDS = 3600


class AnalyzeResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str


@router.post("/resume", status_code=201, response_model=ResumeHealthResult)
async def analyze_resume(
    payload: AnalyzeResumeRequest, session: ActiveSessionDep, manager: SessionManagerDep
) -> ResumeHealthResult:
    cached_raw = await manager.get_object(session, "analysis", payload.document_id)
    if cached_raw:
        return ResumeHealthResult.model_validate_json(cached_raw)

    document_raw = await manager.get_object(session, "document", payload.document_id)
    if document_raw is None:
        raise NotFoundError("No document with that id exists in this session.")

    stored = StoredDocument.model_validate_json(document_raw)
    if stored.resume is None:
        raise ValidationFailedError(
            "This document was uploaded as a job description, not a resume, and has no "
            "structured resume to analyze."
        )

    result = compute_resume_health(stored.resume, stored.layout)

    await manager.put_object(
        session,
        "analysis",
        payload.document_id,
        result.model_dump_json(),
        ttl_seconds=ANALYSIS_TTL_SECONDS,
    )
    await manager.increment_counter(session, "analyses")

    logger.info("analysis.completed", overall=result.overall)
    return result


@router.get("/{analysis_id}", response_model=ResumeHealthResult)
async def get_analysis(
    analysis_id: str, session: ActiveSessionDep, manager: SessionManagerDep
) -> ResumeHealthResult:
    """Retrieve a previously computed analysis. ``analysis_id`` is the document's id."""
    raw = await manager.get_object(session, "analysis", analysis_id)
    if raw is None:
        raise NotFoundError
    return ResumeHealthResult.model_validate_json(raw)
