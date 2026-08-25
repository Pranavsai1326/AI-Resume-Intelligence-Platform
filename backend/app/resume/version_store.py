"""Session-storage access for resume versions.

Shared by the resume-versions API (which lists/creates versions directly) and the tailoring API
(which creates a version as the result of applying accepted proposals) - both need the exact same
"save a version, then append it to its document's index" operation.
"""

from __future__ import annotations

import json

from app.core.errors import NotFoundError, ValidationFailedError
from app.documents.storage import StoredDocument
from app.resume.versions import ResumeVersion, VersionSource, new_version_id
from app.sessions.manager import SessionManager
from app.sessions.models import SessionMeta

VERSION_TTL_SECONDS = 3600


async def _load_index(manager: SessionManager, session: SessionMeta, document_id: str) -> list[str]:
    raw = await manager.get_object(session, "resume_version_index", document_id)
    return list(json.loads(raw)) if raw else []


async def _save_index(
    manager: SessionManager, session: SessionMeta, document_id: str, version_ids: list[str]
) -> None:
    await manager.put_object(
        session,
        "resume_version_index",
        document_id,
        json.dumps(version_ids),
        ttl_seconds=VERSION_TTL_SECONDS,
    )


async def save_version(
    manager: SessionManager, session: SessionMeta, version: ResumeVersion
) -> None:
    await manager.put_object(
        session,
        "resume_version",
        version.version_id,
        version.model_dump_json(),
        ttl_seconds=VERSION_TTL_SECONDS,
    )


async def add_version(
    manager: SessionManager, session: SessionMeta, version: ResumeVersion
) -> None:
    """Save a version and append it to its document's index in one step."""
    await save_version(manager, session, version)
    version_ids = await _load_index(manager, session, version.document_id)
    version_ids.append(version.version_id)
    await _save_index(manager, session, version.document_id, version_ids)


async def get_version(
    manager: SessionManager, session: SessionMeta, version_id: str
) -> ResumeVersion | None:
    raw = await manager.get_object(session, "resume_version", version_id)
    return ResumeVersion.model_validate_json(raw) if raw else None


async def list_versions(
    manager: SessionManager, session: SessionMeta, document_id: str
) -> list[ResumeVersion]:
    """Every version for ``document_id``, creating "Original" on first access."""
    version_ids = await _load_index(manager, session, document_id)
    if version_ids:
        versions = [
            v
            for version_id in version_ids
            if (v := await get_version(manager, session, version_id)) is not None
        ]
        if versions:
            return versions

    document_raw = await manager.get_object(session, "document", document_id)
    if document_raw is None:
        raise NotFoundError("No document with that id exists in this session.")
    stored = StoredDocument.model_validate_json(document_raw)
    if stored.resume is None:
        raise ValidationFailedError("This document has no structured resume to build from.")

    from datetime import UTC, datetime

    original = ResumeVersion(
        version_id=new_version_id(),
        document_id=document_id,
        label="Original",
        source=VersionSource.ORIGINAL,
        resume=stored.resume,
        created_at=datetime.now(UTC),
    )
    await add_version(manager, session, original)
    return [original]


async def get_version_or_original(
    manager: SessionManager, session: SessionMeta, document_id: str, version_id: str | None
) -> ResumeVersion:
    if version_id:
        version = await get_version(manager, session, version_id)
        if version is None:
            raise NotFoundError("No version with that id exists in this session.")
        return version
    versions = await list_versions(manager, session, document_id)
    return versions[0]
