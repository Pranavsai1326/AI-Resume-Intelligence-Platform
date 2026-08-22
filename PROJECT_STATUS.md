# PROJECT STATUS

**Last updated:** 2026-08-22 · **Current phase:** Phase 1 complete → Phase 2 ready to start

> Read this file first in every session, then only the architecture docs relevant to the task.
> Update it after every meaningful implementation change.

## Completed

### Phase 0 — Product & architecture

Repository and environment inspected; stack chosen against what the machine actually has.
Documents: [PRD.md](PRD.md), [ARCHITECTURE.md](ARCHITECTURE.md), [AI_ARCHITECTURE.md](AI_ARCHITECTURE.md),
[PRIVACY_ARCHITECTURE.md](PRIVACY_ARCHITECTURE.md), [API.md](API.md), [SECURITY.md](SECURITY.md),
ADRs 0001–0006 in [docs/adr/](docs/adr/).

### Phase 1 — Ephemeral session foundation

**Backend** (`backend/app/`)

| Area | Delivered |
|---|---|
| Config | Pydantic settings; startup refusal on unsafe combinations (memory store + multi-worker, redis without URL, production with debug/console logs/memory store/wildcard CORS, absolute TTL < idle TTL) |
| Logging | structlog JSON/console with a redaction processor: sensitive keys dropped, emails/phones scrubbed, and prose redacted structurally (logs carry identifiers and enums, never free text) |
| Errors | `AppError` hierarchy → uniform sanitised envelope with code, category, retryable flag and request id. No stack traces, paths or provider details ever reach a client |
| Middleware | Request id (inbound value sanitised), content-free access logging by route template, security headers, HSTS in production, global per-IP rate limit |
| Session store | `SessionStore` protocol; `MemorySessionStore` (dev, zero infrastructure) and `RedisSessionStore` (prod, index-set namespace deletion). Both held to one conformance suite. Every write requires a positive TTL — the interface cannot express persistence |
| Session lifecycle | Create / resolve / heartbeat / release / destroy. Sliding 60-min idle TTL, hard 8-h cap that activity never extends, per-object TTLs capped at session lifetime |
| Cleanup | Four layers: client release beacon, TTL expiry (authoritative), periodic janitor, startup temp-dir purge |
| Rate limiting | Fixed-window limiter over the same store; identities hashed so raw IPs are never stored or logged; fails open if the store is down |
| Health | `/health` (dependency-free) and `/ready` (store reachability + honest capability map) |

**Frontend** (`frontend/`)

Next.js 15 + TypeScript + Tailwind v4 + shadcn-style primitives. Landing page with accurate privacy
messaging and no invented statistics or testimonials; workspace shell; session bootstrap, rejoin
after reload, 5-minute heartbeat, live countdown, expiry dialog, error/loading/empty states;
in-memory Zustand store with an ESLint rule banning persistent browser storage; keyboard-accessible
with skip link, focus styles, live regions and reduced-motion support.

**Verification** — all green:

```
backend   142 passed, 10 skipped (Redis, no server present)   ruff clean   mypy --strict clean
frontend  19 passed   eslint clean   tsc --noEmit clean   next build clean
```

Also smoke-tested against real running servers: session create → get → heartbeat → release →
reload-rejoin → explicit end, plus security headers and the error envelope over HTTP, and the
browser-storage invariant checked in a live page (`sessionStorage` holds only id + mode;
`localStorage` empty).

### Defects found and fixed during Phase 1

These were caught by the tests and the live smoke test, not assumed away:

1. **`SettingsDep` read process-global settings** instead of the running app's, so per-request rate
   limits ignored the deployment's configuration.
2. **Access logs lost their correlation ids** — the context was reset before the `request.completed`
   line was written.
3. **Prose survived log redaction.** A name under an innocuous key is unmatchable by regex, so the
   rule is now structural: values with more than four words are redacted.
4. **Timestamps were being mangled** by the phone-number pattern; self-generated structural keys are
   now exempt from value scrubbing, with inbound request ids sanitised at the boundary instead.
