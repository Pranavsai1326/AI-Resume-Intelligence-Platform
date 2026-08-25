"""PDF extraction: text, page limits, encryption, and the layout heuristics."""

from __future__ import annotations

import pytest

from app.core.errors import CorruptDocumentError, PasswordProtectedDocumentError, TooManyPagesError
from app.documents.extract.pdf import extract_pdf
from app.documents.upload import DocumentKind
from tests.fixtures import make_encrypted_pdf_bytes, make_pdf_bytes, make_two_column_pdf_bytes


def test_extracts_text_and_page_count(settings) -> None:
    result = extract_pdf(make_pdf_bytes(["Hello", "World"]), settings)
    assert result.kind is DocumentKind.PDF
    assert "Hello" in result.text
    assert "World" in result.text
    assert result.layout.page_count == 1


def test_multi_page_document_reports_correct_count(settings) -> None:
    result = extract_pdf(make_pdf_bytes(["Page content"], pages=3), settings)
    assert result.layout.page_count == 3
    assert result.pages is not None
    assert len(result.pages) == 3


def test_rejects_documents_over_the_page_limit(settings) -> None:
    settings = settings.model_copy(update={"max_pdf_pages": 2})
    with pytest.raises(TooManyPagesError):
        extract_pdf(make_pdf_bytes(["x"], pages=3), settings)


def test_encrypted_pdf_is_rejected_cleanly(settings) -> None:
    with pytest.raises(PasswordProtectedDocumentError):
        extract_pdf(make_encrypted_pdf_bytes(), settings)


def test_corrupt_pdf_bytes_raise_corrupt_document_error(settings) -> None:
    with pytest.raises(CorruptDocumentError):
        extract_pdf(b"%PDF-1.7\nnot actually a valid pdf structure", settings)


def test_single_column_page_is_not_flagged(settings) -> None:
    result = extract_pdf(make_pdf_bytes(["one", "two", "three"]), settings)
    assert result.layout.multi_column is False


def test_two_genuinely_separated_columns_are_detected(settings) -> None:
    result = extract_pdf(make_two_column_pdf_bytes(), settings)
    assert result.layout.multi_column is True


def test_pdf_never_claims_text_boxes_are_detected(settings) -> None:
    """Documented limitation: PDF text-box detection is not implemented, never guessed."""
    result = extract_pdf(make_pdf_bytes(), settings)
    assert result.layout.has_text_boxes is False


def test_repeating_margin_text_is_detected_as_header_footer(settings) -> None:
    lines = ["CONFIDENTIAL - Jordan Vance"] + [f"Body line {i}" for i in range(1, 30)]
    result = extract_pdf(make_pdf_bytes(lines, pages=2), settings)
    assert result.layout.has_repeating_header_footer is True


def test_no_repeating_margin_text_on_a_single_page(settings) -> None:
    result = extract_pdf(make_pdf_bytes(["Just one page of content"]), settings)
    assert result.layout.has_repeating_header_footer is False
