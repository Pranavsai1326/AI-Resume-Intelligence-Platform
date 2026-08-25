"""Bounded, self-cleaning temporary storage for uploads.

Bytes are held in memory via ``SpooledTemporaryFile`` and only spill to disk once they exceed a
small threshold; when they do, the file lands in the dedicated temp directory (0700, random
name, created by :func:`app.sessions.janitor.ensure_temp_dir`) and is deleted when the scope
closes - including on an exception (PRIVACY_ARCHITECTURE.md section 5).

Note on the ASGI layer: the multipart parser that produces the inbound ``UploadFile`` may itself
spool large parts to the OS default temp directory before this module ever sees them. That spool
is opened and closed entirely within the lifetime of one request by Starlette itself, so it never
outlives the request - but it is not inside our controlled, janitor-swept ``temp_dir``. Session
content can therefore transit the OS temp directory for the duration of a single upload request.
This is disclosed rather than silently assumed away; the privacy test suite verifies our own
controlled directory (`app.temp_path`), which is the one this architecture actually guarantees.
"""

from __future__ import annotations

import contextlib
import secrets
from collections.abc import Iterator
from tempfile import SpooledTemporaryFile
from typing import Protocol

from app.config import Settings
from app.core.errors import EmptyFileError, FileTooLargeError
from app.sessions.janitor import ensure_temp_dir

#: Bytes held purely in memory before spilling to disk. Keeps the overwhelming majority of
#: resumes - a few hundred KB - from ever touching the filesystem at all.
SPOOL_THRESHOLD_BYTES = 2 * 1024 * 1024

CHUNK_SIZE = 256 * 1024


class AsyncReadable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


@contextlib.contextmanager
def bounded_spool(settings: Settings) -> Iterator[SpooledTemporaryFile[bytes]]:
    """A temporary buffer scoped to one operation, guaranteed to clean up after itself."""
    ensure_temp_dir(settings.temp_path)
    prefix = f"upload-{secrets.token_hex(8)}-"
    spooled: SpooledTemporaryFile[bytes] = SpooledTemporaryFile(
        max_size=SPOOL_THRESHOLD_BYTES, mode="w+b", dir=str(settings.temp_path), prefix=prefix
    )
    try:
        yield spooled
    finally:
        spooled.close()


async def read_upload_bounded(upload: AsyncReadable, settings: Settings) -> bytes:
    """Read an uploaded file, aborting mid-stream the moment it exceeds the size limit.

    The check happens as bytes arrive rather than after the full file is buffered, so an
    oversized upload never fully lands in memory or on disk (SECURITY.md section 2).
    """
    total = 0
    with bounded_spool(settings) as spooled:
        while True:
            chunk = await upload.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.max_upload_bytes:
                raise FileTooLargeError(settings.max_upload_bytes)
            spooled.write(chunk)

        if total == 0:
            raise EmptyFileError

        spooled.seek(0)
        return spooled.read()
