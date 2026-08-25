# PROJECT STATUS

**Last updated:** 2026-08-25 · **Current phase:** Phase 5 complete → Phase 6 ready to start

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

### Phase 3 — Resume analyzer

**Backend** (`backend/app/analysis/`)

| Area | Delivered |
|---|---|
| Scoring engine | `compute_resume_health(resume, layout, profile)` orchestrates six independently-scored components into one weighted overall; weights come from a validated `ScoringProfile` (must cover exactly the six known components, must sum to 1.0), never hardcoded at a call site |
| ATS Compatibility | Parsing simulation (name/email/phone/experience/dates detectable by our own extractor) plus formatting risk from Phase 2's `LayoutSignals` (multi-column, tables, images, text boxes, repeating header/footer) |
| Formatting | Standard-section presence, bullet-backed experience entries, page-length signal where measurable (PDF only — DOCX/TXT are not penalised for a property they cannot express) |
| Content Quality | Weak/passive phrasing, first-person pronouns, action-verb-opening ratio, bullet length, over shared bullet-extraction and lexicon helpers (`text_metrics.py`, `taxonomy.py`) |
| Skills Coverage | Section presence, breadth, categorisation, and whether listed skills are also demonstrated in experience bullets; a curated skills taxonomy adds positive credit only — an unrecognised skill is never penalised |
| Experience Quality | Bullets-per-role, date completeness, quantification and action-verb ratios per role |
| Impact | Quantified-detail density and outcome-verb ratio across every bullet, plus a volume signal so a one-bullet resume cannot score as "high impact" by chance |
| Every component | Returns `{score, weight, evidence[], explanation, available}`; every evidence item is `positive`, `info` or `warning` with a concrete message — no score is ever returned bare |
| Degrade/renormalise | Built even though nothing degrades yet (every component here is deterministic, Layer 1, no external dependency) — so a future component needing an external dependency (e.g. semantic relevance in Phase 4) degrades the identical way rather than as a special case |
| API | `POST /v1/analysis/resume` (body `{document_id}`) and `GET /v1/analysis/{analysis_id}`; analysis is compute-once and session-cached per document, mirroring the Phase 2 upload cache |

**Frontend** (`frontend/components/analysis/`)

The first real feature surface, added now rather than in Phase 2 because uploading with nothing
to show for it is a worse experience than not offering it yet. Drag/click upload → real-time
summary of what was extracted → "Analyze resume health" → full report: overall score and band,
six component cards (score bar + expandable evidence), the lowest-scoring component pre-expanded
so the reader's eye goes straight to what needs attention. Wired into the candidate workspace.

**Verification** — all green:

```
backend    287 passed, 10 skipped (Redis, no server present)   ruff clean   mypy --strict clean
frontend   24 passed   eslint clean   tsc --noEmit clean   next build clean
```

Also verified live end to end: a synthetic resume was uploaded through the real running frontend
(via the actual `File`/`fetch` code path, not a mock) against the real running backend, producing
an overall score of 90 ("Strong") with all six components rendered and the correct component
pre-expanded — plus confirmed `localStorage` stays empty throughout.

### Defects found and fixed during Phase 3

1. **Wrong grammatical article** ("A experience section", "A education section") in Formatting's
   evidence messages — user-facing text, fixed to use the correct article per section.
