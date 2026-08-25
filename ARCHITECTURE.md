# ARCHITECTURE

**Last updated:** 2026-08-25 (Phase 6) · Companion docs: [PRIVACY_ARCHITECTURE.md](PRIVACY_ARCHITECTURE.md),
[AI_ARCHITECTURE.md](AI_ARCHITECTURE.md), [SECURITY.md](SECURITY.md), [API.md](API.md)

## 1. System shape

```
Browser (Next.js, in-memory state)
        |  X-Session-Id header (opaque, 256-bit)
        v
FastAPI application
 |- API layer            (v1 routers, request validation, error sanitisation)
 |- Session layer        (SessionStore abstraction, TTL, namespace deletion, janitor)
 |- Document layer       (validate -> extract -> layout signals -> sections)
 |- Resume/Job layer     (structured models, provenance, normalisation, taxonomy)
 |- Analysis layer       (ATS, formatting, content, keywords, readability)
 |- Matching layer       (deterministic + semantic + gap analysis)
 |- Scoring engine       (configurable weights, component scores, explanations)
 |- AI service           (prompt registry -> provider adapter -> validation -> guards)
 |- Job queue            (async bulk processing, JobQueue abstraction)
 |- Export layer         (PDF/DOCX generation, streamed, never retained)
        |
        v
Ephemeral store: MemorySessionStore (dev) | RedisSessionStore (prod)   <- TTL on every key
Temp file dir  : 0700, random names, deleted in finally + janitor sweep
```

There is **no application database**. No ORM, no migrations, no user/resume/candidate tables.
See [ADR-0003](docs/adr/0003-no-application-database.md).

## 2. Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 15 (App Router) + TypeScript + Tailwind v4 + shadcn/ui | Required stack; App Router streaming suits long AI operations |
| Client state | Zustand (in-memory) + TanStack Query with bounded `gcTime` | No persistence middleware — resume data never reaches localStorage/IndexedDB |
| Backend | FastAPI + Pydantic v2 on **Python 3.13.5** | Async-first, schema-validated I/O; newest runtime with full wheel coverage here (ADR-0001) |
| Ephemeral store | `SessionStore` protocol: memory (dev) / Redis (prod) | Local env has no Redis or Docker; dev must not require infrastructure (ADR-0002) |
| Async work | `JobQueue` protocol: in-process asyncio pool (dev) / ARQ + Redis (prod) | Bulk screening must never run inside an HTTP request |
| PDF text/layout | pdfplumber + pypdf | MIT/BSD licensing; word-level bounding boxes are what make real column/table detection possible (ADR-0004) |
| DOCX | python-docx + defusedxml | Header/footer/text-box detection needs raw OOXML, parsed safely |
| OCR | pytesseract + Tesseract binary, **optional** | Not installed locally; feature-detected and honestly reported |
| Embeddings | fastembed (ONNX, `bge-small-en-v1.5`) local by default; remote adapter optional | Local inference means resume text never leaves the server for semantic matching (ADR-0005) |
| LLM | Anthropic SDK behind `LLMProvider`; `claude-sonnet-5` reasoning / `claude-haiku-4-5` bulk | Provider-swappable by config; no provider call exists outside `app/ai/` |
| Export | HTML/CSS templates rendered by Chromium (Playwright) for PDF; python-docx for DOCX | Preview and PDF share one template source; output PDFs keep selectable text (ADR-0006) |
| Logging | structlog JSON + PII redaction processor | Policy in [SECURITY.md](SECURITY.md) |

## 3. Repository layout

```
backend/
  app/
    main.py  config.py  logging.py
    api/v1/        session documents analysis jobs match resume ai tailor export career
                   [screening] health
    core/          errors middleware ratelimit clock deps
    sessions/      store.py memory.py redis_store.py manager.py models.py janitor.py
    documents/     upload.py tempfile_scope.py storage.py sections.py structure.py
                   heading_split.py extract/{base,pdf,docx,txt,ocr}.py
    resume/        models.py provenance.py versions.py version_store.py
    analysis/      ats.py formatting.py content_quality.py skills_coverage.py
                   experience_quality.py impact.py engine.py config.py
                   models.py taxonomy.py text_metrics.py scoring_utils.py
    jobs/          models.py parse.py education.py
    matching/      deterministic.py semantic.py gaps.py engine.py
                   embeddings.py config.py models.py learning_priorities.py
    ai/            providers.py prompts.py fact_guard.py rewrite.py tailor.py
                   structured.py cover_letter.py interview.py
                   # LLM only (Phase 5-6) - local embeddings live in matching/embeddings.py (ADR-0005)
    export/        html_template.py pdf.py docx.py
    [screening/     pipeline.py redact.py rank.py compare.py]
    [queue/         base.py inprocess.py arq_queue.py]
  tests/           unit/ integration/ privacy/  fixtures.py  matching_fakes.py  ai_fakes.py
frontend/
  app/  components/  lib/  stores/  hooks/  tests/
docs/adr/
```