5. **`/session/end` crashed** on a JSON array body.
6. **Tab-teardown destroyed sessions on reload.** `pagehide` fires on refresh and ordinary
   navigation too, so pressing F5 discarded the user's work. Replaced with *release* semantics — see
   below.

### Architecture change made during Phase 1

**`POST /v1/session/release` replaces a destructive teardown beacon.** The browser gives no way to
distinguish a closed tab from a reload, so the beacon now collapses the session (and every object
beneath it) to a ~2-minute grace deadline instead of deleting it. A page that comes back resumes
with its full TTL restored; a tab that is really gone is cleaned up in minutes rather than an hour.
The explicit "End session" control still destroys immediately. Documented in
[API.md](API.md), [ARCHITECTURE.md](ARCHITECTURE.md) §4 and [PRIVACY_ARCHITECTURE.md](PRIVACY_ARCHITECTURE.md) §3.

## In progress

Nothing. Phase 1 is committed.

## Next task — Phase 2 (document processing)

1. Upload endpoint with streaming size enforcement, magic-byte type validation, PDF page limits and
   DOCX decompression bounds
2. Temp-file context manager that deletes in `finally`, including on exception and cancellation
3. PDF extraction via pdfplumber with word-level geometry (feeds column/table detection later)
4. DOCX extraction via python-docx + defusedxml, including header/footer and text-box detection
5. TXT extraction with encoding detection
6. OCR adapter behind an interface, feature-detected, with an honest unavailable state
7. Section detection and the structured `Resume` model with per-field provenance and confidence
8. Session-scoped storage of extracted artefacts, with the compute-once cache key
9. Tests: parser unit tests over synthetic fixtures, upload validation and security tests
   (oversized, MIME spoof, zip bomb, XXE, malformed PDF), and privacy tests proving temp files are
   gone on every path

## Planned

| Phase | Scope |
|---|---|
| 3 | Resume analyzer: health scores, ATS compatibility, formatting, keywords, explainable scoring |
| 4 | Job intelligence: JD parsing, requirement extraction, matching, semantic layer, skill gaps |
| 5 | Resume builder: editor, templates, live preview, AI writing, tailoring, versions, PDF/DOCX export |
| 6 | Career intelligence: cover letters, interview prep, learning priorities |
| 7 | Recruiter screening: bulk async pipeline, extraction, ranking, comparison, shortlist, export |
| 8 | Production hardening: security, rate limits, retries, performance, monitoring, AI evaluation, cost |
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

## Development commands

```bash
# Backend (from backend/)
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
../.venv/Scripts/python.exe -m pytest tests -q
../.venv/Scripts/python.exe -m ruff check app tests
../.venv/Scripts/python.exe -m mypy app

# Frontend (from frontend/)
npm run dev        # http://localhost:3000
npm run test
npm run lint
npm run typecheck
npm run build
```

No Docker, no Redis, no database and no API key is needed to run any of the above.

## Known issues / environment gaps

| Gap | Impact | Handling |
|---|---|---|
| Redis not installed | Redis backend unexercised locally | 10 conformance tests skip with a clear reason; run them with `TEST_REDIS_URL` set. Memory backend covers development |
| Tesseract not installed | OCR cannot run | Phase 2 concern; feature-detected, reported false by `/ready`, honest error rather than silent failure |
| No LLM/embedding key | Layer 3 features cannot run | `/ready` reports `llm: false`; Phases 1–4 do not need it |
| Playwright not installed | PDF export unavailable | Phase 5 concern; `/ready` reports `pdf_export: false` |
| No CI pipeline yet | Gates run locally only | Phase 9 |

## Current blockers

None.

## Open questions (non-blocking; defaults chosen and documented)

1. **Hosting target** — undecided; architecture stays platform-neutral until Phase 9.
2. **LLM credentials** — needed before Phase 5/6 can be exercised end to end, not before.
3. **Session TTL defaults** — 60 min idle / 8 h absolute / 120 s release grace; revisit against real usage.
