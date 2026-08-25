"""Document upload and retrieval.

Upload -> validate -> extract -> (resume documents only) structure -> store in the session under
a content-hash cache key, so re-uploading identical bytes is a cache hit rather than repeated
work (AI_ARCHITECTURE.md section 6, "parse once, structure once, reuse"). Nothing here is written
anywhere but the ephemeral session store; every stored object carries the same TTL and is gone
when the session is.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from typing import Literal

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.core.deps import ActiveSessionDep, RateLimiterDep, SessionManagerDep, SettingsDep
from app.core.errors import DocumentProcessingTimeoutError, NotFoundError
from app.core.ratelimit import RateLimitRule
from app.documents.extract import extract
from app.documents.extract.base import LayoutSignals
from app.documents.storage import DOCUMENT_TTL_SECONDS, StoredDocument
from app.documents.structure import build_resume
from app.documents.tempfile_scope import read_upload_bounded
from app.documents.upload import DocumentKind, sniff_kind
from app.logging import get_logger
from app.resume.models import Resume

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

#: Wall-clock ceiling for one extraction pass - every parse stage is bounded, so a hung parser
#: fails the request rather than the process (SECURITY.md section 2).
EXTRACTION_TIMEOUT_SECONDS = 20


class ResumeSummary(BaseModel):
    """Counts only - the full structured resume is fetched separately via GET."""

    model_config = ConfigDict(extra="forbid")

    has_name: bool
    has_email: bool
    has_phone: bool
    has_summary: bool
    experience_entries: int
    education_entries: int
    skill_groups: int
    project_entries: int
    certification_entries: int
    custom_sections: int


def _summarize(resume: Resume) -> ResumeSummary:
    return ResumeSummary(
        has_name=resume.contact.full_name is not None,
        has_email=resume.contact.email is not None,
        has_phone=resume.contact.phone is not None,
        has_summary=resume.summary is not None,
        experience_entries=len(resume.experience),
        education_entries=len(resume.education),
        skill_groups=len(resume.skills),
        project_entries=len(resume.projects),
        certification_entries=len(resume.certifications),
        custom_sections=len(resume.custom_sections),
    )


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    kind: DocumentKind
    layout: LayoutSignals
    ocr_used: bool
    text_length: int
    #: ``None`` for a job-description upload - JD requirement extraction is Phase 4.
    resume_summary: ResumeSummary | None
    #: True if these exact bytes were already processed in this session.
    cached: bool


class DocumentDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    kind: DocumentKind
    layout: LayoutSignals
    ocr_used: bool
    text: str
    resume: Resume | None


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DocumentUploadResponse)
async def upload_document(
    session: ActiveSessionDep,
    manager: SessionManagerDep,
    settings: SettingsDep,
    limiter: RateLimiterDep,
    file: UploadFile = File(...),
    kind: Literal["resume", "job_description"] = Form("resume"),
) -> DocumentUploadResponse:
    await limiter.enforce(
        RateLimitRule("document_upload", settings.rate_limit_uploads_per_hour, 3600),
        session.session_id,
    )
    raw = await read_upload_bounded(file, settings)
    content_hash = hashlib.sha256(raw).hexdigest()

    cached_id = await manager.get_object(session, "content_hash", content_hash)
    if cached_id:
        cached_raw = await manager.get_object(session, "document", cached_id)
        if cached_raw:
            stored = StoredDocument.model_validate_json(cached_raw)
            return DocumentUploadResponse(
                document_id=stored.document_id,
                kind=stored.kind,
                layout=stored.layout,
                ocr_used=stored.ocr_used,
                text_length=len(stored.text),
                resume_summary=_summarize(stored.resume) if stored.resume else None,
                cached=True,
            )

    detected_kind = sniff_kind(raw)

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(extract, detected_kind, raw, settings),
            timeout=EXTRACTION_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise DocumentProcessingTimeoutError from exc

    resume = build_resume(result.text) if kind == "resume" else None

    document_id = secrets.token_hex(12)
    stored = StoredDocument(
        document_id=document_id,
        kind=result.kind,
        layout=result.layout,
        ocr_used=result.ocr_used,
        text=result.text,
        resume=resume,
    )

    await manager.put_object(
        session, "document", document_id, stored.model_dump_json(), ttl_seconds=DOCUMENT_TTL_SECONDS
    )
    await manager.put_object(
        session, "content_hash", content_hash, document_id, ttl_seconds=DOCUMENT_TTL_SECONDS
    )
    await manager.increment_counter(session, "documents")

    logger.info(
        "document.uploaded",
        kind=result.kind.value,
        pages=result.layout.page_count,
        ocr_used=result.ocr_used,
    )

    return DocumentUploadResponse(
        document_id=document_id,
        kind=result.kind,
        layout=result.layout,
        ocr_used=result.ocr_used,
        text_length=len(result.text),
        resume_summary=_summarize(resume) if resume else None,
        cached=False,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: str, session: ActiveSessionDep, manager: SessionManagerDep
) -> DocumentDetail:
    raw = await manager.get_object(session, "document", document_id)
    if raw is None:
        raise NotFoundError
    stored = StoredDocument.model_validate_json(raw)
    return DocumentDetail(
        document_id=stored.document_id,
        kind=stored.kind,
        layout=stored.layout,
        ocr_used=stored.ocr_used,
        text=stored.text,
        resume=stored.resume,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str, session: ActiveSessionDep, manager: SessionManagerDep
) -> Response:
    await manager.delete_object(session, "document", document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