2. **Singular/plural verb agreement** in two evidence messages ("1 work experience entry *were*
   detected", "1 bullet *use* first-person pronouns") — found by an adversarial single-entry test
   fixture, fixed to compute noun/verb agreement from the count.

Both were caught by manually inspecting real component output against synthetic fixtures — not
things a type checker or a passing assertion would have caught, which is why the models were
smoke-tested against printed output before the formal test suite was written.

### Phase 4 — Job intelligence

**Backend** (`backend/app/jobs/`, `backend/app/matching/`)

| Area | Delivered |
|---|---|
| JD parsing | Deterministic (`app/jobs/parse.py`): title extraction, section detection reused from resume parsing via a newly-shared `app.documents.heading_split` module, requirements split into required/preferred/responsibilities/ignored, each requirement classified as skill / soft-skill / experience / education / certification with years and education-level extraction |
| Skill matching | Word-boundary-safe skill detection (`app.analysis.taxonomy.contains_skill_mention`) — fixes a real substring-matching bug (see Defects below) shared by JD keyword extraction, resume skills-coverage grounding, and gap analysis |
| Embeddings | `app/matching/embeddings.py`: `EmbeddingProvider` protocol, `NullEmbeddingProvider`, and a real `FastEmbedProvider` (fastembed, `bge-small-en-v1.5`, ADR-0005) as a lazily-loaded process singleton. `EMBEDDING_BACKEND` now defaults to `fastembed` (was `none` in Phase 1, before any real consumer existed); `/ready` reports package-presence honestly, the provider itself reports whether the model actually loaded |
| Deterministic components | Required Skills, Preferred Skills, Experience (years, summed per role), Education (highest level detected vs. required) — always available, no external dependency |
| Semantic components | Project Relevance, Semantic Relevance — need the embedding provider; report `available: false` and exercise the degrade/renormalise path Phase 3 built but never triggered, when the model can't load |
| Skill gaps | Strong / Moderate / Missing / Insufficient-Evidence buckets (`app/matching/gaps.py`); the fourth bucket needs the semantic layer to distinguish "no evidence at all" from "something plausibly related is listed" — falls back to a coarser Strong/Moderate/Missing without it |
| API | `POST/GET /v1/jobs{,/{id}}`, `POST /v1/match` (one endpoint computing all six components plus skill gaps together, not the two speculative endpoints Phase 0 sketched — gap analysis reuses the same checks the scores already compute), both cached per-session |

**Frontend**: extends the Phase 3 analyzer — after a resume is analyzed, an optional "Match
against a job" panel accepts pasted JD text and renders the full match report (score bars,
evidence, skill-gap buckets) using UI components refactored to be shared between resume-health
and job-match display (`components/analysis/component-score-list.tsx`).

**Verification** — all green:

```
backend    378 passed, 10 skipped (Redis, no server present)   ruff clean   mypy --strict clean
frontend   28 passed   eslint clean   tsc --noEmit clean   next build clean
```

The real fastembed model was exercised, not mocked: `tests/unit/test_embeddings.py` loads the
actual ONNX model (skips gracefully if it cannot - offline, no cache yet) and asserts related
professional text scores meaningfully higher than unrelated text. The rest of the suite uses a
deterministic fake provider (`tests/matching_fakes.py`) so it stays fast and hermetic; the default
`client`/`settings` test fixtures run with `embedding_backend="none"`, so every integration test
genuinely exercises the degrade path rather than assuming it. Also verified live end to end
through the real running frontend against the real running backend, with real embeddings: upload
→ analyze → paste a JD → match → skill gaps, including a correct semantic upgrade of "Terraform"
to "worth confirming" based on Kubernetes/AWS already being listed.

### Defects found and fixed during Phase 4

1. **Naive substring skill matching was a real bug, not a style nit.** `skill in text` matched
   "r" (the language) inside "your"/"were"/"programmer" and "go" inside "google"/"algorithm" -
   caught while smoke-testing JD parsing output, where "Strong communication skills" was
   misclassified as containing the skills "r" and "go". Fixed with word-boundary matching
   (`app.analysis.taxonomy.contains_skill_mention`), which also fixed a latent instance of the
   same bug in Phase 3's `skills_coverage.py` grounding check.
2. **Taxonomy design overlap**: soft-skill words ("leadership", "communication") lived in the
   same `COMMON_SKILLS` set as technical skills, which silently broke JD requirement
   classification (a requirement matching both a soft skill and a "skill" always resolved to
   the technical branch). Split into `COMMON_SKILLS` and a new `SOFT_SKILLS` set.
3. **`ComponentScore.weight` was documented as "post-renormalisation" but never actually
   rewritten** by Phase 3's engine - harmless there since nothing ever degraded, but would have
   silently misreported weights the moment a match component genuinely went unavailable. Fixed
   with a shared `apply_degrade_and_renormalize` helper, applied retroactively to the resume-
   health engine too so both report weights consistently.
