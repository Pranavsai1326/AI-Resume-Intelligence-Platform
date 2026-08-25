"""PDF extraction via pdfplumber (ADR-0004).

Word-level bounding boxes are what make the layout heuristics below real measurements rather than
guesses: column detection looks at where words actually sit on the page, not at formatting hints.
They remain heuristics, not certainties, and are documented as such on
:class:`~app.documents.extract.base.LayoutSignals`.
"""

from __future__ import annotations

from collections import Counter
from io import BytesIO
from itertools import pairwise
from typing import Any

import pdfplumber
from pdfplumber.page import Page
from pypdf import PdfReader

from app.config import Settings
from app.core.errors import CorruptDocumentError, PasswordProtectedDocumentError, TooManyPagesError
from app.documents.extract.base import ExtractionResult, LayoutSignals
from app.documents.upload import DocumentKind

#: Each side of a candidate gutter must hold at least this share of the page's words for the page
#: to count as multi-column - guards against a handful of stray words (e.g. a page number)
#: triggering a false positive.
COLUMN_MIN_SIDE_FRACTION = 0.15
#: The gutter itself must be at least this wide, as a fraction of page width, to count as a real
#: column break rather than ordinary word-to-word spacing within one column of running text.
COLUMN_MIN_GUTTER_FRACTION = 0.035
#: Only gutters within this central band are considered - keeps a wide left/right page margin
#: from ever being mistaken for a gutter between two columns.
COLUMN_SEARCH_LOW = 0.20
COLUMN_SEARCH_HIGH = 0.80

#: Top/bottom margin band (fraction of page height) scanned for repeating header/footer text.
MARGIN_BAND_FRACTION = 0.08


def _check_not_encrypted(data: bytes) -> None:
    try:
        reader = PdfReader(BytesIO(data))
        encrypted = reader.is_encrypted
    except Exception as exc:
        raise CorruptDocumentError from exc
    if encrypted:
        raise PasswordProtectedDocumentError


def _find_gutter(page: Page, words: list[dict[str, Any]]) -> float | None:
    """Locate a real column gutter's x-position, or ``None`` if the page reads as one column.

    Fixed-width detection (a hardcoded 45-55% band) only catches columns of near-equal width. A
    common resume template - a narrow sidebar (contact/skills) alongside a wider main column
    (experience) - puts its gutter anywhere from roughly 25% to 40% of the page width, which a
    fixed centre band misses entirely. Instead: sort every word's horizontal midpoint, find the
    single widest gap between consecutive midpoints within the central search band, and treat
    that as the gutter candidate. A real column break shows up as a gap much wider than the
    ordinary spacing between words *within* a column of running text; both constraints below
    (minimum gutter width, minimum words on each side) exist specifically to reject an ordinary
    paragraph's largest inter-word gap from being mistaken for one.
    """
    if not words or page.width == 0:
        return None

    midpoints = sorted((w["x0"] + w["x1"]) / 2 for w in words)
    best_gap = 0.0
    best_position: float | None = None
    for previous, current in pairwise(midpoints):
        gap = current - previous
        position = (previous + current) / 2
        position_fraction = position / page.width
        if COLUMN_SEARCH_LOW <= position_fraction <= COLUMN_SEARCH_HIGH and gap > best_gap:
            best_gap = gap
            best_position = position

    if best_position is None or best_gap < page.width * COLUMN_MIN_GUTTER_FRACTION:
        return None

    left = sum(1 for m in midpoints if m < best_position)
    right = len(midpoints) - left
    total = len(midpoints)
    if left / total < COLUMN_MIN_SIDE_FRACTION or right / total < COLUMN_MIN_SIDE_FRACTION:
        return None
    return best_position


def _column_aware_text(page: Page, gutter_x: float) -> str:
    """Text for a genuinely multi-column page, reading one full column before the next.

    ``page.extract_text()`` groups words into lines purely by vertical position: on a two-column
    page, a word from the left column and a word from the right column that happen to sit at the
    same height land on the *same reconstructed line*, interleaved - "Jordan Vance EXPERIENCE"
    where the source page has "Jordan Vance" in a left sidebar and "EXPERIENCE" starting the right
    column's content. Cropping to each column and extracting each independently avoids that:
    pdfplumber's own line-grouping runs correctly within a column that no longer has anything at
    a conflicting horizontal position to merge with.
    """
    left = page.crop((0, 0, gutter_x, page.height))
    right = page.crop((gutter_x, 0, page.width, page.height))
    left_text = left.extract_text(x_tolerance=1.5, y_tolerance=3) or ""
    right_text = right.extract_text(x_tolerance=1.5, y_tolerance=3) or ""
    return "\n\n".join(part for part in (left_text, right_text) if part.strip())


def _margin_text(page: Page, words: list[dict[str, Any]]) -> str:
    if page.height == 0:
        return ""
    top_cut = page.height * MARGIN_BAND_FRACTION
    bottom_cut = page.height * (1 - MARGIN_BAND_FRACTION)
    fragments = [w["text"] for w in words if w["top"] < top_cut or w["bottom"] > bottom_cut]
    return " ".join(fragments).strip()


def _has_repeating_snippet(snippets: list[str]) -> bool:
    """True if the same non-trivial margin text appears on at least two pages."""
    counts = Counter(snippet for snippet in snippets if snippet)
    return any(count >= 2 for count in counts.values())


def extract_pdf(data: bytes, settings: Settings) -> ExtractionResult:
    _check_not_encrypted(data)

    pages_text: list[str] = []
    multi_column_pages = 0
    has_tables = False
    has_images = False
    margin_snippets: list[str] = []

    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            if len(pdf.pages) == 0:
                raise CorruptDocumentError("The document has no pages.")
            if len(pdf.pages) > settings.max_pdf_pages:
                raise TooManyPagesError(settings.max_pdf_pages)

            for page in pdf.pages:
                words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
                gutter_x = _find_gutter(page, words)
                pages_text.append(
                    _column_aware_text(page, gutter_x)
                    if gutter_x is not None
                    else (page.extract_text(x_tolerance=1.5, y_tolerance=3) or "")
                )

                if gutter_x is not None:
                    multi_column_pages += 1
                if not has_tables and page.find_tables():
                    has_tables = True
                if not has_images and page.images:
                    has_images = True

                margin_text = _margin_text(page, words)
                if margin_text:
                    margin_snippets.append(margin_text)
    except (CorruptDocumentError, TooManyPagesError, PasswordProtectedDocumentError):
        raise
    except Exception as exc:
        raise CorruptDocumentError from exc

    return ExtractionResult(
        kind=DocumentKind.PDF,
        text="\n\n".join(pages_text).strip(),
        pages=pages_text,
        layout=LayoutSignals(
            page_count=len(pages_text),
            multi_column=multi_column_pages >= max(1, len(pages_text) // 2),
            has_tables=has_tables,
            has_images=has_images,
            has_text_boxes=False,
            has_repeating_header_footer=_has_repeating_snippet(margin_snippets),
        ),
    )
