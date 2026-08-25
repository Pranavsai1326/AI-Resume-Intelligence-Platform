"""Resume version endpoints (PRD section 19).

Versions are immutable snapshots: every save creates a new one rather than mutating an existing
one in place, so a before/after comparison across edits is always available within the session.
The first version for a document ("Original") is created lazily from the document's extracted
resume the first time its versions are listed or fetched, rather than at upload time - most
uploads are only ever analyzed, never opened in the builder, so creating a version eagerly for
every upload would be wasted session storage for the common case.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, model_validator

from app.core.deps import ActiveSessionDep, SessionManagerDep
from app.core.errors import NotFoundError
from app.logging import get_logger
from app.resume.models import Resume
from app.resume.version_store import (
    add_version,
    get_version,
    list_versions,
)
from app.resume.versions import ResumeVersion, VersionSource, VersionSummary, new_version_id

logger = get_logger(__name__)
router = APIRouter(prefix="/resume", tags=["resume"])


class CreateVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    label: str
    resume: Resume | None = None
    based_on_version_id: str | None = None
    source: VersionSource = VersionSource.MANUAL_EDIT

    @model_validator(mode="after")
    def _resume_or_base(self) -> CreateVersionRequest:
        if self.resume is None and self.based_on_version_id is None:
            raise ValueError("provide either 'resume' or 'based_on_version_id'")
        return self


@router.get("/versions", response_model=list[VersionSummary])
async def list_versions_endpoint(
    document_id: str, session: ActiveSessionDep, manager: SessionManagerDep
) -> list[VersionSummary]:
    versions = await list_versions(manager, session, document_id)
    return [VersionSummary.from_version(v) for v in versions]


@router.post("/versions", status_code=status.HTTP_201_CREATED, response_model=ResumeVersion)
async def create_version(
    payload: CreateVersionRequest, session: ActiveSessionDep, manager: SessionManagerDep
) -> ResumeVersion:
    await list_versions(manager, session, payload.document_id)  # ensures "Original" exists

    if payload.resume is not None:
        resume = payload.resume
    else:
        base = await get_version(manager, session, payload.based_on_version_id)  # type: ignore[arg-type]
        if base is None:
            raise NotFoundError("No version with that id exists in this session.")
        resume = base.resume

    version = ResumeVersion(
        version_id=new_version_id(),
        document_id=payload.document_id,
        label=payload.label,
        source=payload.source,
        resume=resume,
        created_at=datetime.now(UTC),
        based_on_version_id=payload.based_on_version_id,
    )
    await add_version(manager, session, version)

    logger.info("resume_version.created", source=version.source.value)
    return version


@router.get("/versions/{version_id}", response_model=ResumeVersion)
async def get_version_endpoint(
    version_id: str, session: ActiveSessionDep, manager: SessionManagerDep
) -> ResumeVersion:
    version = await get_version(manager, session, version_id)
    if version is None:
        raise NotFoundError
    return version
