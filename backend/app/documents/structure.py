"""Build a structured, provenance-tagged Resume from extracted text.

Entirely deterministic - regex and heuristics, Layer 1 of AI_ARCHITECTURE.md, never an LLM. The
confidence attached to each extracted value reflects how mechanical the parsing step was: a
regex-matched email is 0.95; a block of text tentatively split into "job title" and "company" by
punctuation position is 0.6. These are honest calibration choices, documented inline, not
decorative numbers - a low-confidence field is exactly the kind of thing the resume builder (a
later phase) should invite the user to double-check rather than trust silently.
"""

from __future__ import annotations

import re

from app.documents.sections import DetectedSection, SectionKind, detect_sections
from app.resume.models import (
    CertificationEntry,
    ContactInfo,
    CustomSection,
    DateRange,
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    Resume,
    SkillGroup,
)
from app.resume.provenance import Provenance, ProvenancedValue

# -- contact -----------------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}")
_URL_RE = re.compile(
    r"(https?://\S+|(?:www\.)?linkedin\.com/\S+|(?:www\.)?github\.com/\S+)", re.IGNORECASE
)
_LOCATION_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]+,\s*[A-Za-z]{2,}(?:\s+\d{4,6})?$")


def _parse_contact(text: str) -> ContactInfo:
    contact = ContactInfo()
    if not text.strip():
        return contact

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    email_match = _EMAIL_RE.search(text)
    if email_match:
        contact.email = ProvenancedValue(
            value=email_match.group(0), provenance=Provenance.extracted(0.95)
        )

    phone_match = _PHONE_RE.search(text)
    if phone_match and sum(c.isdigit() for c in phone_match.group(0)) >= 7:
        contact.phone = ProvenancedValue(
            value=phone_match.group(0).strip(), provenance=Provenance.extracted(0.85)
        )

    contact.links = [
        ProvenancedValue(value=match.group(0).rstrip(".,"), provenance=Provenance.extracted(0.9))
        for match in _URL_RE.finditer(text)
    ]

    # Name and location are read only from the first few lines: a resume's header block, not
    # its body, is where these plausibly live.
    for line in lines[:3]:
        if _EMAIL_RE.search(line) or _URL_RE.search(line):
            continue
        digit_ratio = sum(c.isdigit() for c in line) / max(1, len(line))
        if digit_ratio > 0.3:
            continue
        words = line.split()
        if contact.full_name is None and 1 <= len(words) <= 5:
            contact.full_name = ProvenancedValue(value=line, provenance=Provenance.extracted(0.6))
            continue
        if contact.location is None and _LOCATION_RE.match(line):
            contact.location = ProvenancedValue(value=line, provenance=Provenance.extracted(0.55))

    return contact


# -- dates ---------------------------------------------------------------------------------------

_MONTH_ORDER = (
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
)
_MONTH_TO_NUMBER = {name: f"{i + 1:02d}" for i, name in enumerate(_MONTH_ORDER)}
_MONTH_NAMES_RE = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_DATE_TOKEN_RE = rf"(?:(?:{_MONTH_NAMES_RE})\.?\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
_DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN_RE})\s*(?:-|–|—|to)\s*(?P<end>{_DATE_TOKEN_RE}|present|current)",
    re.IGNORECASE,
)


def _normalize_date_token(token: str) -> str:
    token = token.strip()
    month_match = re.match(rf"({_MONTH_NAMES_RE})\.?\s+(\d{{4}})", token, re.IGNORECASE)
    if month_match:
        key = month_match.group(1)[:3].lower()
        return f"{month_match.group(2)}-{_MONTH_TO_NUMBER[key]}"
    slash_match = re.match(r"(\d{1,2})/(\d{4})", token)
    if slash_match:
        return f"{slash_match.group(2)}-{int(slash_match.group(1)):02d}"
    return token  # bare "YYYY", already in its final form


