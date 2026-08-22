"""Log redaction.

Redaction is a product requirement, not a convention. These tests exercise the processor
directly; ``tests/privacy`` additionally drives the whole API and asserts on real output.
"""

from __future__ import annotations

from app.logging import MAX_VALUE_LENGTH, MAX_VALUE_TOKENS, REDACTED, redact_processor

RESUME_TEXT = (
    "Priya Raman, Senior Backend Engineer at Northwind Logistics. "
    "priya.raman@example.com | +91 98765 43210 | Bengaluru, India"
)


def _process(event: dict[str, object]) -> dict[str, object]:
    return redact_processor(None, "info", event)  # type: ignore[arg-type]


def test_sensitive_keys_are_dropped() -> None:
    result = _process({"event": "parsed", "resume_text": RESUME_TEXT, "email": "a@b.com"})
    assert result["resume_text"] == REDACTED
    assert result["email"] == REDACTED
    assert "Priya" not in str(result)


def test_email_redacted_under_innocuous_key() -> None:
    result = _process({"event": "x", "note": "contact was priya.raman@example.com"})
    assert "priya.raman@example.com" not in str(result["note"])
    assert REDACTED in str(result["note"])


def test_phone_redacted_under_innocuous_key() -> None:
    result = _process({"event": "x", "note": "reached them on +91 98765 43210 today"})
    assert "98765 43210" not in str(result["note"])


def test_long_values_are_truncated_not_emitted() -> None:
    """Any long free-text value is assumed to be user content."""
    blob = "Managed a team of engineers delivering logistics software. " * 20
    result = _process({"event": "x", "detail": blob})
    assert len(str(result["detail"])) < MAX_VALUE_LENGTH + 40
    assert "logistics" not in str(result["detail"])


def test_nested_structures_are_redacted() -> None:
    result = _process(
        {
            "event": "x",
            "candidate": {"name": "Priya Raman", "email": "priya@example.com"},
            "items": [{"resume_text": RESUME_TEXT}],
        }
    )
    assert result["candidate"] == REDACTED
    assert "Priya" not in str(result)
    assert "example.com" not in str(result)


def test_operational_fields_survive() -> None:
    """Redaction must not destroy the operational value of logs."""
    result = _process(
        {
            "event": "request.completed",
            "request_id": "abc123",
            "status": 200,
            "duration_ms": 12.5,
            "route": "/v1/session",
            "model": "claude-sonnet-5",
            "tokens": 480,
        }
    )
    assert result["request_id"] == "abc123"
    assert result["status"] == 200
    assert result["duration_ms"] == 12.5
    assert result["route"] == "/v1/session"
    assert result["tokens"] == 480


def test_secrets_are_dropped() -> None:
    result = _process({"event": "x", "api_key": "sk-ant-secret", "authorization": "Bearer xyz"})
    assert result["api_key"] == REDACTED
    assert result["authorization"] == REDACTED
    assert "sk-ant-secret" not in str(result)


def test_prose_is_redacted_even_under_innocuous_keys() -> None:
    """No regex recognises a person's name, so prose is redacted structurally."""
    result = _process({"event": "x", "note": "Priya Raman, Senior Backend Engineer"})
    assert "Priya" not in str(result)
    assert REDACTED in str(result["note"])


def test_short_identifier_values_survive() -> None:
    for value in ("session.created", "/v1/session", "claude-sonnet-5", "SESSION_EXPIRED"):
        assert _process({"event": "x", "field": value})["field"] == value


def test_token_threshold_is_the_boundary() -> None:
    short = " ".join(["word"] * MAX_VALUE_TOKENS)
    long = " ".join(["word"] * (MAX_VALUE_TOKENS + 1))
    assert _process({"event": "x", "field": short})["field"] == short
    assert REDACTED in str(_process({"event": "x", "field": long})["field"])


def test_prose_is_redacted_at_every_nesting_depth() -> None:
    payload: dict[str, object] = {"event": "x"}
    node = payload
    for _ in range(8):
        child: dict[str, object] = {"note": RESUME_TEXT}
        node["child"] = child
        node = child
    assert "Priya" not in str(_process(payload))
    assert "Northwind" not in str(_process(payload))
