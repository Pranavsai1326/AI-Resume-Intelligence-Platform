"""Session-storage shape for an uploaded document.

Shared between the documents API (which writes it) and the analysis API (which reads it), so
neither imports a private name from the other.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.documents.extract.base import LayoutSignals
from app.documents.upload import DocumentKind
from app.resume.models import Resume

#: Documents are session-scoped working data, not indefinitely cached; capped at a modest TTL
#: rather than given their own longer lifetime.
DOCUMENT_TTL_SECONDS = 3600


class StoredDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    kind: DocumentKind
    layout: LayoutSignals
    ocr_used: bool
    text: str
    resume: Resume | None
