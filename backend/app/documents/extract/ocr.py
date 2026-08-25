"""OCR fallback for documents with no extractable text layer.

Feature-detected, never assumed available. Tesseract is not installed in this environment
(confirmed during Phase 0 inspection), so :func:`ocr_available` reports ``False`` and callers get
an honest :class:`~app.core.errors.NoExtractableTextError` instead of empty or fabricated text.
The provider abstraction exists so a real OCR pass can be wired in later without touching call
sites - the same pattern AI_ARCHITECTURE.md section 2 applies to LLM providers.
"""

from __future__ import annotations

from typing import Protocol

from app.config import Settings
from app.core.errors import ServiceUnavailableError


class OcrProvider(Protocol):
    def is_available(self) -> bool: ...
    def extract_text(self, image_bytes: bytes) -> str: ...


class NullOcrProvider:
    """The only provider actually wired up today."""

    def is_available(self) -> bool:
        return False

    def extract_text(self, image_bytes: bytes) -> str:
        raise ServiceUnavailableError("OCR is not available on this deployment.")


def get_ocr_provider(settings: Settings) -> OcrProvider:
    """Select an OCR provider by configuration and actual binary availability.

    Only ``NullOcrProvider`` exists today: `pytesseract` is not part of this deployment's
    dependency set, matching the Tesseract binary's absence. A real provider (pytesseract +
    Pillow, gated on `settings.capabilities()["ocr"]`) is tracked as follow-up work in
    PROJECT_STATUS.md, not fabricated here.
    """
    del settings  # kept in the signature so call sites do not change when a real provider lands
    return NullOcrProvider()


def ocr_available(settings: Settings) -> bool:
    return get_ocr_provider(settings).is_available()
