"""Shared extraction result shape.

All Layer 1 (deterministic) work per AI_ARCHITECTURE.md section 1 - nothing here calls an LLM.
Word-level geometry is used internally to compute the layout signals below but is not retained on
the result: keeping session objects small matters more than exposing raw coordinates that no
Phase 2 caller needs yet.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.documents.upload import DocumentKind


class LayoutSignals(BaseModel):
    """ATS-relevant formatting signals, computed heuristically from document structure.

    These are deterministic heuristics over real document geometry, not guesses - but they are
    still heuristics, and are documented as such rather than presented as certainties. Consumed
    by the ATS analyzer in Phase 3 to flag likely parsing problems (SECURITY.md-adjacent: this is
    product logic, not a security control).
    """

    model_config = ConfigDict(extra="forbid")

    #: True page count. Only PDF is paginated without rendering; ``None`` for DOCX and TXT.
    page_count: int | None = None
    #: Words cluster into two side-by-side columns on at least one page. PDF and DOCX only;
    #: single-column TXT is always False.
    multi_column: bool = False
    has_tables: bool = False
    has_images: bool = False
    #: Explicit text-box / floating-text elements. Reliably detectable in DOCX via its XML;
    #: not detected for PDF, where a floating text box is indistinguishable from ordinary text
    #: once rendered - always False there rather than an unreliable guess.
    has_text_boxes: bool = False
    #: The same short text (e.g. a name or page number) repeats in the page margins across
    #: multiple pages, suggesting a running header/footer that some ATS parsers skip.
    has_repeating_header_footer: bool = False


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: DocumentKind
    #: Full document text in reading order.
    text: str
    #: Per-page text. ``None`` for TXT, where the concept of a page does not apply.
    pages: list[str] | None = None
    layout: LayoutSignals
    ocr_used: bool = False