Bracketed paths are planned, not yet built — see PROJECT_STATUS.md for what phase adds each one.
`documents/` and `resume/` hold Phase 2 code plus Phase 5's versioning (`versions.py`,
`version_store.py`): upload validation and bounded temp storage, per-format extraction (PDF via
pdfplumber, DOCX via python-docx + defusedxml, TXT), deterministic section detection, the
provenance-tagged structured-resume builder, and immutable in-session resume snapshots.
`analysis/` holds Phase 3: six independently-scored components (`ats.py`, `content_quality.py`,
`experience_quality.py`, `skills_coverage.py`, `formatting.py`, `impact.py`) sharing
`text_metrics.py` (bullet/verb/quantification detection) and `taxonomy.py` (curated word lists),
orchestrated by `engine.py` against the weights in `config.py`. `jobs/` and `matching/` hold
Phase 4: deterministic JD parsing (`jobs/parse.py`, sharing `documents/heading_split.py`'s generic
header-splitting algorithm with resume section detection), the local embedding provider
(`matching/embeddings.py`, ADR-0005), four deterministic and two semantic match components, and
skill-gap analysis (`matching/gaps.py`). `ai/` and `export/` are Phase 5: the LLM provider
abstraction, prompt registry and fact guard (`ai/providers.py`, `ai/prompts.py`,
`ai/fact_guard.py`), AI-assisted rewriting and tailoring (`ai/rewrite.py`, `ai/tailor.py`, the
first real consumers of Layer 3), and PDF/DOCX export (`export/pdf.py` via headless Chromium per
ADR-0006, `export/docx.py` via python-docx, sharing one HTML template source in
`export/html_template.py`). Phase 6 added career intelligence on the same foundation: a shared
JSON-in-prompt structured-output helper (`ai/structured.py`) plus cover letters and interview
prep (`ai/cover_letter.py`, `ai/interview.py` — the first features needing multi-field LLM
output rather than one plain string), and `matching/learning_priorities.py` (pure Layer 1,
reordering Phase 4's skill gaps, no LLM involved). The originally-planned single `scoring/` module never materialised as
a separate package - each domain (`analysis/`, `matching/`) keeps its own `config.py` /
`engine.py`, sharing only the actually-common piece,
`analysis/scoring_utils.apply_degrade_and_renormalize`, since a resume-health profile and a
match profile have entirely different component sets and no other logic to share. Rule: no
source file over ~400 lines. A module that outgrows
it is split by responsibility.

## 4. Session model

```json
{
  "session_id":       "<32 random bytes, base64url>",
  "created_at":       "2026-08-22T10:00:00Z",
  "last_activity_at": "2026-08-22T10:12:31Z",
  "expires_at":       "2026-08-22T11:12:31Z",
  "hard_expires_at":  "2026-08-22T18:00:00Z",
  "mode":             "candidate | recruiter",
  "counters":         { "documents": 3, "ai_calls": 11 },
  "released":         false
}
```

* `session_id` is an opaque random token, not a user identifier, and is never reused for analytics.
* Sliding idle TTL (default 60 min) refreshed on activity; absolute cap (default 8 h) never extends.
* Every object lives under `sess:{session_id}:{kind}:{object_id}` and **every key carries its own
  TTL**, so expiry stays correct even if the metadata key is lost — no orphans by construction.
* `DELETE /v1/session` destroys the whole namespace synchronously.
* `POST /v1/session/release` collapses the session to a short grace window when the client
  page goes away. Deliberately not a destroy - `pagehide` cannot distinguish a closed tab
  from a reload. Object TTLs collapse with it and are restored if the user returns.
* Session IDs are never logged in full (first 8 characters only, for correlation).

## 5. Data flow — candidate

```
Upload  -> validate (magic bytes, size, page/entry limits)
        -> extract text + layout signals   [bytes held in memory; disk only if size forces it]
        -> section detection -> structured Resume (provenance-tagged)
        -> store in session (TTL) -> embed once (sections + skills) -> store vectors (TTL)
        -> deterministic analysis -> optional LLM narrative
        -> JD paste/upload -> requirement extraction
        -> match: deterministic + semantic components -> scoring engine -> explanation
        -> tailoring proposals (fact-guarded) -> accepted edits mutate the session resume only
        -> export: render in memory -> stream -> discard
```

Parse once, structure once, embed once, reuse everywhere (see [AI_ARCHITECTURE.md](AI_ARCHITECTURE.md) §6).

## 6. Data flow — recruiter

```
JD upload   -> requirement extraction -> requirement vector set
Bulk upload -> enqueue N jobs (JobQueue) -> bounded-concurrency workers
   per job: validate -> extract -> structure -> redact protected attributes
            -> embed -> match -> component scores
Client polls job state: PENDING -> PROCESSING -> COMPLETED | FAILED | RETRYING
Ranking     = sort by scoring-engine overall, per-candidate evidence retained in session
Comparison  = matrix over stored component scores (no recomputation, no extra LLM calls)
Export      = report rendered on demand, streamed, discarded
Session end = every candidate's data destroyed with the namespace
```

## 7. Scoring engine

Configuration-driven; weights never hardcoded at call sites. Built in Phase 3 for resume health
(`app/analysis/config.py`: `ats_compatibility`, `content_quality`, `experience_quality`,
`skills_coverage`, `formatting`, `impact` — weights sum to 1.0, validated at construction) and
reused unchanged for job matching in Phase 4:

```yaml
match_profile_default:  # Phase 4 - not yet built
  required_skills:    0.40
  preferred_skills:   0.15
  experience:         0.20
  education:          0.05
  project_relevance:  0.10
  semantic_relevance: 0.10
```

* Each component returns `{score, weight, evidence[], explanation, availability}`.
* If a component is unavailable (e.g. no embedding backend), its weight is redistributed
  proportionally and the response carries `degraded: ["semantic_relevance"]`, which the UI **must**
  render. Scores never silently change meaning.
* Overall = weighted sum of available components. **The LLM never produces the number.** It produces
  prose that is displayed next to numbers it did not compute.

## 8. Async processing

`JobQueue` protocol: `enqueue(job) -> job_id`, `get(job_id) -> JobState`, `cancel(job_id)`.
States: `PENDING -> PROCESSING -> COMPLETED | FAILED | RETRYING`. Retries apply only to idempotent
stages (extraction, embedding, scoring) with capped exponential backoff. Every job is session-scoped
and inherits the session TTL: when a session expires, its queued jobs are cancelled and their inputs
dropped.

## 9. Failure posture

Every external dependency is assumed to fail. Each has a defined, honest degradation:

| Dependency down | Behaviour |
|---|---|
| LLM provider | Deterministic analysis, matching and scoring still work; AI narrative/generation returns an explicit unavailable state |
| Embedding runtime | Semantic components marked unavailable; weights renormalised with disclosure |
| OCR binary | Image-only PDFs rejected clearly: "no extractable text, and OCR is unavailable" |
| Chromium renderer | DOCX and HTML export still offered; PDF export reports unavailable |
| Redis (prod) | Readiness fails and new sessions are refused, rather than silently falling back to memory |
| Worker | Job moves to FAILED with a retryable flag; partial bulk results remain usable and are labelled partial |

## 10. Health and observability

`/health` (liveness, no dependency checks) and `/ready` (session store reachable, embedding runtime
loaded, capability map). Metrics are content-free: API latency, error rate by category, queue depth,
worker failures, processing duration, AI latency, token counts, temp-storage bytes, cleanup
success/failure, active session count. No metric or log line carries resume content.

## 11. Configuration

Pydantic `Settings` sourced from environment; secrets only from environment or a secret manager,
never committed. Key knobs: `SESSION_IDLE_TTL_SECONDS`, `SESSION_ABSOLUTE_TTL_SECONDS`,
`SESSION_STORE_BACKEND`, `REDIS_URL`, `MAX_UPLOAD_BYTES`, `MAX_PDF_PAGES`, `MAX_BULK_RESUMES`,
`LLM_PROVIDER`, `LLM_MODEL_REASONING`, `LLM_MODEL_BULK`, `EMBEDDING_BACKEND`, `OCR_ENABLED`,
`RATE_LIMIT_*`, `CORS_ORIGINS`.

Configuration is validated at startup and the app **refuses to boot** on unsafe production
combinations — memory session store with multiple workers, wildcard CORS with credentials, or a
missing `REDIS_URL` when the Redis backend is selected.
