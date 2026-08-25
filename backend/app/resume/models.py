"""Structured resume model.

Deliberately plain data: every entry here comes from deterministic extraction (Layer 1 of
AI_ARCHITECTURE.md), never from an LLM. Scalars and list entries that can plausibly come from
different places in the document (or be user-edited independently) each carry their own
:class:`~app.resume.provenance.ProvenancedValue`, so provenance survives at the granularity edits
actually happen at.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.resume.provenance import ProvenancedValue


class ContactInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: ProvenancedValue[str] | None = None
    email: ProvenancedValue[str] | None = None
    phone: ProvenancedValue[str] | None = None
    location: ProvenancedValue[str] | None = None
    links: list[ProvenancedValue[str]] = Field(default_factory=list)


class DateRange(BaseModel):
    """A period of time as it appeared in the document, plus a best-effort normalisation.

    ``raw`` is always populated - it is exactly what the resume said. ``start`` / ``end`` are
    filled in only when the text confidently parses as a date; a resume with an unusual date
    format is not silently reinterpreted, and downstream code must treat ``None`` as "unknown",
    not "the entry started at time zero".
    """

    model_config = ConfigDict(extra="forbid")

    raw: str
    #: ISO 8601 year-month, e.g. "2021-03". Only ever the first day of the month by convention.
    start: str | None = None
    end: str | None = None
    is_current: bool = False


class ExperienceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    organization: str
    location: str | None = None
    dates: DateRange | None = None
    bullets: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    location: str | None = None
    dates: DateRange | None = None
    details: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    dates: DateRange | None = None


class CertificationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    issuer: str | None = None
    date: str | None = None


class SkillGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: e.g. "Languages", "Tools". None for a flat, uncategorised skills section.
    category: str | None = None
    skills: list[str] = Field(default_factory=list)


class CustomSection(BaseModel):
    """A section that does not fit the standard categories (e.g. "Publications", "Awards").

    Kept verbatim rather than forced into one of the typed sections above, so extraction never
    silently drops or mis-files content it does not recognise.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    bullets: list[str] = Field(default_factory=list)


class Resume(BaseModel):
    """The full structured resume for one session."""

    model_config = ConfigDict(extra="forbid")

    contact: ContactInfo = Field(default_factory=ContactInfo)
    summary: ProvenancedValue[str] | None = None
    experience: list[ProvenancedValue[ExperienceEntry]] = Field(default_factory=list)
    education: list[ProvenancedValue[EducationEntry]] = Field(default_factory=list)
    skills: list[ProvenancedValue[SkillGroup]] = Field(default_factory=list)
    projects: list[ProvenancedValue[ProjectEntry]] = Field(default_factory=list)
    certifications: list[ProvenancedValue[CertificationEntry]] = Field(default_factory=list)
    custom_sections: list[ProvenancedValue[CustomSection]] = Field(default_factory=list)
