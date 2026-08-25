"""Extraction dispatch: bytes of a known kind in, plain text and layout signals out."""

from __future__ import annotations

from app.config import Settings
from app.core.errors import NoExtractableTextError
from app.documents.extract.base import ExtractionResult
from app.documents.extract.docx import extract_docx
from app.documents.extract.ocr import ocr_available
from app.documents.extract.pdf import extract_pdf
from app.documents.extract.txt import extract_txt
from app.documents.upload import DocumentKind

__all__ = ["ExtractionResult", "extract"]


def extract(kind: DocumentKind, data: bytes, settings: Settings) -> ExtractionResult:
    """Run the extractor for ``kind`` and enforce the "no fabricated content" rule.

    A document that is valid but yields no text (typically a scanned image saved as PDF) is not
    silently returned as an empty resume - it raises :class:`NoExtractableTextError`, honestly
    naming OCR as the missing capability when OCR is unavailable.
    """
    if kind is DocumentKind.PDF:
        result = extract_pdf(data, settings)
    elif kind is DocumentKind.DOCX:
        result = extract_docx(data)
    else:
        result = extract_txt(data)

    if not result.text.strip():
        if not ocr_available(settings):
            raise NoExtractableTextError
        # Reachable once a real OCR provider is wired in (see app.documents.extract.ocr).
        raise NoExtractableTextError  # pragma: no cover - no provider exists yet

    return result
