"""DOCX extraction: paragraphs, tables, columns, headers/footers."""

from __future__ import annotations

import pytest

from app.core.errors import CorruptDocumentError
from app.documents.extract.docx import extract_docx
from app.documents.upload import DocumentKind
from tests.fixtures import (
    make_corrupt_docx_bytes,
    make_docx_bytes,
    make_docx_with_header_footer_bytes,
)


def test_extracts_paragraph_text() -> None:
    result = extract_docx(make_docx_bytes(["Hello", "World"], with_table=False))
    assert result.kind is DocumentKind.DOCX
    assert "Hello" in result.text
    assert "World" in result.text


def test_extracts_table_content_in_reading_order() -> None:
    result = extract_docx(make_docx_bytes(["Before table"], with_table=True))
    assert "Before table" in result.text
    assert "Skill | Level" in result.text
    assert "Python | Expert" in result.text
    assert result.layout.has_tables is True


def test_no_table_when_none_present() -> None:
    result = extract_docx(make_docx_bytes(["Just text"], with_table=False))
    assert result.layout.has_tables is False


def test_two_column_section_is_detected() -> None:
    result = extract_docx(make_docx_bytes(["Text"], with_table=False, with_two_columns=True))
    assert result.layout.multi_column is True


def test_single_column_is_not_flagged() -> None:
    result = extract_docx(make_docx_bytes(["Text"], with_table=False, with_two_columns=False))
    assert result.layout.multi_column is False


def test_header_and_footer_text_detected() -> None:
    result = extract_docx(make_docx_with_header_footer_bytes())
    assert result.layout.has_repeating_header_footer is True


def test_corrupt_docx_raises_before_python_docx_opens_it() -> None:
    with pytest.raises(CorruptDocumentError):
        extract_docx(make_corrupt_docx_bytes())


def test_docx_has_no_fixed_page_count() -> None:
    result = extract_docx(make_docx_bytes(["Text"], with_table=False))
    assert result.layout.page_count is None
