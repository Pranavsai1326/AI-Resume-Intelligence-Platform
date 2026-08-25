"""Integration tests for POST /v1/ai/rewrite.

The default ``client`` fixture runs with ``llm_provider="null"`` (Settings default, no API key
configured in test settings), so every rewrite here exercises the honest "unavailable" path -
the correct default behaviour for a deployment with no LLM configured, not a shortcut standing in
for different behaviour.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.ai_fakes import FakeLLMProvider
from tests.conftest import new_session
from tests.fixtures import make_txt_bytes


async def _upload_document(client: AsyncClient, session_id: str) -> str:
    files = {"file": ("resume.txt", make_txt_bytes(), "text/plain")}
    upload = await client.post(
        "/v1/documents", files=files, headers={"X-Session-Id": session_id}
    )
    return str(upload.json()["document_id"])


async def test_rewrite_bullet_without_llm_configured_is_honestly_unavailable(
    client: AsyncClient,
) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    response = await client.post(
        "/v1/ai/rewrite",
        json={"document_id": document_id, "kind": "bullet", "text": "Built the service."},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["after"] is None
    assert body["unavailable_reason"] == "AI writing is not configured on this deployment."


async def test_rewrite_summary_without_llm_configured_is_honestly_unavailable(
    client: AsyncClient,
) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    response = await client.post(
        "/v1/ai/rewrite",
        json={"document_id": document_id, "kind": "summary", "text": "Backend engineer."},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 200
    assert response.json()["available"] is False


async def test_rewrite_unknown_document_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.post(
        "/v1/ai/rewrite",
        json={"document_id": "does-not-exist", "kind": "bullet", "text": "x"},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 404


async def test_rewrite_requires_a_session(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/ai/rewrite", json={"document_id": "d1", "kind": "bullet", "text": "x"}
    )
    assert response.status_code == 400


async def test_rewrite_rejects_invalid_kind(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)
    response = await client.post(
        "/v1/ai/rewrite",
        json={"document_id": document_id, "kind": "paragraph", "text": "x"},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 422


async def test_rewrite_with_an_available_provider_tracks_ai_calls_and_tokens(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 8: session counters must reflect real provider usage, not just count requests
    regardless of whether a call actually happened - `ai_tokens` previously existed on the
    counters model but nothing ever incremented it."""
    fake = FakeLLMProvider(response_text="Migrated the billing pipeline to event sourcing.")
    monkeypatch.setattr("app.api.v1.ai.get_llm_provider", lambda settings: fake)

    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    response = await client.post(
        "/v1/ai/rewrite",
        json={"document_id": document_id, "kind": "bullet", "text": "Built the service."},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 200
    assert response.json()["available"] is True

    session_state = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    counters = session_state.json()["counters"]
    assert counters["ai_calls"] == 1
    assert counters["ai_tokens"] == 20  # FakeLLMProvider reports 10 input + 10 output
