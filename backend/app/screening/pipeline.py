"""Per-candidate screening pipeline: validate -> extract -> structure -> redact -> match.

Runs as one queue job per candidate (ARCHITECTURE.md section 6): the bytes are already read and
size-bounded by the time this runs (Starlette's ``UploadFile`` cannot survive past the request
that created it, so streaming has to happen at request time - everything downstream of that runs
in the background job). Redaction happens strictly before matching, never after (PRD section 8) -
even though the deterministic/semantic scoring components never read contact info, so redacting
first costs nothing and keeps the ordering honest rather than incidentally correct.

Both CPU-bound stages (extraction, matching) run in a thread via ``asyncio.to_thread`` - this
function is itself a coroutine running inside the job queue's worker pool, and calling a
synchronous, potentially slow stage directly would block the whole event loop, stalling every
other candidate's job and the API server together.
"""

from __future__ import annotations

import asyncio

from app.config import Settings
from app.core.errors import DocumentProcessingTimeoutError
from app.documents.extract import extract
from app.documents.structure import build_resume
from app.documents.upload import sniff_kind
from app.jobs.models import JobDescription
from app.matching.engine import compute_job_match
from app.screening.models import CandidateResult, RedactionInfo
from app.screening.redact import redact_resume

#: Same ceiling as single-document extraction (app.api.v1.documents) - one hung parser fails
#: that one candidate's job rather than the whole batch or the process (SECURITY.md section 2).
EXTRACTION_TIMEOUT_SECONDS = 20


async def process_candidate(
    raw: bytes, job: JobDescription, candidate_id: str, settings: Settings
) -> CandidateResult:
    """Raises on any failure - the caller (the job queue) turns that into a FAILED job state and
    never surfaces provider/library detail either way (SECURITY.md section 4)."""
    detected_kind = sniff_kind(raw)

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(extract, detected_kind, raw, settings),
            timeout=EXTRACTION_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise DocumentProcessingTimeoutError from exc

    resume = build_resume(result.text)
    redacted_resume, fields = redact_resume(resume)
    match = await asyncio.to_thread(compute_job_match, redacted_resume, job, settings)

    return CandidateResult(
        candidate_id=candidate_id,
        match=match,
        redaction=RedactionInfo(applied=bool(fields), fields=fields),
        resume=redacted_resume,
    )
