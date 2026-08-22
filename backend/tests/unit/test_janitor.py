"""Janitor and startup recovery: deletion layers 3 and 4."""

from __future__ import annotations

from pathlib import Path

from app.core.clock import FakeClock
from app.sessions.janitor import Janitor, ensure_temp_dir, purge_temp_dir, startup_recovery
from app.sessions.memory import MemorySessionStore
from app.sessions.store import object_key


def test_ensure_temp_dir_creates_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "tmp"
    ensure_temp_dir(target)
    assert target.is_dir()


def test_purge_removes_files_and_directories(tmp_path: Path) -> None:
    (tmp_path / "leftover.pdf").write_bytes(b"%PDF-1.7 fake")
    nested = tmp_path / "job-123"
    nested.mkdir()
    (nested / "extract.txt").write_text("text")

    assert purge_temp_dir(tmp_path) == 2
    assert list(tmp_path.iterdir()) == []


def test_purge_respects_age_cutoff(tmp_path: Path) -> None:
    """A file currently being written must survive the sweep."""
    (tmp_path / "in-flight.pdf").write_bytes(b"data")
    assert purge_temp_dir(tmp_path, older_than_seconds=3600) == 0
    assert (tmp_path / "in-flight.pdf").exists()


async def test_startup_recovery_clears_crash_leftovers(tmp_path: Path) -> None:
    """Anything present at startup belongs to a dead process and must go."""
    temp_dir = tmp_path / "tmp"
    ensure_temp_dir(temp_dir)
    (temp_dir / "orphan-upload.pdf").write_bytes(b"%PDF-1.7")
    (temp_dir / "orphan-export.docx").write_bytes(b"PK")

    assert await startup_recovery(temp_dir) == 2
    assert list(temp_dir.iterdir()) == []


async def test_startup_recovery_creates_missing_dir(tmp_path: Path) -> None:
    temp_dir = tmp_path / "absent"
    assert await startup_recovery(temp_dir) == 0
    assert temp_dir.is_dir()


async def test_janitor_reclaims_expired_keys(tmp_path: Path, clock: FakeClock) -> None:
    store = MemorySessionStore(clock=clock)
    for index in range(3):
        await store.set(object_key("s1", "doc", str(index)), "v", 30)
    await store.set(object_key("s1", "doc", "long"), "v", 3600)

    clock.advance(31)
    janitor = Janitor(store, tmp_path, interval_seconds=60)
    stats = await janitor.run_once()

    assert stats.keys_reclaimed == 3
    assert stats.failures == 0
    assert store.live_key_count() == 1


async def test_janitor_survives_store_failure(tmp_path: Path) -> None:
    """The janitor must never die: a failing sweep is counted, not raised."""

    class BrokenStore(MemorySessionStore):
        async def sweep(self) -> int:
            raise ConnectionError("store down")

    janitor = Janitor(BrokenStore(), tmp_path, interval_seconds=60)
    stats = await janitor.run_once()
    assert stats.failures == 1


async def test_janitor_start_and_stop_is_clean(tmp_path: Path) -> None:
    janitor = Janitor(MemorySessionStore(), tmp_path, interval_seconds=1)
    janitor.start()
    janitor.start()  # idempotent
    await janitor.stop()
    await janitor.stop()  # safe to call twice
