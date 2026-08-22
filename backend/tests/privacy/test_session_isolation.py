"""Session isolation: one session must never observe another's data."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.sessions.manager import SessionManager
from app.sessions.models import SessionMode
from app.sessions.store import meta_key, object_key
from tests.conftest import new_session

SECRET_A = "Session A resume for Zorvath Quillfeather"
SECRET_B = "Session B resume for Marlowe Ashgrove"


async def test_objects_are_namespaced_per_session(manager: SessionManager) -> None:
    a = await manager.create(SessionMode.CANDIDATE)
    b = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(a, "document", "resume", SECRET_A)
    await manager.put_object(b, "document", "resume", SECRET_B)

    assert await manager.get_object(a, "document", "resume") == SECRET_A
    assert await manager.get_object(b, "document", "resume") == SECRET_B
    assert object_key(a.session_id, "document", "resume") != object_key(
        b.session_id, "document", "resume"
    )


async def test_destroying_one_session_leaves_the_other_intact(manager: SessionManager) -> None:
    a = await manager.create(SessionMode.CANDIDATE)
    b = await manager.create(SessionMode.RECRUITER)
    await manager.put_object(a, "document", "resume", SECRET_A)
    await manager.put_object(b, "document", "resume", SECRET_B)

    await manager.destroy(a.session_id)

    assert await manager.get_object(a, "document", "resume") is None
    assert await manager.get_object(b, "document", "resume") == SECRET_B


async def test_expiry_of_one_session_leaves_the_other_intact(manager: SessionManager) -> None:
    """Namespaces expire independently; one session's clock is not another's."""
    a = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(a, "cache", "c1", SECRET_A, ttl_seconds=30)
    b = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(b, "cache", "c1", SECRET_B, ttl_seconds=3000)

    assert await manager.get_object(b, "cache", "c1") == SECRET_B
    await manager.destroy(a.session_id)
    assert await manager.get_object(b, "cache", "c1") == SECRET_B


async def test_session_b_cannot_read_session_a_over_the_api(client: AsyncClient) -> None:
    session_a = await new_session(client)
    session_b = await new_session(client)
    assert session_a != session_b

    response = await client.get("/v1/session", headers={"X-Session-Id": session_b})
    assert response.json()["session_id"] == session_b


@pytest.mark.parametrize(
    "forged",
    [
        "sess:other:meta",
        "../../etc/passwd",
        "%2e%2e%2f",
        "' OR 1=1 --",
        "*",
        "sess:*",
    ],
)
async def test_forged_session_ids_are_rejected(client: AsyncClient, forged: str) -> None:
    """Ids are looked up as opaque strings; no pattern, path or wildcard is interpreted."""
    response = await client.get("/v1/session", headers={"X-Session-Id": forged})
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


async def test_key_construction_cannot_be_influenced_by_the_id(manager: SessionManager) -> None:
    """Even a hostile id stays inside its own namespace rather than escaping it."""
    hostile = "abc:*:meta"
    assert meta_key(hostile).startswith("sess:abc:*:meta")
    assert await manager.get(hostile) is None


async def test_destroying_a_wildcard_id_deletes_nothing(manager: SessionManager) -> None:
    a = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(a, "document", "resume", SECRET_A)

    assert await manager.destroy("*") == 0
    assert await manager.destroy("") == 0
    assert await manager.get_object(a, "document", "resume") == SECRET_A


async def test_explicit_delete_only_destroys_the_named_session(client: AsyncClient) -> None:
    session_a = await new_session(client)
    session_b = await new_session(client)

    await client.delete("/v1/session", headers={"X-Session-Id": session_a})

    assert (
        await client.get("/v1/session", headers={"X-Session-Id": session_a})
    ).status_code == 410
    assert (
        await client.get("/v1/session", headers={"X-Session-Id": session_b})
    ).status_code == 200
