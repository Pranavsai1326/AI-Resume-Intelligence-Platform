"""PDF extraction via pdfplumber (ADR-0004).

Word-level bounding boxes are what make the layout heuristics below real measurements rather than
guesses: column detection looks at where words actually sit on the page, not at formatting hints.
They remain heuristics, not certainties, and are documented as such on
:class:`~app.documents.extract.base.LayoutSignals`.
"""

from __future__ import annotations

from collections import Counter
from io import BytesIO
from typing import Any

import pdfplumber
from pdfplumber.page import Page
from pypdf import PdfReader

from app.config import Settings
from app.core.errors import CorruptDocumentError, PasswordProtectedDocumentError, TooManyPagesError
from app.documents.extract.base import ExtractionResult, LayoutSignals
from app.documents.upload import DocumentKind

#: Fraction of page width treated as the gutter between two columns. A word whose horizontal
#: midpoint falls here counts toward neither side.
COLUMN_GUTTER_LOW = 0.45
COLUMN_GUTTER_HIGH = 0.55
#: Each side must hold at least this share of the page's words for the page to count as
#: multi-column - guards against a handful of stray words (e.g. a page number) triggering a
#: false positive.
COLUMN_MIN_SIDE_FRACTION = 0.15
COLUMN_MAX_CENTER_FRACTION = 0.05

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


def _is_multi_column(page: Page, words: list[dict[str, Any]]) -> bool:
    if not words or page.width == 0:
        return False
    left = right = center = 0
    for word in words:
        midpoint = ((word["x0"] + word["x1"]) / 2) / page.width
        if midpoint < COLUMN_GUTTER_LOW:
            left += 1
        elif midpoint > COLUMN_GUTTER_HIGH:
            right += 1
        else:
            center += 1
    total = left + right + center
    if total == 0:
        return False
    return (
        left / total >= COLUMN_MIN_SIDE_FRACTION
        and right / total >= COLUMN_MIN_SIDE_FRACTION
        and center / total < COLUMN_MAX_CENTER_FRACTION
    )


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
                pages_text.append(page.extract_text(x_tolerance=1.5, y_tolerance=3) or "")

                if _is_multi_column(page, words):
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