4. **The `insufficient_evidence` semantic threshold was miscalibrated on first measurement.**
   Bare single-word embeddings ("communication" vs "Go") cluster at 0.55-0.65 regardless of
   actual relatedness, which would have made the skill-gap semantic upgrade fire on noise.
   Measured real similarity scores for related vs. unrelated short phrases before picking a
   threshold (0.68), and switched from bare keywords to full-phrase context, which meaningfully
   improved discrimination (0.68-0.73 for genuinely related pairs vs. 0.52-0.57 for unrelated).
5. **Two-entry education sections without a blank line between them collapse into one entry** -
   a real, narrow Phase 2 parser gap surfaced by a Phase 4 test (education entries have no
   bullets, so the PDF-blank-line-collapse fallback that rescues multi-entry experience/project
   sections has nothing to anchor on). Documented rather than patched under time pressure this
   late in the phase; tracked below.

### Phase 5 — Resume builder, AI-assisted writing, tailoring, export

**Backend** (`backend/app/resume/`, `backend/app/ai/`, `backend/app/export/`)

| Area | Delivered |
|---|---|
| Versioning | Immutable `ResumeVersion` snapshots (`app/resume/versions.py`) — every save is a new version, never an in-place mutation, so before/after is always available. `VersionSource`: `original` / `manual_edit` / `ai_tailored`. Shared session-storage index (`app/resume/version_store.py`) lazily creates an "Original" version from the uploaded document's structured resume the first time it's needed, rather than eagerly at upload time |
| LLM provider abstraction | `app/ai/providers.py`: `LLMProvider` protocol, `NullLLMProvider` (first-class, not a fallback hack — every call honestly returns unavailable), `AnthropicProvider` (vendor SDK confined here, feature-detected like OCR and embeddings before it). `get_llm_provider(settings)` returns Null unless `LLM_PROVIDER=anthropic` and a key is configured |
| Prompt registry | `app/ai/prompts.py`: versioned `PromptSpec` records (system prompt, token budgets, temperature) for bullet rewrite, summary rewrite, and tailoring — prompts as data, not inline strings, sharing one explicit anti-invention instruction |
| Fact guard | `app/ai/fact_guard.py`: builds a `FactIndex` (numbers + notable words) from the user's own resume content and flags any number, organisation, or technology in generated text that doesn't appear in the source — a code-level control, not just a prompt instruction (AI_ARCHITECTURE.md section 5) |
| AI rewriting | `app/ai/rewrite.py`: `rewrite_bullet` / `rewrite_summary` return a proposal (before/after, fact-guard findings, `available`), never mutate the resume directly |
| Tailoring | `app/ai/tailor.py`: two layers — deterministic (always available: reorder skill groups so job-relevant skills lead; surface reminders for required skills with no evidence, never auto-added) and AI-assisted (needs a configured LLM: re-emphasise bullets already mentioning a job-relevant keyword, capped at `MAX_BULLET_REWRITES = 3` for token discipline). `apply_proposals` is a separate, explicit step — nothing is applied until the user accepts |
| Export | `app/export/html_template.py` (shared HTML/CSS template, all content HTML-escaped), `app/export/pdf.py` (headless Chromium via Playwright, ADR-0006, offline browser context, `set_content` never `goto`, returns `None` honestly if Chromium isn't available), `app/export/docx.py` (python-docx object API, no raw XML, no injection surface) |
| API | `GET/POST /v1/resume/versions`, `GET /v1/resume/versions/{id}`, `POST /v1/ai/rewrite`, `POST /v1/tailor`, `POST /v1/tailor/apply`, `POST /v1/export` (`{document_id, version_id?, format: "pdf"\|"docx"}` → streamed binary with a filename derived from an `[A-Za-z0-9-]` allowlist, never the raw label) |

**Frontend** (`frontend/components/builder/`)

Resume builder UI: `section-editor.tsx` (add/edit/delete per section, plus move-up/move-down
buttons for reordering — up/down buttons chosen deliberately over drag-and-drop, for simplicity,
accessibility and no new dependency), `resume-preview.tsx` (live preview as the user edits),
`version-switcher.tsx` (lists version lineage: label, source, created-at, based-on),
`ai-rewrite-control.tsx` ("Improve with AI" on the summary and on individual bullets — shows the
honest "AI writing is not configured on this deployment" state calmly, as an expected state, not
an error; when available, shows before/after with fact-guard findings surfaced, never hidden),
`tailor-panel.tsx` (generate proposals against a job, accept/reject each with rationale and
before/after, apply only the accepted ones), `export-buttons.tsx` (PDF/DOCX, downloads using the
server's `Content-Disposition` filename). `lib/api-client.ts` extended with typed calls for all
five new endpoints.

**Verification** — all green:

```
backend    460 passed, 10 skipped (Redis, no server present)   ruff clean   mypy clean
frontend   34 passed   eslint clean   tsc --noEmit clean   next build clean
```

Playwright's Chromium is installed in this environment, so PDF export was verified rendering real
output (`tests/unit/test_export_pdf.py`), not just mocked — a change from the Phase 4-era
assumption that it wouldn't be available; `/ready` now reports `pdf_export: true`.

### Defects found and fixed during Phase 5

1. **Fact-guard sentence-initial false positive.** The proper-noun/technology heuristic (a
   capitalised word not in the source) flagged the first word of every generated sentence, since
   English capitalises sentence-initial words regardless of whether they're proper nouns — this
   would have made nearly every AI rewrite trip at least one false warning. Fixed by excluding
   position-0 matches from the capitalisation signal (digit/symbol-based detection, e.g. "AWS123"
   or "C++", still applies regardless of position). Verified with a regression test: an honest
   rewrite produces zero findings; a genuine mid-sentence fabrication is still caught.
2. **`anthropic` SDK 1.0.0's `messages.create()` does not accept `temperature` as a typed keyword
   argument** — confirmed via `inspect.signature()` at runtime, not assumed from a stub gap. Fixed
   by passing it through `extra_body={"temperature": temperature}`, which merges into the raw JSON
   request body regardless of what the Python wrapper's typed surface exposes; the underlying
   Messages API has always accepted `temperature` as a top-level field.

## In progress

Nothing. Phase 5 is committed.

## Next task — Phase 6 (career intelligence)

1. Cover letter generation grounded in session facts (resume + JD), fact-guarded the same way as
   tailoring
2. Interview preparation: question set with a "why this is asked" rationale per question, traced
   to a resume or JD span
3. Learning/skill-gap priorities derived from Phase 4's skill-gap buckets
4. Fix the Phase 2 education multi-entry-without-blank-line gap (still open — see Known Issues);
   the builder UI shipped in Phase 5 is where a user would notice a collapsed entry, so this is a
   good point to revisit it
5. Tests: AI-unavailable fallback, fact-guard catch rate against deliberately hallucinated
   samples, API and privacy tests for the new endpoints

## Planned

| Phase | Scope |
|---|---|
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
| No LLM key | Layer 3 (AI writing, tailoring, cover letters, interview prep) cannot run | `/ready` reports `llm: false`. `NullLLMProvider` reports every AI feature honestly unavailable rather than erroring or fabricating; deterministic tailoring (skill reordering, requirement reminders) works with no key at all. Semantic matching (Phase 4) needed no key and is confirmed working — ADR-0005's bet on local ONNX embeddings paid off |
| Education entries without a blank line between them collapse into one | Rare, narrow resume-parsing gap (Phase 2) surfaced by a Phase 4 test | Still documented, not yet fixed; queued for Phase 6 |
| No CI pipeline yet | Gates run locally only | Phase 9 |

## Current blockers

None.

## Open questions (non-blocking; defaults chosen and documented)

1. **Hosting target** — undecided; architecture stays platform-neutral until Phase 9.
2. **LLM credentials** — needed before Phase 5/6 can be exercised end to end, not before.
3. **Session TTL defaults** — 60 min idle / 8 h absolute / 120 s release grace; revisit against real usage.
