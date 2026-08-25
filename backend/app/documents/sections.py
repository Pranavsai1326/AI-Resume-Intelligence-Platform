"""Section detection over plain resume text.

Deterministic heuristics (AI_ARCHITECTURE.md Layer 1), not an LLM: a line is recognised as a
section header either by matching a canonical keyword ("Work Experience", "Employment History",
...) or by looking structurally like a header (short, title-case or all-caps, no trailing
punctuation). Neither test is perfect - resumes are not standardised documents - so this is
documented as a heuristic and every detected section keeps its original header text, letting a
misclassified section still be inspected rather than silently discarded.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


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

#: A candidate header line: short, letters/spaces/basic punctuation only, no sentence-ending
#: punctuation. Deliberately conservative - a false negative just falls into the previous
#: section's body, which is recoverable; a false positive fragments real content.
_HEADER_SHAPE_RE = re.compile(r"^[A-Za-z][A-Za-z\s&/,'\-]{1,45}$")
_TRAILING_PUNCTUATION_RE = re.compile(r"[:\-–—]+$")


def _normalize_header(line: str) -> str:
    return _TRAILING_PUNCTUATION_RE.sub("", line.strip()).strip().lower()


def _looks_like_header(line: str) -> bool:
    """Fallback detector for a custom section header not in the known-keyword list.

    Deliberately narrow: ALL-CAPS only. A title-case shape test was tried and rejected - it
    matched ordinary content lines just as readily as headers (a person's name, "Senior Backend
    Engineer, Cascade Systems"), fragmenting the contact block and experience entries into bogus
    sections. Known headers in any casing ("Experience", "SKILLS", "Education") are still caught
    by the keyword table above regardless of this function; this path exists only for a header
    like "AWARDS" or "PUBLICATIONS" that is not in that table. A custom header written in
    ordinary title case (rare) is missed and its content simply stays part of the previous
    section - a safe failure mode, unlike corrupting the sections around it.
    """
    stripped = line.strip()
    if not (3 <= len(stripped) <= 45):
        return False
    if not _HEADER_SHAPE_RE.match(stripped):
        return False
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) < 3:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio > 0.85


def detect_sections(text: str) -> list[DetectedSection]:
    lines = text.split("\n")
    headers: list[tuple[int, SectionKind, str]] = []

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        normalized = _normalize_header(stripped)
        if normalized in _HEADER_KEYWORDS:
            headers.append((index, _HEADER_KEYWORDS[normalized], stripped))
        elif _looks_like_header(stripped):
            headers.append((index, SectionKind.CUSTOM, stripped))

    sections: list[DetectedSection] = []

    preamble_end = headers[0][0] if headers else len(lines)
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

    for position, (line_index, kind, title) in enumerate(headers):
        body_start = line_index + 1
        body_end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        body = "\n".join(lines[body_start:body_end]).strip()
        sections.append(
            DetectedSection(
                kind=kind, title=title, body=body, start_line=line_index, end_line=body_end
            )
        )

    return sections
