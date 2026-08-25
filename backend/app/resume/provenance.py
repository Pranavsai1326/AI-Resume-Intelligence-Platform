"""Field provenance.

Every piece of resume data is one of four kinds, per AI_ARCHITECTURE.md section 5. Provenance is
carried on the field itself, survives edits, and is what lets the UI show "this came from your
upload" versus "the AI proposed this and you accepted it" instead of quietly blurring the two.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ProvenanceKind(StrEnum):
    #: Typed or pasted directly by the user.
    USER_PROVIDED = "user_provided"
    #: Parsed from an uploaded document. Carries a confidence and, where available, a source span.
    EXTRACTED = "extracted"
    #: Proposed by AI, not yet accepted. Must never be treated as the resume's actual content.
    AI_SUGGESTED = "ai_suggested"
    #: AI text the user explicitly accepted. The pre-acceptance value is retained separately so a
    #: before/after comparison is always available (AI_ARCHITECTURE.md section 5).
    AI_GENERATED = "ai_generated"


class SourceSpan(BaseModel):
    """Where in the source document a value was found. Extraction only."""

    model_config = ConfigDict(extra="forbid")

    page: int | None = None
    #: Character offsets into the page/section's extracted text, for highlighting the source.
    start: int | None = None
    end: int | None = None


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ProvenanceKind
    #: 0.0-1.0. Required for EXTRACTED; meaningless (and omitted) for USER_PROVIDED.
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: SourceSpan | None = None

    @staticmethod
    def user_provided() -> Provenance:
        return Provenance(kind=ProvenanceKind.USER_PROVIDED)

    @staticmethod
    def extracted(confidence: float, source: SourceSpan | None = None) -> Provenance:
        return Provenance(kind=ProvenanceKind.EXTRACTED, confidence=confidence, source=source)


class ProvenancedValue(BaseModel, Generic[T]):
    """A value paired with where it came from.

    Generic over the value type so the same wrapper serves a plain string field (a name) and a
    structured one (an experience entry) without duplicating the provenance bookkeeping.
    """

    model_config = ConfigDict(extra="forbid")

    value: T
    provenance: Provenance
