"""Unit tests for app.resume.versions."""

from __future__ import annotations

from datetime import UTC, datetime

from app.resume.versions import ResumeVersion, VersionSource, VersionSummary, new_version_id
from tests.fixtures import make_resume


def test_new_version_id_is_unique_and_url_safe() -> None:
    ids = {new_version_id() for _ in range(50)}
    assert len(ids) == 50
    for version_id in ids:
        assert version_id.isalnum()


def test_version_summary_from_version_omits_resume_content() -> None:
    version = ResumeVersion(
        version_id="v1",
        document_id="d1",
        label="Original",
        source=VersionSource.ORIGINAL,
        resume=make_resume(),
        created_at=datetime.now(UTC),
    )
    summary = VersionSummary.from_version(version)
    assert summary.version_id == "v1"
    assert summary.label == "Original"
    assert summary.source == VersionSource.ORIGINAL
    assert summary.based_on_version_id is None
    assert "resume" not in summary.model_dump()


def test_version_summary_preserves_lineage() -> None:
    version = ResumeVersion(
        version_id="v2",
        document_id="d1",
        label="Tailored",
        source=VersionSource.AI_TAILORED,
        resume=make_resume(),
        created_at=datetime.now(UTC),
        based_on_version_id="v1",
    )
    summary = VersionSummary.from_version(version)
    assert summary.based_on_version_id == "v1"


def test_version_source_enum_values() -> None:
    assert VersionSource.ORIGINAL.value == "original"
    assert VersionSource.MANUAL_EDIT.value == "manual_edit"
    assert VersionSource.AI_TAILORED.value == "ai_tailored"
