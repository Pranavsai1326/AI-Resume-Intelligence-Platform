"""Section detection over plain resume text.

Deterministic heuristics (AI_ARCHITECTURE.md Layer 1), not an LLM: a line is recognised as a
section header either by matching a canonical keyword ("Work Experience", "Employment History",
...) or by looking structurally like a header (see
``app.documents.heading_split.looks_like_all_caps_header``). Neither test is perfect - resumes
are not standardised documents - so this is documented as a heuristic and every detected section
keeps its original header text, letting a misclassified section still be inspected rather than
silently discarded.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.documents.heading_split import find_headers, slice_bodies


class SectionKind(StrEnum):
    #: Text before the first recognised header - usually name, contact details, links.
    CONTACT = "contact"
    SUMMARY = "summary"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    PROJECTS = "projects"
    CERTIFICATIONS = "certifications"
    #: A header that looks structurally like one but matches no known keyword (e.g. "Awards").
    CUSTOM = "custom"


class DetectedSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SectionKind
    #: The header exactly as written in the document (or "Contact" for the preamble).
    title: str
    body: str
    start_line: int
    end_line: int


_HEADER_KEYWORDS: dict[str, SectionKind] = {
    "summary": SectionKind.SUMMARY,
    "professional summary": SectionKind.SUMMARY,
    "career summary": SectionKind.SUMMARY,
    "objective": SectionKind.SUMMARY,
    "career objective": SectionKind.SUMMARY,
    "profile": SectionKind.SUMMARY,
    "about": SectionKind.SUMMARY,
    "about me": SectionKind.SUMMARY,
    "experience": SectionKind.EXPERIENCE,
    "work experience": SectionKind.EXPERIENCE,
    "professional experience": SectionKind.EXPERIENCE,
    "employment history": SectionKind.EXPERIENCE,
    "work history": SectionKind.EXPERIENCE,
    "career history": SectionKind.EXPERIENCE,
    "relevant experience": SectionKind.EXPERIENCE,
    "education": SectionKind.EDUCATION,
    "education & training": SectionKind.EDUCATION,
    "academic background": SectionKind.EDUCATION,
    "academic qualifications": SectionKind.EDUCATION,
    "skills": SectionKind.SKILLS,
    "technical skills": SectionKind.SKILLS,
    "core competencies": SectionKind.SKILLS,
    "skills & tools": SectionKind.SKILLS,
    "key skills": SectionKind.SKILLS,
    "projects": SectionKind.PROJECTS,
    "personal projects": SectionKind.PROJECTS,
    "academic projects": SectionKind.PROJECTS,
    "selected projects": SectionKind.PROJECTS,
    "certifications": SectionKind.CERTIFICATIONS,
    "certificates": SectionKind.CERTIFICATIONS,
    "licenses": SectionKind.CERTIFICATIONS,
    "licenses & certifications": SectionKind.CERTIFICATIONS,
    "certifications & licenses": SectionKind.CERTIFICATIONS,
}


def detect_sections(text: str) -> list[DetectedSection]:
    lines = text.split("\n")
    headers = find_headers(lines, _HEADER_KEYWORDS, fallback_kind=SectionKind.CUSTOM)

    sections: list[DetectedSection] = []

    preamble_end = headers[0].line_index if headers else len(lines)
    if preamble_end > 0:
        preamble = "\n".join(lines[:preamble_end]).strip()
        if preamble:
            sections.append(
                DetectedSection(
                    kind=SectionKind.CONTACT,
                    title="Contact",
                    body=preamble,
                    start_line=0,
                    end_line=preamble_end,
                )
            )

    for position, (header, body) in enumerate(slice_bodies(lines, headers)):
        body_end = (
            headers[position + 1].line_index if position + 1 < len(headers) else len(lines)
        )
        sections.append(
            DetectedSection(
                kind=header.kind,
                title=header.title,
                body=body,
                start_line=header.line_index,
                end_line=body_end,
            )
        )

    return sections
