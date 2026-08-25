"""TXT extraction."""

from __future__ import annotations

from app.documents.extract.txt import extract_txt
from app.documents.upload import DocumentKind


def test_extracts_plain_text() -> None:
    result = extract_txt(b"Hello\nWorld\n")
    assert result.kind is DocumentKind.TXT
    assert result.text == "Hello\nWorld\n"
    assert result.pages is None


def test_normalizes_line_endings() -> None:
    result = extract_txt(b"line1\r\nline2\rline3\n")
    assert "\r" not in result.text
    assert result.text.split("\n") == ["line1", "line2", "line3", ""]


def test_page_count_is_not_meaningful_for_txt() -> None:
    assert extract_txt(b"text").layout.page_count is None
