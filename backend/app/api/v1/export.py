"""Export endpoints: PDF and DOCX, rendered in memory and streamed.

Nothing here is written to a server export directory (PRIVACY_ARCHITECTURE.md section 5) - the
rendered bytes exist only for the duration of one response.
"""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from app.core.deps import ActiveSessionDep, RateLimiterDep, SessionManagerDep, SettingsDep
from app.core.errors import ServiceUnavailableError
from app.core.ratelimit import RateLimitRule
from app.export.docx import render_resume_docx
from app.export.pdf import render_resume_pdf
from app.logging import get_logger
from app.resume.version_store import get_version_or_original

logger = get_logger(__name__)
router = APIRouter(prefix="/export", tags=["export"])

_UNSAFE_FILENAME_CHARS_RE = re.compile(r"[^A-Za-z0-9-]+")


class ExportResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    version_id: str | None = None
    format: Literal["pdf", "docx"]


def _safe_filename(label: str, extension: str) -> str:
    """A filename derived only from an allowlisted character set - never the raw label.

    The label is user-supplied (a version's name); stripping to `[A-Za-z0-9-]` rules out both
    path traversal and any possibility of CR/LF header injection into `Content-Disposition`
    (SECURITY.md section 6), independent of whether the value is later quoted.
    """
    slug = _UNSAFE_FILENAME_CHARS_RE.sub("-", label).strip("-").lower() or "resume"
    return f"{slug}.{extension}"


@router.post("")
async def export_resume(
    payload: ExportResumeRequest,
    session: ActiveSessionDep,
    manager: SessionManagerDep,
    settings: SettingsDep,
    limiter: RateLimiterDep,
) -> Response:
    await limiter.enforce(
        RateLimitRule("exports", settings.rate_limit_exports_per_hour, 3600), session.session_id
    )
    version = await get_version_or_original(
        manager, session, payload.document_id, payload.version_id
    )

    if payload.format == "pdf":
        data = await render_resume_pdf(version.resume)
        if data is None:
            raise ServiceUnavailableError("PDF export is not available on this deployment.")
        media_type = "application/pdf"
    else:
        data = render_resume_docx(version.resume)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    filename = _safe_filename(version.label, payload.format)
    logger.info("export.completed", format=payload.format)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
