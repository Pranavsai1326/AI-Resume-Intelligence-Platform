"""Upload validation.

Uploaded bytes are hostile input until proven otherwise (SECURITY.md section 2). Type is
determined by magic-byte sniffing, never by the client-supplied ``Content-Type`` or filename
extension, and a DOCX's internal zip structure is bounds-checked before any XML parser ever
touches it.
"""

from __future__ import annotations

import zipfile
from enum import StrEnum
from io import BytesIO

import chardet

from app.core.errors import CorruptDocumentError, DocumentStructureError, UnsupportedFileTypeError

#: DOCX is a zip archive containing OOXML; entry-count and decompression-ratio limits are the
#: standard zip-bomb defence (SECURITY.md section 2).
MAX_DOCX_ENTRIES = 2_000
MAX_DOCX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
#: A single entry expanding more than this multiple of its compressed size is treated as hostile.
MAX_DOCX_COMPRESSION_RATIO = 100

REQUIRED_DOCX_ENTRIES = frozenset({"[Content_Types].xml", "word/document.xml"})


class DocumentKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"


def sniff_kind(data: bytes) -> DocumentKind:
    """Determine the real file type from its content, not its claimed type.

    Falls back to TXT only if the bytes are not one of the recognised binary formats *and*
    decode as text - so an arbitrary binary blob renamed to ``.txt`` is still rejected.
    """
    if data.startswith(b"%PDF-"):
        return DocumentKind.PDF
    if data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"):
        # A DOCX is a zip; a plain zip or another OOXML type shares this signature. Structural
        # validation below confirms it is actually a Word document.
        return DocumentKind.DOCX
    if _looks_like_text(data):
        return DocumentKind.TXT
    raise UnsupportedFileTypeError


def _looks_like_text(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return False
    detected = chardet.detect(data[:65536])
    confidence = detected.get("confidence") or 0.0
    return detected.get("encoding") is not None and confidence >= 0.5


def decode_text(data: bytes) -> str:
    """Decode TXT bytes, preferring UTF-8 and falling back to detection.

    Never raises on decodable-but-unusual encodings; a genuinely undecodable file was already
    rejected by :func:`sniff_kind`.
    """
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    detected = chardet.detect(data)
    encoding = detected.get("encoding") or "latin-1"
    try:
        return data.decode(encoding, errors="strict")
    except (UnicodeDecodeError, LookupError):
        return data.decode("utf-8", errors="replace")


def validate_docx_structure(data: bytes) -> None:
    """Bound a DOCX's internal zip before any XML parser opens it.

    Raises :class:`DocumentStructureError` for anything shaped like a zip bomb, and
    :class:`CorruptDocumentError` for a zip that is not actually a Word document.
    """
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}

            if len(infos) > MAX_DOCX_ENTRIES:
                raise DocumentStructureError(
                    f"The document contains too many internal parts (max {MAX_DOCX_ENTRIES})."
                )

            total_uncompressed = 0
            for info in infos:
                total_uncompressed += info.file_size
                if (
                    info.compress_size > 0
                    and info.file_size / info.compress_size > MAX_DOCX_COMPRESSION_RATIO
                    and info.file_size > 10 * 1024 * 1024
                ):
                    raise DocumentStructureError(
                        "The document contains a part with an implausible compression ratio."
                    )
            if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise DocumentStructureError(
                    "The document's uncompressed content exceeds the allowed size."
                )

            if not REQUIRED_DOCX_ENTRIES.issubset(names):
                raise CorruptDocumentError("This does not appear to be a valid Word document.")
    except zipfile.BadZipFile as exc:
        raise CorruptDocumentError from exc