def parse_date_range(text: str) -> DateRange | None:
    """Find the first date range in ``text``, if any.

    ``start`` / ``end`` are ISO year-month when the source gave a month, or a bare year when it
    did not - a bare year is never padded to a fabricated month.
    """
    match = _DATE_RANGE_RE.search(text)
    if not match:
        return None
    end_token = match.group("end")
    is_current = end_token.lower() in {"present", "current"}
    return DateRange(
        raw=match.group(0),
        start=_normalize_date_token(match.group("start")),
        end=None if is_current else _normalize_date_token(end_token),
        is_current=is_current,
    )


# -- shared block parsing --------------------------------------------------------------------

_BULLET_PREFIX_RE = re.compile(r"^[\-•\*●▪]\s*")
_HEADER_SPLIT_RE = re.compile(r"\s*[|,–—]\s*|\s+-\s+| at | @ ")


def _blocks(body: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]


def _split_entries(body: str) -> list[str]:
    """Split a section's body into per-entry blocks.

    Blank lines are the primary separator - reliable for DOCX and TXT, where a paragraph break
    survives as a literal empty line. PDF text extraction does not: pdfplumber infers line breaks
    from vertical position, and a visually blank line between two entries commonly collapses to a
    single newline in the extracted text, leaving an entire section as one blank-line block. When
    that happens, a secondary heuristic re-splits it: a plain, non-bulleted line that follows at
    least one bulleted line is treated as the start of a new entry - the shape of "title/org, then
    bullets, then the next title/org" holds whether or not blank lines survived.
    """
    blank_split = _blocks(body)
    if len(blank_split) != 1:
        return blank_split

    lines = [line for line in blank_split[0].split("\n") if line.strip()]
    if not lines:
        return []

    entries: list[list[str]] = [[lines[0]]]
    seen_bullet_in_current = False
    for line in lines[1:]:
        is_bullet = bool(_BULLET_PREFIX_RE.match(line.strip()))
        if not is_bullet and seen_bullet_in_current:
            entries.append([line])
            seen_bullet_in_current = False
            continue
        entries[-1].append(line)
        if is_bullet:
            seen_bullet_in_current = True

    return ["\n".join(entry) for entry in entries]


def _clean_bullet(line: str) -> str:
    return _BULLET_PREFIX_RE.sub("", line.strip()).strip()


