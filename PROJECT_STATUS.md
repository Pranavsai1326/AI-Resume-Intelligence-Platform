# PROJECT STATUS

**Last updated:** 2026-08-25 · **Current phase:** Phase 2 complete → Phase 3 ready to start

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

### Phase 2 — Document processing

**Backend** (`backend/app/documents/`, `backend/app/resume/`)

| Area | Delivered |
|---|---|
| Upload validation | Magic-byte type sniffing (PDF/DOCX/TXT), independent of client `Content-Type` or filename; streaming size enforcement that aborts mid-transfer; DOCX zip-bomb defence (entry count, uncompressed-size, per-entry compression-ratio bounds) checked before any XML parser opens the file |
| Temp storage | `SpooledTemporaryFile`-backed bounded buffer; touches disk only past 2 MB, and only inside the session's controlled, janitor-swept temp dir; deleted in `finally` on every path including exceptions |
| PDF extraction | pdfplumber (ADR-0004): text, page count/limit, encryption rejection via pypdf pre-check, and layout heuristics computed from real word geometry — multi-column detection, table detection, image detection, repeating header/footer detection |
| DOCX extraction | python-docx for structural text (paragraphs + tables in document order); `defusedxml` used separately for the security-sensitive raw-XML pass (column count, text-box markers) rather than trusting any one parser |
| TXT extraction | Encoding detection with UTF-8 preference, never raises on odd encodings |
| OCR | Provider abstraction (`OcrProvider` protocol) wired to `NullOcrProvider`; Tesseract is not installed in this environment, so OCR is honestly reported unavailable rather than faked — a document with no extractable text and no OCR fails with `422 NO_EXTRACTABLE_TEXT` |
| Section detection | Deterministic heuristics: canonical keyword table (any casing) plus a narrow ALL-CAPS fallback for unrecognised headers like "Awards" |
| Structure builder | Provenance-tagged `Resume` model (contact, summary, experience, education, skills, projects, certifications, custom sections); every populated field carries `ProvenanceKind.EXTRACTED` with a confidence calibrated to how mechanical its parsing was; date-range parsing that never pads a bare year into a fabricated month |
| API | `POST/GET/DELETE /v1/documents{,/{id}}`; content-hash cache (re-uploading identical bytes is a cache hit, no re-extraction); per-session upload rate limit; session document counter |

**Verification** — all green:

```
backend   230 passed, 10 skipped (Redis, no server present)   ruff clean   mypy --strict clean
```

Also smoke-tested against a running server outside the test harness: upload → get → cache-hit
re-upload → delete, all over real HTTP.

### Defects found and fixed during Phase 2

Development followed a build-then-verify-against-real-input loop; every one of these was caught by
running the pipeline against synthetic fixtures, not assumed correct from reading the code:

1. **The generic "looks like a header" fallback was far too permissive.** It matched ordinary
   title-case content lines — a person's name, a job-title line — as section headers, which
   fragmented the contact block and corrupted experience-entry extraction. Narrowed to known
   keywords (any casing) plus ALL-CAPS only; a title-case custom header that isn't in the keyword
   table is now missed rather than corrupting what surrounds it — a safe failure mode.
2. **Dates on their own line weren't captured.** A common resume layout ("Title, Org" on one line,
   "Jan 2021 - Present" on the next) has no date on the header line itself; the parser only checked
   the header. Fixed by checking whether the *next* line is essentially just a date range.
3. **Certification lines separated by a plain hyphen didn't split into name/issuer.** The splitter
   recognised `|`, `,`, en-dash and em-dash but not a bare `-` surrounded by spaces.
4. **PDF text extraction collapses blank lines between visually separated entries** (a structural
   property of `pdfplumber`, not a bug in it), which silently broke blank-line-based splitting of
   multi-entry sections. Added a fallback: when blank-line splitting yields a single block, a
   non-bulleted line following at least one bulleted line is treated as the start of a new entry.
5. **Rate limiting read the process-global `Settings`** in one code path inherited from Phase 1's
   pattern rather than the request-scoped instance — carried the Phase 1 fix forward correctly on
   review rather than reintroducing it.

Each of these is now a named regression test (`tests/unit/test_sections.py`,
`tests/unit/test_structure.py`) so the specific input that broke it stays covered.

## In progress

Nothing. Phase 2 is committed.

## Next task — Phase 3 (resume analyzer)

1. Resume health score: six sub-scores (ATS compatibility, content quality, skills coverage,
   experience quality, formatting, impact), each with inputs, weights and evidence exposed
2. ATS compatibility analysis building on Phase 2's `LayoutSignals` (multi-column, tables, images,
   repeating header/footer) plus parsing-simulation checks (name/contact/section/date detection)
3. Keyword coverage, action-verb detection, quantification detection — deterministic, Layer 1
4. Explainable scoring engine: configurable weights, per-component evidence, no bare numbers
5. First frontend surface for the document pipeline: an upload UI in the workspace, natural to add
   once there is a real analysis result to show — deferred from Phase 2, which was backend-only by
   design (uploading with nothing to show for it is a worse experience than not offering it yet)
6. Tests: scoring unit tests against fixtures with known expected bands, explainability tests
   (every score traces to evidence), API and privacy tests for the new endpoints

## Planned

| Phase | Scope |
|---|---|
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
| Tesseract not installed | Scanned/image-only PDFs fail with `422 NO_EXTRACTABLE_TEXT` | Provider abstraction built in Phase 2 (`app.documents.extract.ocr`); feature-detected and reported false by `/ready`, honest error rather than silent failure or fake text |
| No LLM/embedding key | Layer 3 features cannot run | `/ready` reports `llm: false`; Phases 1–4 do not need it |
| Playwright not installed | PDF export unavailable | Phase 5 concern; `/ready` reports `pdf_export: false` |
| No CI pipeline yet | Gates run locally only | Phase 9 |

## Current blockers

None.

## Open questions (non-blocking; defaults chosen and documented)

1. **Hosting target** — undecided; architecture stays platform-neutral until Phase 9.
2. **LLM credentials** — needed before Phase 5/6 can be exercised end to end, not before.
3. **Session TTL defaults** — 60 min idle / 8 h absolute / 120 s release grace; revisit against real usage.
