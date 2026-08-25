"""Screening domain models: a context (one job, many candidates), one result per candidate."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.matching.models import JobMatchResult
from app.queue.base import JobState
from app.resume.models import Resume


class RedactionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applied: bool
    #: Categories actually found and removed - never lists a category that found nothing
    #: (PRD section 8, SECURITY.md section 10).
    fields: list[str] = Field(default_factory=list)


class ScreeningContext(BaseModel):
    """One recruiter screening run: a job plus the candidate ids enqueued against it."""

    model_config = ConfigDict(extra="forbid")

    screening_id: str
    job_id: str
    created_at: datetime
    candidate_ids: list[str] = Field(default_factory=list)


class CandidateStatus(BaseModel):
    """Poll-friendly per-candidate progress - no resume content, just state."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    state: JobState
    error: str | None = None


class CandidateResult(BaseModel):
    """One candidate's outcome: the redacted resume, its match score, and shortlist status.

    ``resume`` is always the *redacted* copy - the only version ever stored, so there is no
    unredacted candidate resume anywhere in the session for a ranking/comparison view to
    accidentally surface (blind-review by construction, not by a display-time filter).
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    match: JobMatchResult
    redaction: RedactionInfo
    resume: Resume
    shortlisted: bool = False


class ScreeningStatusSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screening_id: str
    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    candidates: list[CandidateStatus]