def _split_two(remainder: str) -> tuple[str, str]:
    parts = [part.strip() for part in _HEADER_SPLIT_RE.split(remainder) if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if parts:
        return parts[0], ""
    return remainder.strip(), ""


def _strip_dates(header: str, dates: DateRange | None) -> str:
    if dates is None:
        return header
    return header.replace(dates.raw, "").strip(" -|,–—")


def _split_header_and_dates(lines: list[str]) -> tuple[str, DateRange | None, list[str]]:
    """Pull the header line and an optional date range out of a block's lines.

    Handles both common layouts: dates on the same line as the title ("Title, Org  Jan 2021 -
    Present") and dates on their own line directly beneath it ("Title, Org" / newline /
    "Jan 2021 - Present"). A second line counts as a date line only when the date match covers
    most of it, so a bullet that merely mentions a year in passing is never mistaken for the
    entry's date range.
    """
    header = lines[0]
    rest = lines[1:]
    dates = parse_date_range(header)
    if dates is None and rest:
        candidate = rest[0].strip()
        candidate_dates = parse_date_range(candidate)
        if candidate_dates is not None and len(candidate_dates.raw) >= 0.6 * len(candidate):
            dates = candidate_dates
            rest = rest[1:]
    return header, dates, rest


# -- experience / education / projects ---------------------------------------------------------


def _parse_experience(body: str) -> list[ProvenancedValue[ExperienceEntry]]:
    entries: list[ProvenancedValue[ExperienceEntry]] = []
    for block in _split_entries(body):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        header, dates, rest = _split_header_and_dates(lines)
        remainder = _strip_dates(header, dates)
        title, organization = _split_two(remainder)
        bullets = [b for line in rest if (b := _clean_bullet(line))]
        entry = ExperienceEntry(
            title=title or remainder, organization=organization, dates=dates, bullets=bullets
        )
        entries.append(ProvenancedValue(value=entry, provenance=Provenance.extracted(0.6)))
    return entries


_DEGREE_KEYWORDS_RE = re.compile(
    r"\b(bachelor|master|associate|doctorate|ph\.?d\.?|mba|b\.?s\.?|m\.?s\.?|b\.?a\.?|m\.?a\.?|"
    r"diploma|certificate)\b",
    re.IGNORECASE,
)


def _split_education_entries(body: str) -> list[str]:
    """``_split_entries``, with a fallback anchor for education's usual bullet-free shape.

    Education entries rarely have bullets, so ``_split_entries``'s bullet-based fallback (used
    when a PDF's extracted text collapses the blank line between entries) has nothing to anchor
    on - two entries in a row silently merge into one. A degree line ("B.S. Computer Science,
    2015") is education's equivalent of a bullet: it reliably closes out the entry it belongs to,
    so a following non-degree line (the next entry's institution name) can be treated as a new
    entry's start the same way a non-bulleted line after a bullet already is.
    """
    blocks = _split_entries(body)
    if len(blocks) != 1:
        return blocks

    lines = [line for line in blocks[0].split("\n") if line.strip()]
    if len(lines) < 2:
        return blocks

    def is_date_only(line: str) -> bool:
        # A line that is essentially just a date range ("2014 - 2018") belongs to the entry
        # above it, never a new one - the same "date line beneath the header" shape
        # `_split_header_and_dates` already recognises for experience entries.
        date_match = parse_date_range(line)
        return date_match is not None and len(date_match.raw) >= 0.6 * len(line.strip())

    entries: list[list[str]] = [[lines[0]]]
    #: The current entry already has its degree line - it is complete once it has also
    #: consumed (or skipped) an optional date-only line right after it.
    entry_has_degree = bool(_DEGREE_KEYWORDS_RE.search(lines[0]))
    awaiting_optional_date = entry_has_degree

    for line in lines[1:]:
        is_degree_line = bool(_DEGREE_KEYWORDS_RE.search(line))

        if awaiting_optional_date and is_date_only(line):
            entries[-1].append(line)
            awaiting_optional_date = False
            continue

        if entry_has_degree:
            # The current entry is already complete (degree seen, date consumed or skipped) -
            # any further line, including one that is itself a new degree/header line, starts
            # the next entry.
            entries.append([line])
            entry_has_degree = is_degree_line
            awaiting_optional_date = is_degree_line
            continue

        entries[-1].append(line)
        if is_degree_line:
            entry_has_degree = True
            awaiting_optional_date = True

    return ["\n".join(entry) for entry in entries]


def _parse_education(body: str) -> list[ProvenancedValue[EducationEntry]]:
    entries: list[ProvenancedValue[EducationEntry]] = []
    for block in _split_education_entries(body):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        header, dates, rest = _split_header_and_dates(lines)
        remainder = _strip_dates(header, dates)
        institution, degree = _split_two(remainder)
        details = [d for line in rest if (d := _clean_bullet(line))]
        entry = EducationEntry(
            institution=institution or remainder,
            degree=degree or None,
            dates=dates,
            details=details,
        )
        entries.append(ProvenancedValue(value=entry, provenance=Provenance.extracted(0.6)))
    return entries


_TRAILING_PARENS_RE = re.compile(r"\(([^)]+)\)\s*$")


def _parse_projects(body: str) -> list[ProvenancedValue[ProjectEntry]]:
    entries: list[ProvenancedValue[ProjectEntry]] = []
    for block in _split_entries(body):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        header, dates, rest = _split_header_and_dates(lines)
        remainder = _strip_dates(header, dates)

        technologies: list[str] = []
        tech_match = _TRAILING_PARENS_RE.search(remainder)
        if tech_match:
            technologies = [t.strip() for t in tech_match.group(1).split(",") if t.strip()]
            remainder = remainder[: tech_match.start()].strip(" -|,–—")

        name, _ = _split_two(remainder)
        bullets = [b for line in rest if (b := _clean_bullet(line))]
        entry = ProjectEntry(
            name=name or remainder,
            description=bullets[0] if len(bullets) == 1 else None,
            bullets=bullets if len(bullets) != 1 else [],
            technologies=technologies,
            dates=dates,
        )
        entries.append(ProvenancedValue(value=entry, provenance=Provenance.extracted(0.55)))
    return entries


_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_CERT_SPLIT_RE = re.compile(r"\s*[|,–—]\s*|\s+-\s+")


def _parse_certifications(body: str) -> list[ProvenancedValue[CertificationEntry]]:
    entries: list[ProvenancedValue[CertificationEntry]] = []
    for raw_line in body.split("\n"):
        line = _clean_bullet(raw_line)
        if not line:
            continue
        year_match = _YEAR_RE.search(line)
        date = year_match.group(0) if year_match else None
        parts = [p for p in _CERT_SPLIT_RE.split(line) if p and p != date]
        name = parts[0] if parts else line
        issuer = parts[1] if len(parts) > 1 else None
        entry = CertificationEntry(name=name, issuer=issuer, date=date)
        entries.append(ProvenancedValue(value=entry, provenance=Provenance.extracted(0.55)))
    return entries


_SKILL_SPLIT_RE = re.compile(r"[,;•|]")


def _parse_skills(body: str) -> list[ProvenancedValue[SkillGroup]]:
    groups: list[ProvenancedValue[SkillGroup]] = []
    categorized = False

    for line in (line.strip() for line in body.split("\n") if line.strip()):
        if ":" in line and len(line.split(":", 1)[0].split()) <= 4:
            category, rest = line.split(":", 1)
            skills = [s.strip() for s in _SKILL_SPLIT_RE.split(rest) if s.strip()]
            if skills:
                group = SkillGroup(category=category.strip(), skills=skills)
                groups.append(ProvenancedValue(value=group, provenance=Provenance.extracted(0.75)))
                categorized = True

    if not categorized:
        skills = [s.strip() for s in _SKILL_SPLIT_RE.split(body.replace("\n", ",")) if s.strip()]
        if skills:
            group = SkillGroup(category=None, skills=skills)
            groups.append(ProvenancedValue(value=group, provenance=Provenance.extracted(0.7)))

    return groups


def _parse_custom(section: DetectedSection) -> ProvenancedValue[CustomSection] | None:
    bullets = [b for line in section.body.split("\n") if (b := _clean_bullet(line))]
    if not bullets:
        return None
    custom = CustomSection(title=section.title, bullets=bullets)
    return ProvenancedValue(value=custom, provenance=Provenance.extracted(0.5))


# -- top level -------------------------------------------------------------------------------


def build_resume(text: str) -> Resume:
    """Turn extracted plain text into a structured, provenance-tagged Resume.

    Every populated field carries ``ProvenanceKind.EXTRACTED`` with a confidence reflecting how
    mechanical its parsing step was. Nothing here invents content that is not in ``text``.
    """
    sections = detect_sections(text)
    resume = Resume()

    contact_section = next((s for s in sections if s.kind == SectionKind.CONTACT), None)
    if contact_section is not None:
        resume.contact = _parse_contact(contact_section.body)

    for section in sections:
        if section.kind == SectionKind.CONTACT:
            continue
        if section.kind == SectionKind.SUMMARY:
            if section.body.strip():
                resume.summary = ProvenancedValue(
                    value=section.body.strip(), provenance=Provenance.extracted(0.7)
                )
        elif section.kind == SectionKind.EXPERIENCE:
            resume.experience.extend(_parse_experience(section.body))
        elif section.kind == SectionKind.EDUCATION:
            resume.education.extend(_parse_education(section.body))
        elif section.kind == SectionKind.SKILLS:
            resume.skills.extend(_parse_skills(section.body))
        elif section.kind == SectionKind.PROJECTS:
            resume.projects.extend(_parse_projects(section.body))
        elif section.kind == SectionKind.CERTIFICATIONS:
            resume.certifications.extend(_parse_certifications(section.body))
        elif section.kind == SectionKind.CUSTOM:
            custom = _parse_custom(section)
            if custom is not None:
                resume.custom_sections.append(custom)

    return resume
