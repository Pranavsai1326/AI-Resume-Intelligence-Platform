"""Generic line-based header/section splitting.

Shared by resume section detection (``app.documents.sections``) and job-description section
detection (``app.jobs.parse``): both need the same mechanical operation - find lines that look
like a section header (a known keyword, in any casing, or a narrow ALL-CAPS fallback) and slice
the text between them - over different keyword tables and different section-kind enums.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Generic, TypeVar

K = TypeVar("K")

#: A candidate header line: short, letters/spaces/basic punctuation only, no sentence-ending
#: punctuation. Deliberately conservative - a false negative just falls into the previous
#: section's body, which is recoverable; a false positive fragments real content.
_HEADER_SHAPE_RE = re.compile(r"^[A-Za-z][A-Za-z\s&/,'\-]{1,45}$")
_TRAILING_PUNCTUATION_RE = re.compile(r"[:\-–—]+$")


def normalize_header(line: str) -> str:
    return _TRAILING_PUNCTUATION_RE.sub("", line.strip()).strip().lower()


#: A real section header word is essentially never this short - "AWARDS" (6) and
#: "PUBLICATIONS" (12) are typical. Short all-caps tokens well under this length are
#: overwhelmingly degree and certification abbreviations that legitimately appear on their own
#: line inside a section - "MBA", "PMP", "CFA", "PHD", "CPA" - not section headers themselves.
#: Phase 9C found this concretely: an EDUCATION entry with "MBA" alone on its own line had that
#: line misread as the start of an unrelated custom section, silently truncating the entry and
#: losing its date range entirely.
_MIN_ALL_CAPS_HEADER_LENGTH = 5


def looks_like_all_caps_header(line: str) -> bool:
    """Fallback detector for a header not in the known-keyword table: ALL-CAPS only.

    A title-case shape test was tried (in the resume section detector this module was factored
    out of) and rejected - it matched ordinary content lines just as readily as headers, which
    corrupted surrounding sections. Known headers in any casing are still caught via the keyword
    table regardless of this function; this path exists only for an unrecognised header like
    "AWARDS". A header written in ordinary title case is missed rather than corrupting what
    surrounds it - a safe failure mode.
    """
    stripped = line.strip()
    if not (_MIN_ALL_CAPS_HEADER_LENGTH <= len(stripped) <= 45):
        return False
    if not _HEADER_SHAPE_RE.match(stripped):
        return False
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) < _MIN_ALL_CAPS_HEADER_LENGTH:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio > 0.85


@dataclass(slots=True)
class HeaderMatch(Generic[K]):
    line_index: int
    kind: K
    title: str


def find_headers(
    lines: list[str], keyword_map: dict[str, K], *, fallback_kind: K | None = None
) -> list[HeaderMatch[K]]:
    """Locate header lines.

    ``fallback_kind``, if given, is assigned to an ALL-CAPS line matching no known keyword;
    leave it ``None`` to only ever recognise the given keywords.
    """
    headers: list[HeaderMatch[K]] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        normalized = normalize_header(stripped)
        if normalized in keyword_map:
            headers.append(HeaderMatch(index, keyword_map[normalized], stripped))
        elif fallback_kind is not None and looks_like_all_caps_header(stripped):
            headers.append(HeaderMatch(index, fallback_kind, stripped))
    return headers


def slice_bodies(
    lines: list[str], headers: list[HeaderMatch[K]]
) -> list[tuple[HeaderMatch[K], str]]:
    """Pair each header with the text between it and the next header (or end of document)."""
    result: list[tuple[HeaderMatch[K], str]] = []
    for position, header in enumerate(headers):
        body_start = header.line_index + 1
        body_end = (
            headers[position + 1].line_index if position + 1 < len(headers) else len(lines)
        )
        body = "\n".join(lines[body_start:body_end]).strip()
        result.append((header, body))
    return result
