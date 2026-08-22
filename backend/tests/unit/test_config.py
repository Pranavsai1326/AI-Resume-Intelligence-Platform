"""Startup configuration safety.

The application must refuse to boot on combinations that silently break correctness or privacy,
rather than starting and failing subtly in production.
"""

from __future__ import annotations

import pytest

from app.config import Settings, UnsafeConfigurationError


def _prod(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "app_env": "production",
        "debug": False,
        "log_format": "json",
        "session_store_backend": "redis",
        "redis_url": "redis://localhost:6379/0",
        "cors_origins": ["https://app.example.com"],
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_development_defaults_are_valid() -> None:
    Settings(app_env="development").validate_runtime()


def test_memory_store_rejected_with_multiple_workers() -> None:
    settings = Settings(app_env="development", session_store_backend="memory", workers=4)
    with pytest.raises(UnsafeConfigurationError, match="WORKERS>1"):
        settings.validate_runtime()


def test_redis_backend_requires_url() -> None:
    settings = Settings(app_env="development", session_store_backend="redis", redis_url="")
    with pytest.raises(UnsafeConfigurationError, match="REDIS_URL"):
        settings.validate_runtime()


def test_absolute_ttl_must_not_be_shorter_than_idle_ttl() -> None:
    settings = Settings(
        app_env="development",
        session_idle_ttl_seconds=3600,
        session_absolute_ttl_seconds=600,
    )
    with pytest.raises(UnsafeConfigurationError, match="ABSOLUTE_TTL"):
        settings.validate_runtime()


def test_production_rejects_debug() -> None:
    with pytest.raises(UnsafeConfigurationError, match="DEBUG"):
        _prod(debug=True).validate_runtime()


def test_production_rejects_memory_store() -> None:
    with pytest.raises(UnsafeConfigurationError, match="redis"):
        _prod(session_store_backend="memory").validate_runtime()


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(UnsafeConfigurationError, match="CORS_ORIGINS"):
        _prod(cors_origins=["*"]).validate_runtime()


def test_production_rejects_console_logging() -> None:
    with pytest.raises(UnsafeConfigurationError, match="LOG_FORMAT"):
        _prod(log_format="console").validate_runtime()


def test_production_rejects_anthropic_without_key() -> None:
    with pytest.raises(UnsafeConfigurationError, match="ANTHROPIC_API_KEY"):
        _prod(llm_provider="anthropic", anthropic_api_key="").validate_runtime()


def test_valid_production_config_passes() -> None:
    _prod().validate_runtime()


def test_empty_cors_rejected() -> None:
    with pytest.raises(UnsafeConfigurationError, match="at least one allowed origin"):
        Settings(app_env="development", cors_origins=[]).validate_runtime()


def test_cors_origins_parsed_from_csv() -> None:
    settings = Settings(cors_origins="http://a.test, http://b.test")  # type: ignore[arg-type]
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_capabilities_are_honest_without_providers() -> None:
    """With nothing configured, every AI capability reports false - no pretending."""
    capabilities = Settings(app_env="development").capabilities()
    assert capabilities["llm"] is False
    assert capabilities["embeddings"] is False
    assert capabilities["redis"] is False


def test_llm_capability_requires_key_not_just_provider() -> None:
    settings = Settings(app_env="development", llm_provider="anthropic", anthropic_api_key="")
    assert settings.capabilities()["llm"] is False
