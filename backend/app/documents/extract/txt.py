"""TXT extraction. The simplest path: decode, done."""

from __future__ import annotations

from app.documents.extract.base import ExtractionResult, LayoutSignals
from app.documents.upload import DocumentKind, decode_text


def extract_txt(data: bytes) -> ExtractionResult:
    text = decode_text(data).replace("\r\n", "\n").replace("\r", "\n")
    return ExtractionResult(
        kind=DocumentKind.TXT,
        text=text,
        pages=None,
        layout=LayoutSignals(),
    )
