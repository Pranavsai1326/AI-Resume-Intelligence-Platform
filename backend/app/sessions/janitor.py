"""Background cleanup and startup recovery.

Layers 3 and 4 of the deletion model (PRIVACY_ARCHITECTURE.md section 3). TTL expiry alone is
authoritative for correctness; these exist so that a crash, a forced kill or a lost browser
cannot leave anything behind on disk, and so expired entries are reclaimed rather than lingering
in memory until someone happens to read them.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.logging import get_logger
from app.sessions.store import SessionStore

logger = get_logger(__name__)


@dataclass(slots=True)
class JanitorStats:
    """Content-free operational counters."""

    runs: int = 0
    keys_reclaimed: int = 0
    files_removed: int = 0
    failures: int = 0
    last_run_monotonic: float | None = field(default=None)


def ensure_temp_dir(path: Path) -> Path:
    """Create the temp directory with restrictive permissions.

    ``mode`` is honoured on POSIX; on Windows the directory inherits the user's ACL, which is
    already user-scoped. Documented rather than silently assumed.
    """
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    with contextlib.suppress(NotImplementedError, OSError):
        path.chmod(0o700)
    return path


def purge_temp_dir(path: Path, *, older_than_seconds: float = 0.0) -> int:
    """Remove temporary artefacts. Returns the number of entries removed.

    Called at startup (``older_than_seconds=0``: nothing in there can belong to this process,
    so everything is a leftover from a crash) and periodically by the janitor.
    """
    if not path.exists():
        return 0
    cutoff = time.time() - older_than_seconds
    removed = 0
    for entry in path.iterdir():
        try:
            if entry.stat().st_mtime > cutoff:
                continue
            if entry.is_dir():
                import shutil

                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        except OSError:
            # A file held open by another process is retried on the next sweep.
            logger.warning("janitor.temp_entry_unremovable")
    return removed


async def startup_recovery(temp_dir: Path) -> int:
    """Reclaim anything a previous process left behind.

    Session data itself needs no recovery: every key carries a TTL, so a crashed process leaves
    entries that expire on their own (memory backend: the process is gone with them).
    """
    ensure_temp_dir(temp_dir)
    removed = await asyncio.to_thread(purge_temp_dir, temp_dir, older_than_seconds=0.0)
    logger.info("startup.recovery_complete", temp_entries_removed=removed)
    return removed


class Janitor:
    """Periodic sweep of expired store entries and stale temporary files."""

    __slots__ = ("_interval", "_stats", "_stopping", "_store", "_task", "_temp_dir")

    def __init__(self, store: SessionStore, temp_dir: Path, interval_seconds: int) -> None:
        self._store = store
        self._temp_dir = temp_dir
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stats = JanitorStats()
        self._stopping = asyncio.Event()

    @property
    def stats(self) -> JanitorStats:
        return self._stats

    async def run_once(self) -> JanitorStats:
        try:
            reclaimed = await self._store.sweep()
            files = await asyncio.to_thread(
                purge_temp_dir, self._temp_dir, older_than_seconds=float(self._interval)
            )
            self._stats.runs += 1
            self._stats.keys_reclaimed += reclaimed
            self._stats.files_removed += files
            self._stats.last_run_monotonic = time.monotonic()
            if reclaimed or files:
                logger.info("janitor.swept", keys_reclaimed=reclaimed, files_removed=files)
        except Exception as exc:
            self._stats.failures += 1
            logger.error("janitor.sweep_failed", error_type=type(exc).__name__)
        return self._stats

    async def _loop(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                return
            await self.run_once()

    def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._loop(), name="session-janitor")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
