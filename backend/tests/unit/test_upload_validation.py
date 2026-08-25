"""Upload validation: magic-byte sniffing and DOCX structural bounds (SECURITY.md section 2)."""

from __future__ import annotations

import pytest

from app.core.errors import CorruptDocumentError, DocumentStructureError, UnsupportedFileTypeError
from app.documents.upload import DocumentKind, decode_text, sniff_kind, validate_docx_structure
from tests.fixtures import (
    make_corrupt_docx_bytes,
    make_docx_bytes,
    make_pdf_bytes,
    make_random_binary_bytes,
    make_txt_bytes,
    make_zip_bomb_docx_bytes,
)


def test_sniffs_pdf_by_signature() -> None:
    assert sniff_kind(make_pdf_bytes()) is DocumentKind.PDF


def test_sniffs_docx_by_signature() -> None:
    assert sniff_kind(make_docx_bytes()) is DocumentKind.DOCX


def test_sniffs_txt_by_decodability() -> None:
    assert sniff_kind(make_txt_bytes()) is DocumentKind.TXT


def test_client_supplied_extension_is_irrelevant() -> None:
    """A PDF renamed to .txt is still sniffed as a PDF - the client's claim is never trusted."""
    pdf_bytes = make_pdf_bytes()
    assert sniff_kind(pdf_bytes) is DocumentKind.PDF


def test_random_binary_is_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        sniff_kind(make_random_binary_bytes())


def test_empty_bytes_are_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        sniff_kind(b"")


def test_decode_text_prefers_utf8() -> None:
    assert decode_text("café".encode()) == "café"


def test_decode_text_falls_back_for_latin1() -> None:
    # "café" in latin-1 is not valid UTF-8.
    data = "café".encode("latin-1")
    assert "caf" in decode_text(data)


def test_decode_text_never_raises_on_garbage() -> None:
    decode_text(b"\xff\xfe\x00\x01not really text")  # must not raise


def test_valid_docx_structure_passes() -> None:
    validate_docx_structure(make_docx_bytes())  # must not raise


def test_corrupt_docx_missing_required_parts() -> None:
    with pytest.raises(CorruptDocumentError):
        validate_docx_structure(make_corrupt_docx_bytes())


def test_not_a_zip_at_all() -> None:
    with pytest.raises(CorruptDocumentError):
        validate_docx_structure(b"this is not a zip file")


def test_zip_bomb_shaped_docx_is_rejected() -> None:
    """Many highly-compressible large entries must be rejected before any XML parser opens them."""
    with pytest.raises(DocumentStructureError):
        validate_docx_structure(make_zip_bomb_docx_bytes(entries=10, entry_size=30_000_000))


def test_too_many_entries_is_rejected() -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
        for index in range(2_001):
            archive.writestr(f"part_{index}.xml", "x")
    with pytest.raises(DocumentStructureError):
        validate_docx_structure(buffer.getvalue())


def test_ordinary_small_docx_with_table_is_fine() -> None:
    validate_docx_structure(make_docx_bytes(with_table=True))
