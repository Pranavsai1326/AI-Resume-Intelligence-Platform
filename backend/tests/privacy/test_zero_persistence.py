"""Zero-persistence guarantees.

These are product requirements, not optional extras (PRIVACY_ARCHITECTURE.md section 10). They
assert the property directly - that user content does not reach durable storage and does not
survive expiry - rather than trusting that no code path happens to write it today.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.core.clock import FakeClock
from app.main import create_app
from app.sessions.manager import SessionManager
from app.sessions.memory import MemorySessionStore
from app.sessions.models import SessionMode
from tests.conftest import new_session

#: Distinctive strings that must never appear on disk or in logs. Synthetic, not a real person.
CANARY_NAME = "Zorvath Quillfeather"
CANARY_EMAIL = "zorvath.quillfeather@example-canary.test"
CANARY_RESUME = (
    f"{CANARY_NAME}\n{CANARY_EMAIL}\n+1 555 0100 4242\n"
    "Senior Platform Engineer at Cindervale Robotics. Built the Palewind ingestion service."
)
CANARY_TOKENS = ("Zorvath", "Quillfeather", "Cindervale", "Palewind", "example-canary")

#: Directories that are build/tooling artefacts, not application output.
_IGNORED_DIRS = {".git", ".venv", "node_modules", ".next", "__pycache__", ".pytest_cache",
                 ".ruff_cache", ".mypy_cache", ".turbo"}


def _snapshot(root: Path) -> dict[Path, float]:
    """Map of every file under ``root`` to its mtime, skipping tooling artefacts."""
    seen: dict[Path, float] = {}
    for path in root.rglob("*"):
        if any(part in _IGNORED_DIRS for part in path.parts):
            continue
        if path.is_file():
            try:
                seen[path] = path.stat().st_mtime
            except OSError:
                continue
    return seen


def _files_containing(paths: list[Path], needles: tuple[str, ...]) -> list[Path]:
    hits: list[Path] = []
    for path in paths:
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        text = blob.decode("utf-8", errors="ignore")
        if any(needle in text for needle in needles):
            hits.append(path)
    return hits


@pytest.fixture
def workspace_root() -> Path:
    """The backend package root - the only place application code could write to."""
    return Path(__file__).resolve().parents[2]


async def test_session_content_never_reaches_disk(
    workspace_root: Path, tmp_path: Path
) -> None:
    """A full session carrying resume-shaped content must leave nothing on the filesystem."""
    settings = Settings(
        app_env="development",
        temp_dir=str(tmp_path / "tmp"),
        session_store_backend="memory",
        rate_limit_enabled=False,
        log_format="json",
    )
    app = create_app(settings)
    before = _snapshot(workspace_root)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_id = await new_session(http)
            manager: SessionManager = app.state.session_manager
            meta = await manager.require(session_id)
            await manager.put_object(meta, "document", "d1", CANARY_RESUME)
            await manager.put_object(meta, "analysis", "a1", CANARY_RESUME)

            assert await manager.get_object(meta, "document", "d1") == CANARY_RESUME

    after = _snapshot(workspace_root)
    new_files = [path for path in after if path not in before]
    modified = [path for path in after if path in before and after[path] != before[path]]

    assert _files_containing(new_files + modified, CANARY_TOKENS) == [], (
        "session content reached durable storage"
    )
    assert _files_containing(list(tmp_path.rglob("*")), CANARY_TOKENS) == []  # noqa: ASYNC240


async def test_temp_directory_is_empty_after_session(tmp_path: Path) -> None:
    settings = Settings(
        app_env="development",
        temp_dir=str(tmp_path / "tmp"),
        session_store_backend="memory",
        rate_limit_enabled=False,
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_id = await new_session(http)
            await http.delete("/v1/session", headers={"X-Session-Id": session_id})

    temp_dir = tmp_path / "tmp"
    assert temp_dir.is_dir()
    assert list(temp_dir.iterdir()) == []


async def test_expiry_destroys_everything_without_any_client_call(
    manager: SessionManager, clock: FakeClock, memory_store: MemorySessionStore
) -> None:
    """The authoritative deletion layer: no beacon, no janitor, no request - just time."""
    meta = await manager.create(SessionMode.CANDIDATE)
    for index in range(5):
        await manager.put_object(meta, "document", f"d{index}", CANARY_RESUME)
    assert memory_store.live_key_count() == 6

    clock.advance(3601)

    assert await manager.get(meta.session_id) is None
    assert await manager.get_object(meta, "document", "d0") is None
    assert memory_store.live_key_count() == 0
    await memory_store.sweep()
    assert not any(CANARY_NAME in str(value) for value in memory_store._data.values())


async def test_janitor_reclaims_expired_content(
    manager: SessionManager, clock: FakeClock, memory_store: MemorySessionStore, tmp_path: Path
) -> None:
    from app.sessions.janitor import Janitor

    meta = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(meta, "document", "d1", CANARY_RESUME)
    clock.advance(3601)

    stats = await Janitor(memory_store, tmp_path, 60).run_once()
    assert stats.keys_reclaimed == 2
    assert memory_store.live_key_count() == 0


async def test_new_process_starts_clean(tmp_path: Path) -> None:
    """Restarting must not restore anything: there is no durable store to restore from."""
    settings = Settings(
        app_env="development",
        temp_dir=str(tmp_path / "tmp"),
        session_store_backend="memory",
        rate_limit_enabled=False,
    )

    first = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=first), base_url="http://test") as http:
        async with first.router.lifespan_context(first):
            session_id = await new_session(http)
            manager: SessionManager = first.state.session_manager
            meta = await manager.require(session_id)
            await manager.put_object(meta, "document", "d1", CANARY_RESUME)

    second = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=second), base_url="http://test") as http:
        async with second.router.lifespan_context(second):
            response = await http.get("/v1/session", headers={"X-Session-Id": session_id})
            assert response.status_code == 410
            assert second.state.session_store.live_key_count() == 0


async def test_startup_recovery_removes_crashed_process_leftovers(tmp_path: Path) -> None:
    """A crash cannot leave an uploaded document behind: startup purges the temp directory."""
    temp_dir = tmp_path / "tmp"
    temp_dir.mkdir(parents=True)
    orphan = temp_dir / "upload-abc123.pdf"
    orphan.write_text(CANARY_RESUME, encoding="utf-8")

    settings = Settings(
        app_env="development", temp_dir=str(temp_dir), session_store_backend="memory"
    )
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test"):
        async with app.router.lifespan_context(app):
            assert not orphan.exists()
            assert _files_containing(list(temp_dir.rglob("*")), CANARY_TOKENS) == []


async def test_deleted_session_content_is_unrecoverable(manager: SessionManager) -> None:
    meta = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(meta, "document", "d1", CANARY_RESUME)
    await manager.destroy(meta.session_id)

    assert await manager.get_object(meta, "document", "d1") is None
    assert await manager.list_object_keys(meta) == []
    assert await manager.get(meta.session_id) is None


async def test_no_endpoint_accepts_a_storage_key(client: AsyncClient) -> None:
    """Handlers derive keys from the resolved session; a caller cannot supply one."""
    session_id = await new_session(client)
    for payload in ({"key": "sess:other:meta"}, {"namespace": "sess:other"}):
        response = await client.post(
            "/v1/session", json={"mode": "candidate", **payload}
        )
        assert response.status_code == 422
    assert (
        await client.get("/v1/session", headers={"X-Session-Id": session_id})
    ).status_code == 200
