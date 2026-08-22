# PROJECT STATUS

**Last updated:** 2026-08-22 · **Current phase:** Phase 0 complete → Phase 1 ready to start

> Read this file first in every session, then only the architecture docs relevant to the task.
> Update it after every meaningful implementation change.

## Completed

* **Phase 0 — Product & architecture**
  * Repository and environment inspected (empty directory, not a git repo)
  * Stack selected and justified against the actual local environment
  * Product requirements: [PRD.md](PRD.md)
  * System architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
  * AI architecture: [AI_ARCHITECTURE.md](AI_ARCHITECTURE.md)
  * Privacy architecture: [PRIVACY_ARCHITECTURE.md](PRIVACY_ARCHITECTURE.md)
  * API contract: [API.md](API.md)
  * Security model: [SECURITY.md](SECURITY.md)
  * ADRs 0001–0006 in [docs/adr/](docs/adr/)

## In progress

Nothing. Awaiting go-ahead for the Phase 1 slice below.

## Next task — Phase 1 slice (foundation)

Backend:
1. Project scaffold: `pyproject.toml`, Python 3.13 venv, ruff + mypy + pytest config
2. `app/config.py` — Pydantic settings with startup validation of unsafe combinations
3. `app/logging.py` — structlog JSON with PII redaction processor
4. `app/core/errors.py` + exception middleware — sanitised error envelope
5. `app/core/middleware.py` — request ID, security headers, CORS allowlist
6. `app/sessions/` — `SessionStore` protocol, `MemorySessionStore`, `RedisSessionStore`, models, janitor
7. `app/api/v1/session.py` — create / get / heartbeat / delete
8. `app/api/v1/health.py` — `/health`, `/ready` with capability map
9. `app/core/ratelimit.py` — token bucket over the session store backend

Frontend:
10. Next.js 15 + TypeScript + Tailwind + shadcn/ui scaffold
11. Landing page with accurate privacy messaging (no fake stats, testimonials or activity)
12. App shell, navigation, session bootstrap hook, heartbeat, `sendBeacon` cleanup
13. Zustand in-memory store; lint rule banning `localStorage`/`indexedDB` for user content
14. Session-expiry UX (expiring banner, expired recovery path)

Tests (part of the slice, not after it):
15. Store conformance suite run against both backends (TTL, namespace delete, isolation)
16. Session lifecycle integration tests (create, sliding TTL, absolute cap, delete)
17. First privacy tests: expiry removes data, session B cannot read session A, logs carry no content
18. Health/ready and error-envelope tests

Definition of done for the slice: backend + frontend + validation + error handling + tests + docs,
with `PROJECT_STATUS.md` updated.

## Planned (after Phase 1)

| Phase | Scope |
|---|---|
| 2 | Document processing: upload, validation, PDF/DOCX/TXT extraction, layout signals, sections, structured resume, OCR fallback, cleanup |
| 3 | Resume analyzer: health scores, ATS compatibility, formatting, keywords, explainable scoring, recommendations |
| 4 | Job intelligence: JD parsing, requirement extraction, matching, semantic layer, skill gaps |
| 5 | Resume builder: editor, templates, live preview, AI writing, tailoring, in-session versions, PDF/DOCX export |
| 6 | Career intelligence: cover letters, interview prep, learning priorities |
| 7 | Recruiter screening: bulk async pipeline, extraction, ranking, comparison, shortlist, report export |
| 8 | Production hardening: security, rate limits, retries, performance, monitoring, privacy tests, AI evaluation, cost |
| 9 | Deployment: environments, CI/CD, health checks, monitoring, smoke tests, DEPLOYMENT.md + TESTING.md |

## Architecture decisions

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-python-313-runtime.md) | Python 3.13.5 backend runtime |
| [0002](docs/adr/0002-session-store-abstraction.md) | `SessionStore` abstraction: memory (dev) / Redis (prod) |
| [0003](docs/adr/0003-no-application-database.md) | No application database at all |
| [0004](docs/adr/0004-pdf-parsing-library.md) | pdfplumber + pypdf (permissive licence, word geometry) |
| [0005](docs/adr/0005-local-embeddings-default.md) | Local ONNX embeddings (fastembed, bge-small-en-v1.5) |
| [0006](docs/adr/0006-pdf-export-via-chromium.md) | HTML templates rendered to PDF by headless Chromium |

## Known issues / environment gaps

| Gap | Impact | Handling |
|---|---|---|
| Redis not installed locally | Cannot exercise the Redis backend on this machine | Memory backend for dev; Redis backend covered by the shared conformance suite and CI service container |
| Docker not installed | No container-based local stack | Dev loop requires none; containers introduced in Phase 9 |
| Tesseract not installed | OCR fallback cannot run locally | OCR is feature-detected; image-only PDFs get an honest error, never silent failure |
| No LLM/embedding API key in environment | Layer 3 features cannot run yet | `NullLLMProvider` returns an explicit unavailable state; local embeddings need no key |
| Node package manager is npm (no pnpm/yarn) | — | Use npm; no workspace tooling required |

## Current blockers

None.

## Open questions (non-blocking, decided by default until challenged)

1. **Hosting target** — not yet chosen. Architecture stays platform-neutral; decided in Phase 9.
2. **LLM provider credentials** — needed before Phase 5/6 can be exercised end to end. Deterministic
   phases 1–4 are unaffected.
3. **Session TTL defaults** — 60 min idle / 8 h absolute, configurable; revisit against real usage.
