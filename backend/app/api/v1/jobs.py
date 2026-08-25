"""Job description endpoints.

Parsing is deterministic (AI_ARCHITECTURE.md Layer 1) - see ``app.jobs.parse``. A JD may be
pasted directly or uploaded first as a document (``kind=job_description`` via ``/v1/documents``)
and referenced by its ``document_id``; either way, only the parsed, structured result is stored,
under its own id.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, model_validator

from app.core.deps import ActiveSessionDep, SessionManagerDep
from app.core.errors import NotFoundError, ValidationFailedError
from app.documents.storage import StoredDocument
from app.jobs.models import JobDescription
from app.jobs.parse import parse_job_description
from app.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])

#: Session-scoped working data, matching the document/analysis TTLs.
JOB_TTL_SECONDS = 3600


class CreateJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    document_id: str | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> CreateJobRequest:
        if bool(self.text) == bool(self.document_id):
            raise ValueError("provide exactly one of 'text' or 'document_id'")
        return self


class JobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    job: JobDescription


@router.post("", status_code=status.HTTP_201_CREATED, response_model=JobResponse)
async def create_job(
    payload: CreateJobRequest, session: ActiveSessionDep, manager: SessionManagerDep
) -> JobResponse:
    if payload.document_id:
        raw = await manager.get_object(session, "document", payload.document_id)
        if raw is None:
            raise NotFoundError("No document with that id exists in this session.")
        text = StoredDocument.model_validate_json(raw).text
    else:
        text = payload.text or ""

    if not text.strip():
        raise ValidationFailedError("The job description text is empty.")

    job = parse_job_description(text)
    job_id = secrets.token_hex(12)
    await manager.put_object(
        session, "job", job_id, job.model_dump_json(), ttl_seconds=JOB_TTL_SECONDS
    )

    logger.info("job.created", requirement_count=len(job.requirements))
    return JobResponse(job_id=job_id, job=job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str, session: ActiveSessionDep, manager: SessionManagerDep
) -> JobResponse:
    raw = await manager.get_object(session, "job", job_id)
    if raw is None:
        raise NotFoundError
    return JobResponse(job_id=job_id, job=JobDescription.model_validate_json(raw))
