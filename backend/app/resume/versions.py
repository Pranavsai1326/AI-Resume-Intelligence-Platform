"""In-session resume versions (PRD section 19).

Every meaningful edit - a manual save, an accepted tailoring proposal - becomes a new, immutable
version rather than mutating one in place, so a before/after comparison and a return to an
earlier version are always possible within the session. Versions disappear with the session;
there is no cross-session history (PRIVACY_ARCHITECTURE.md).
"""

from __future__ import annotations

import secrets
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.resume.models import Resume


class VersionSource(StrEnum):
    #: The structured resume exactly as extracted from the uploaded document.
    ORIGINAL = "original"
    #: Saved by the user editing fields directly.
    MANUAL_EDIT = "manual_edit"
    #: Produced by accepting one or more AI tailoring proposals.
    AI_TAILORED = "ai_tailored"


class ResumeVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: str
    document_id: str
    label: str
    source: VersionSource
    resume: Resume
    created_at: datetime
    #: The version this one was derived from, if any - lets the UI show lineage.
    based_on_version_id: str | None = None


class VersionSummary(BaseModel):
    """The list view - no resume content, so listing versions never re-sends a full resume."""

    model_config = ConfigDict(extra="forbid")

    version_id: str
    label: str
    source: VersionSource
    created_at: datetime
    based_on_version_id: str | None = None

    @staticmethod
    def from_version(version: ResumeVersion) -> VersionSummary:
        return VersionSummary(
            version_id=version.version_id,
            label=version.label,
            source=version.source,
            created_at=version.created_at,
            based_on_version_id=version.based_on_version_id,
        )


def new_version_id() -> str:
    return secrets.token_hex(10)
