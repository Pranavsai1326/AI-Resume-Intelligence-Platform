"""Application configuration.

Settings come from the environment (optionally a local ``.env``). Unsafe combinations are
rejected at startup rather than degrading silently in production - see ``validate_runtime``.
"""

from __future__ import annotations

import os
import shutil
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


#: Values that mean "no real credential was ever supplied" even though the field isn't empty -
#: chiefly `.env.example`'s literal `YOUR_GEMINI_API_KEY_HERE` placeholder, so copying the example
#: file verbatim into a real `.env` degrades to the honest "unavailable" state (Phase 9F) rather
#: than the provider attempting - and failing - a real request with a dummy string.
_PLACEHOLDER_API_KEY_VALUES = frozenset(
    {
        "your_gemini_api_key_here",
        "your-gemini-api-key-here",
        "your_anthropic_api_key_here",
        "your-anthropic-api-key-here",
        "changeme",
        "change_me",
        "replace_me",
        "placeholder",
        "xxx",
    }
)


def is_configured_api_key(value: str) -> bool:
    """True only for a value that could plausibly be a real credential."""
    return bool(value) and value.strip().lower() not in _PLACEHOLDER_API_KEY_VALUES


class UnsafeConfigurationError(RuntimeError):
    """Raised when the configuration would be unsafe to run.

    The application refuses to boot rather than starting in a state that silently breaks the
    privacy or correctness guarantees (for example: an in-memory session store shared across
    multiple worker processes, where sessions would resolve only on the worker that created them).
    """


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Under pytest (`PYTEST_VERSION` is set for the whole session, before collection even
        # starts) tests must be hermetic and reproducible regardless of what a developer's local
        # `.env` happens to contain - every test that cares about a setting passes it explicitly.
        # Without this, a local `backend/.env` (e.g. one holding a real Gemini key for manual
        # testing) would silently change default test behaviour depending on who ran the suite.
        env_file=None if os.environ.get("PYTEST_VERSION") else (".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # -- Application ---------------------------------------------------------------------
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_version: str = "0.1.0"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 1
    trust_proxy: bool = False

    # -- CORS ----------------------------------------------------------------------------
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # -- Session store -------------------------------------------------------------------
    session_store_backend: Literal["memory", "redis"] = "memory"
    redis_url: str = ""

    # -- Session lifetime ----------------------------------------------------------------
    session_idle_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)
    session_absolute_ttl_seconds: int = Field(default=28_800, ge=300, le=604_800)
    janitor_interval_seconds: int = Field(default=60, ge=5, le=3600)
    #: How long a released session survives after the page goes away. Long enough that a
    #: reload or a quick back-navigation rejoins it; short enough that a genuinely closed tab
    #: is cleaned up in minutes rather than an hour.
    session_release_grace_seconds: int = Field(default=120, ge=10, le=600)

    # -- Rate limiting -------------------------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_session_create_per_hour: int = Field(default=30, ge=1)
    rate_limit_requests_per_minute: int = Field(default=120, ge=1)
    rate_limit_uploads_per_hour: int = Field(default=120, ge=1)
    #: Bounds provider spend per anonymous session (SECURITY.md section 4) - covers rewrite,
    #: tailoring's AI-assisted bullets, cover letters, and interview prep alike.
    rate_limit_ai_calls_per_hour: int = Field(default=100, ge=1)
    #: Session-lifetime cap on total AI tokens spent (input + output, summed across every AI
    #: feature) - bounds total spend even when every individual call stays under the hourly
    #: ai_calls limit above. Phase 9G: closes the "tracked but not enforced" gap noted in Phase 8.
    rate_limit_ai_tokens_per_session: int = Field(default=200_000, ge=1)
    #: PDF export launches a Chromium process per call - bounded independently of the general
    #: upload/AI limits so it cannot become its own resource-exhaustion vector.
    rate_limit_exports_per_hour: int = Field(default=60, ge=1)

    # -- Uploads (Phase 2) ---------------------------------------------------------------
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    max_pdf_pages: int = Field(default=20, ge=1)
    max_bulk_resumes: int = Field(default=100, ge=1)
    temp_dir: str = ""

    # -- AI providers (Phases 4+) --------------------------------------------------------
    llm_provider: Literal["null", "anthropic", "gemini"] = "null"
    anthropic_api_key: str = ""
    llm_model_reasoning: str = "claude-sonnet-5"
    llm_model_bulk: str = "claude-haiku-4-5-20251001"
    #: Server-side only, never exposed to the frontend (AI_ARCHITECTURE.md section 2).
    #: `.env.example` ships the literal placeholder `YOUR_GEMINI_API_KEY_HERE` - see
    #: `is_configured_api_key` below, which is what keeps that placeholder from ever being
    #: treated as a real credential.
    gemini_api_key: str = ""
    #: A current, low-cost/free-tier-friendly Gemini Flash model - configurable so a
    #: deprecated or renamed model id never needs a code change to fix.
    llm_model_gemini: str = "gemini-2.5-flash"
    llm_timeout_seconds: int = Field(default=60, ge=1)
    #: "fastembed" by default (ADR-0005: local ONNX, no API key, resume text stays server-side).
    #: Falls back honestly if the package or model cannot load - see
    #: app.matching.embeddings.FastEmbedProvider - rather than requiring this to be flipped on.
    embedding_backend: Literal["none", "fastembed", "remote"] = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # -- Document processing (Phase 2) ---------------------------------------------------
    ocr_enabled: bool = False
    tesseract_cmd: str = ""

    # -- Recruiter screening (Phase 7) ----------------------------------------------------
    #: Bounded-concurrency in-process worker pool (ARCHITECTURE.md section 8) - bulk screening
    #: must never block inside the HTTP request that enqueues it.
    screening_worker_concurrency: int = Field(default=4, ge=1)

    # -- Logging -------------------------------------------------------------------------
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid log level: {value}")
        return level

    # -- Derived -------------------------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def temp_path(self) -> Path:
        if self.temp_dir:
            return Path(self.temp_dir)
        import tempfile

        return Path(tempfile.gettempdir()) / "resume-intelligence"

    def capabilities(self) -> dict[str, bool]:
        """Honest capability map.

        Reported by ``/ready`` so the frontend can disable features that genuinely cannot run
        instead of offering them and failing, or worse, faking a result.
        """
        return {
            "llm": (
                (self.llm_provider == "anthropic" and is_configured_api_key(self.anthropic_api_key))
                or (self.llm_provider == "gemini" and is_configured_api_key(self.gemini_api_key))
            ),
            "embeddings": self._embeddings_importable(),
            "ocr": self.ocr_enabled and self._tesseract_available(),
            "pdf_export": self._playwright_available(),
            "redis": self.session_store_backend == "redis",
        }

    def _tesseract_available(self) -> bool:
        if self.tesseract_cmd:
            return Path(self.tesseract_cmd).exists()
        return shutil.which("tesseract") is not None

    def _embeddings_importable(self) -> bool:
        """Package-presence check only - fast enough for a health probe.

        Whether the model actually *loads* (first-run download, disk space) is checked lazily by
        the provider itself when a match is actually requested; that is the authoritative signal,
        reflected per-request via a component's own ``available`` flag. This is a necessary-but-
        not-sufficient precondition, same spirit as the Tesseract binary-presence check above.
        """
        if self.embedding_backend == "none":
            return False
        if self.embedding_backend == "fastembed":
            from importlib.util import find_spec

            return find_spec("fastembed") is not None
        return True  # "remote": availability depends on runtime credentials, not checked here

    @staticmethod
    def _playwright_available() -> bool:
        from importlib.util import find_spec

        return find_spec("playwright") is not None

    # -- Startup safety ------------------------------------------------------------------

    def validate_runtime(self) -> None:
        """Refuse to boot on configurations that are unsafe in the current environment."""
        problems: list[str] = []

        if self.session_store_backend == "memory" and self.workers > 1:
            problems.append(
                "SESSION_STORE_BACKEND=memory cannot be used with WORKERS>1: sessions would be "
                "invisible to other workers. Set SESSION_STORE_BACKEND=redis or WORKERS=1."
            )
        if self.session_store_backend == "redis" and not self.redis_url:
            problems.append("SESSION_STORE_BACKEND=redis requires REDIS_URL to be set.")
        if self.session_absolute_ttl_seconds < self.session_idle_ttl_seconds:
            problems.append(
                "SESSION_ABSOLUTE_TTL_SECONDS must be >= SESSION_IDLE_TTL_SECONDS."
            )
        if "*" in self.cors_origins and self.is_production:
            problems.append("CORS_ORIGINS=* is not permitted in production.")
        if not self.cors_origins:
            problems.append("CORS_ORIGINS must list at least one allowed origin.")

        if self.is_production:
            if self.debug:
                problems.append("DEBUG must be false in production.")
            if self.session_store_backend == "memory":
                problems.append(
                    "Production requires SESSION_STORE_BACKEND=redis so sessions survive "
                    "process restarts across instances."
                )
            if self.log_format != "json":
                problems.append("LOG_FORMAT must be json in production.")
            anthropic_selected = self.llm_provider == "anthropic"
            if anthropic_selected and not is_configured_api_key(self.anthropic_api_key):
                problems.append(
                    "LLM_PROVIDER=anthropic requires a real ANTHROPIC_API_KEY (not a placeholder)."
                )
            if self.llm_provider == "gemini" and not is_configured_api_key(self.gemini_api_key):
                problems.append(
                    "LLM_PROVIDER=gemini requires a real GEMINI_API_KEY (not a placeholder)."
                )

        if problems:
            raise UnsafeConfigurationError(
                "Refusing to start due to unsafe configuration:\n  - " + "\n  - ".join(problems)
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
