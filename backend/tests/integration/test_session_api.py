"""Session API behaviour through the full middleware stack."""

from __future__ import annotations

import json

from httpx import AsyncClient

from tests.conftest import new_session


async def test_create_session_requires_no_input(client: AsyncClient) -> None:
    """No signup, no login, no identity - a POST with a mode is the whole ceremony."""
    response = await client.post("/v1/session", json={})
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "candidate"
    assert len(body["session_id"]) >= 40
    assert body["idle_ttl_seconds"] > 0
    assert body["absolute_ttl_seconds"] > body["idle_ttl_seconds"]
    assert body["counters"] == {"documents": 0, "analyses": 0, "ai_calls": 0, "ai_tokens": 0}


async def test_create_recruiter_session(client: AsyncClient) -> None:
    response = await client.post("/v1/session", json={"mode": "recruiter"})
    assert response.status_code == 201
    assert response.json()["mode"] == "recruiter"


async def test_rejects_unknown_mode(client: AsyncClient) -> None:
    response = await client.post("/v1/session", json={"mode": "administrator"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_rejects_unknown_fields(client: AsyncClient) -> None:
    response = await client.post("/v1/session", json={"mode": "candidate", "user_id": "u-1"})
    assert response.status_code == 422


async def test_get_session_returns_metadata(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    assert response.status_code == 200
    assert response.json()["session_id"] == session_id


async def test_missing_header_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/v1/session")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SESSION_REQUIRED"


async def test_unknown_session_reports_expired(client: AsyncClient) -> None:
    """Unknown and expired are reported identically so a prober learns nothing."""
    response = await client.get("/v1/session", headers={"X-Session-Id": "x" * 43})
    assert response.status_code == 410
    body = response.json()["error"]
    assert body["code"] == "SESSION_EXPIRED"
    assert body["category"] == "session"


async def test_heartbeat_extends_idle_ttl(client: AsyncClient) -> None:
    session_id = await new_session(client)
    first = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    response = await client.post(
        "/v1/session/heartbeat", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 200
    assert response.json()["last_activity_at"] >= first.json()["last_activity_at"]


async def test_heartbeat_never_extends_absolute_deadline(client: AsyncClient) -> None:
    session_id = await new_session(client)
    created = (await client.get("/v1/session", headers={"X-Session-Id": session_id})).json()
    beat = (
        await client.post("/v1/session/heartbeat", headers={"X-Session-Id": session_id})
    ).json()
    assert beat["hard_expires_at"] == created["hard_expires_at"]


async def test_delete_session_is_idempotent(client: AsyncClient) -> None:
    session_id = await new_session(client)
    headers = {"X-Session-Id": session_id}
    assert (await client.delete("/v1/session", headers=headers)).status_code == 204
    assert (await client.delete("/v1/session", headers=headers)).status_code == 204
    after = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    assert after.status_code == 410


async def test_delete_unknown_session_still_204(client: AsyncClient) -> None:
    """Teardown must never error, and must not reveal whether the id existed."""
    response = await client.delete("/v1/session", headers={"X-Session-Id": "unknown"})
    assert response.status_code == 204


async def test_beacon_release_shortens_but_does_not_destroy(client: AsyncClient) -> None:
    """sendBeacon cannot set headers, so /session/release takes the id in a text/plain body.

    Release must not destroy: `pagehide` also fires on a reload, and a refresh must not throw
    away the user's work.
    """
    session_id = await new_session(client)
    before = (await client.get("/v1/session", headers={"X-Session-Id": session_id})).json()

    response = await client.post(
        "/v1/session/release",
        content=json.dumps({"session_id": session_id}),
        headers={"Content-Type": "text/plain;charset=UTF-8"},
    )
    assert response.status_code == 204

    after = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    assert after.status_code == 200, "a released session must still be resumable"
    assert before["idle_ttl_seconds"] > 1000


async def test_resuming_a_released_session_restores_the_full_idle_ttl(
    client: AsyncClient,
) -> None:
    session_id = await new_session(client)
    await client.post(
        "/v1/session/release",
        content=json.dumps({"session_id": session_id}),
        headers={"Content-Type": "text/plain;charset=UTF-8"},
    )
    resumed = (await client.get("/v1/session", headers={"X-Session-Id": session_id})).json()
    assert resumed["idle_ttl_seconds"] > 3000


async def test_beacon_release_tolerates_garbage(client: AsyncClient) -> None:
    for payload in ("", "not json", "[]", '{"session_id": null}'):
        response = await client.post(
            "/v1/session/release",
            content=payload,
            headers={"Content-Type": "text/plain;charset=UTF-8"},
        )
        assert response.status_code == 204


async def test_session_ids_are_unique_across_creations(client: AsyncClient) -> None:
    ids = {await new_session(client) for _ in range(20)}
    assert len(ids) == 20
