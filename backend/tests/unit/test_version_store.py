"""Unit tests for app.resume.version_store."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.errors import NotFoundError, ValidationFailedError
from app.documents.extract.base import LayoutSignals
from app.documents.storage import StoredDocument
from app.documents.upload import DocumentKind
from app.resume.version_store import (
    add_version,
    get_version,
    get_version_or_original,
    list_versions,
)
from app.resume.versions import ResumeVersion, VersionSource, new_version_id
from app.sessions.manager import SessionManager
from app.sessions.models import SessionMeta, SessionMode
from tests.fixtures import make_resume


async def _store_document(
    manager: SessionManager, session: SessionMeta, document_id: str = "doc1"
) -> None:
    stored = StoredDocument(
        document_id=document_id,
        kind=DocumentKind.TXT,
        layout=LayoutSignals(),
        ocr_used=False,
        text="synthetic resume text",
        resume=make_resume(),
    )
    await manager.put_object(session, "document", document_id, stored.model_dump_json())


async def test_add_and_get_version_round_trips(manager: SessionManager) -> None:
    session = await manager.create(SessionMode.CANDIDATE)
    version = ResumeVersion(
        version_id=new_version_id(),
        document_id="doc1",
        label="Manual edit",
        source=VersionSource.MANUAL_EDIT,
        resume=make_resume(),
        created_at=datetime.now(UTC),
    )
    await add_version(manager, session, version)

    fetched = await get_version(manager, session, version.version_id)
    assert fetched is not None
    assert fetched.version_id == version.version_id
    assert fetched.label == "Manual edit"


async def test_get_version_unknown_id_returns_none(manager: SessionManager) -> None:
    session = await manager.create(SessionMode.CANDIDATE)
    assert await get_version(manager, session, "does-not-exist") is None


async def test_list_versions_lazily_creates_original(manager: SessionManager) -> None:
    session = await manager.create(SessionMode.CANDIDATE)
    await _store_document(manager, session)

    versions = await list_versions(manager, session, "doc1")
    assert len(versions) == 1
    assert versions[0].label == "Original"
    assert versions[0].source == VersionSource.ORIGINAL

    # Second call must not create a second "Original".
    versions_again = await list_versions(manager, session, "doc1")
    assert len(versions_again) == 1
    assert versions_again[0].version_id == versions[0].version_id


async def test_list_versions_unknown_document_raises_not_found(manager: SessionManager) -> None:
    session = await manager.create(SessionMode.CANDIDATE)
    with pytest.raises(NotFoundError):
        await list_versions(manager, session, "no-such-doc")


async def test_list_versions_document_without_resume_raises_validation_error(
    manager: SessionManager,
) -> None:
    session = await manager.create(SessionMode.CANDIDATE)
    stored = StoredDocument(
        document_id="doc2",
        kind=DocumentKind.TXT,
        layout=LayoutSignals(),
        ocr_used=False,
        text="a job description, not a resume",
        resume=None,
    )
    await manager.put_object(session, "document", "doc2", stored.model_dump_json())

    with pytest.raises(ValidationFailedError):
        await list_versions(manager, session, "doc2")


async def test_get_version_or_original_with_explicit_id(manager: SessionManager) -> None:
    session = await manager.create(SessionMode.CANDIDATE)
    await _store_document(manager, session)
    versions = await list_versions(manager, session, "doc1")
    original = versions[0]

    resolved = await get_version_or_original(manager, session, "doc1", original.version_id)
    assert resolved.version_id == original.version_id


async def test_get_version_or_original_with_none_returns_first_version(
    manager: SessionManager,
) -> None:
    session = await manager.create(SessionMode.CANDIDATE)
    await _store_document(manager, session)

    resolved = await get_version_or_original(manager, session, "doc1", None)
    assert resolved.label == "Original"


async def test_get_version_or_original_unknown_id_raises_not_found(
    manager: SessionManager,
) -> None:
    session = await manager.create(SessionMode.CANDIDATE)
    await _store_document(manager, session)
    with pytest.raises(NotFoundError):
        await get_version_or_original(manager, session, "doc1", "bogus-version-id")


async def test_add_version_appends_to_index_across_multiple_saves(
    manager: SessionManager,
) -> None:
    session = await manager.create(SessionMode.CANDIDATE)
    await _store_document(manager, session)
    original = (await list_versions(manager, session, "doc1"))[0]

    second = ResumeVersion(
        version_id=new_version_id(),
        document_id="doc1",
        label="Edit 2",
        source=VersionSource.MANUAL_EDIT,
        resume=make_resume(),
        created_at=datetime.now(UTC),
        based_on_version_id=original.version_id,
    )
    await add_version(manager, session, second)

    all_versions = await list_versions(manager, session, "doc1")
    assert {v.version_id for v in all_versions} == {original.version_id, second.version_id}
