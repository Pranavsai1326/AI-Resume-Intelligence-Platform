# PROJECT STATUS

**Last updated:** 2026-08-25 · **Current phase:** Phase 9 complete (9A–9J). Live Gemini verification done; no staging/production deployment exists yet - see "Production readiness" below

**Phase 9 was revised** after Phase 8 shipped: see [PHASE_9_IMPLEMENTATION_PLAN.md](PHASE_9_IMPLEMENTATION_PLAN.md)
for the full sub-phase breakdown (9A architecture baseline → 9B privacy/consent → 9C extraction
reliability → 9D extraction review UI → 9E frontend redesign → 9F Gemini AI integration → 9G
bounded AI career workflow → 9H full product QA → 9I CI/security/deployment → 9J final
acceptance). The original "Phase 9 = deployment only" scope below is superseded by that plan;
deployment work now lives in 9I.

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

### Phase 6 — Career intelligence

**Backend** (`backend/app/ai/`, `backend/app/matching/`)

| Area | Delivered |
|---|---|
| Structured LLM output | `app/ai/structured.py`: JSON-in-prompt output (the prompt asks for JSON directly, rather than a provider-specific tool-use feature) with strict parse → Pydantic schema validate → one bounded repair attempt → honest `None` on failure. Chosen over Anthropic tool-use so `LLMProvider` stays a plain text-completion interface any provider can implement (see Decisions below) |
| Cover letters | `app/ai/cover_letter.py`: a `{salutation, body_paragraphs, closing}` proposal grounded in the resume and the job's title/requirements, fact-guarded before it's ever returned. Never invents a company or hiring-manager name — addresses generically unless one is actually given |
| Interview prep | `app/ai/interview.py`: 5-8 questions, each with a `category` (behavioral/technical/situational/role_fit), a rationale, and a `grounded_in` span — not a generic question bank. The rationale of every question is itself fact-guarded |
| Fact guard, widened | `app/ai/fact_guard.py`'s `FactIndex.build` now takes an optional `job: JobDescription` — the job's title/requirements/responsibilities are legitimate context (the user's own JD, not a claim about the candidate), so referencing them verbatim in a cover letter or interview question is never flagged. Widening only adds allowed terms; it never suppresses a genuine resume-fact violation |
| Learning priorities | `app/matching/learning_priorities.py`: pure Layer 1 — reorders Phase 4's skill-gap buckets into a ranked "what to learn next" list (required before preferred; within the same importance, a flat miss before "worth confirming" before partial evidence). Needs no LLM, no key, nothing new to compute |
| API | `POST /v1/cover-letter`, `POST /v1/interview/questions`, `POST /v1/learning-priorities` — all three take `{document_id, job_id, version_id?}`, reusing Phase 5's versioned resumes and Phase 4's job/skill-gap machinery rather than introducing a new persistence kind |
| Parser fix | Fixed the Phase 2 gap noted since Phase 4: two education entries with no blank line between them (a PDF-extraction artefact) used to collapse into one, because the bullet-boundary fallback that rescues multi-entry experience/project sections has nothing to anchor on for education, which is usually bullet-free. A degree line ("B.S. Computer Science") is now recognised as education's equivalent anchor — it closes out the entry it belongs to, so the next line (or the next degree line, for the "Institution, Degree" single-line-per-entry format) correctly starts a new one. `app/documents/structure.py::_split_education_entries` |

**Frontend** (`frontend/components/builder/career-panel.tsx`)

One "Career intelligence" panel, added below tailoring in the resume builder: paste a job
description once, then three cards — cover letter and interview prep (Layer 3, showing the same
calm "AI writing is not configured" state as Phase 5's AI controls when no key is set, and
surfacing fact-guard findings directly rather than hiding them), and learning priorities (Layer 1,
works immediately with no key, ranked with a plain-language reason per item).

**Verification** — all green:

```
backend    495 passed, 10 skipped (Redis, no server present)   ruff clean   mypy clean
frontend   37 passed   eslint clean   tsc --noEmit clean   next build clean
```

Verified live against a running frontend and backend: workspace loads with the updated "Phase 6
of the build is live" banner and zero console errors; `/ready` capabilities render correctly
(`llm: not configured`, `pdf export: available` — Playwright's Chromium is genuinely installed in
this environment). Full click-through of the career panel itself (paste JD → generate → review)
was not driven through the browser automation tool available this session, since it has no
file-picker support to get past the upload step that gates the builder — covered instead by the
unit, integration, and privacy test suites, matching the same limitation noted for Phase 5.

### Defects found and fixed during Phase 6

1. **Fact guard's word-matching regex included a trailing sentence period in the matched token**
   (`_WORD_RE`'s allowed-character class includes `.`, needed for tokens like "Node.js"), so a
   sentence-ending mention of an already-known term — e.g. "...experience with Kubernetes." —
   compared "kubernetes." against the index's "kubernetes" and never matched, producing a false
   positive on ordinary, fully-grounded generated text. Caught while writing the cover-letter
   test for "a grounded letter has zero fact-guard findings," which failed on first run. Fixed by
   stripping a trailing period the same way trailing punctuation is already stripped off numbers;
   an internal period ("Node.js" mid-sentence) is untouched since only the match's *last*
   character is trimmed.
2. **The Phase 2 education multi-entry-without-blank-line parser gap**, open since Phase 2 and
   explicitly deferred through Phases 4 and 5 — see Backend row above.

### Decisions made during Phase 6

**JSON-in-prompt over Anthropic tool-use for structured output.** Cover letters and interview
questions are the first features needing multi-field output (Phase 5's rewriting only ever
returned one plain string). Considered forcing a tool call via the Anthropic SDK's tool-use
feature for a stronger shape guarantee, but that would tie `LLMProvider`'s contract to a
capability not every provider implements the same way, adding a second integration surface to
maintain. Asking for JSON in the prompt and validating what comes back keeps the provider
abstraction as plain text completion; the cost is needing a parse-and-repair step, built once in
`app/ai/structured.py` and reused by both callers.

### Phase 7 — Recruiter screening

**Backend** (`backend/app/queue/`, `backend/app/screening/`)

| Area | Delivered |
|---|---|
| Async job queue | `app/queue/base.py` (`JobQueue` protocol, `JobState`: pending/processing/completed/failed/retrying) and `app/queue/inprocess.py` (`InProcessJobQueue` - dev-appropriate, no Redis: a bounded `asyncio.Semaphore` pool, one retry on failure with a fixed content-free error category, never the raw exception). One instance lives on `app.state.job_queue`, matching how the session store and rate limiter are already wired |
| Redaction | `app/screening/redact.py`: direct identifiers (name, email, phone, links) are cleared structurally, since Phase 2 already isolates them in `ContactInfo`; a photo is never present to redact because extraction never captures one in the first place. Everything else PRD section 8 lists (gender, marital status, nationality, religion, race/ethnicity, age/DOB) has no isolated field, so a curated, disclosure-label-first pattern set scrubs free text - summary, bullets, education/project details. Deliberately narrow like `analysis/taxonomy.py`'s word lists: favours "Nationality:"-shaped disclosure labels over broad demonym lists, to keep the false-positive risk on company/technology names low |
| Per-candidate pipeline | `app/screening/pipeline.py::process_candidate`: validate (magic-byte sniff) → extract → structure → **redact → match**, in that order, so scoring always runs against the redacted resume, never the original - honest ordering, not just incidentally safe (the scoring engine doesn't read contact info either way). CPU-bound stages run via `asyncio.to_thread` so one slow candidate never blocks the whole worker pool |
| Ranking & comparison | `app/screening/rank.py` (sort/filter/paginate over already-computed `overall` scores - ranking order is always Layer 1, AI_ARCHITECTURE.md section 9) and `app/screening/compare.py` (a matrix over stored component scores, no recomputation) |
| API | `POST /v1/screening`, `POST /v1/screening/{id}/candidates` (bulk multipart, 202 Accepted - returns immediately with candidate ids to poll), `GET /v1/screening/{id}/status`, `GET /v1/screening/{id}/ranking`, `GET /v1/screening/{id}/candidates/{cid}`, `POST /v1/screening/{id}/compare`, `POST /v1/screening/{id}/shortlist` |
| Blind review | The *only* resume ever stored per candidate is the redacted one (`CandidateResult.resume`) - there is no unredacted version anywhere in the session for a future ranking or comparison view to accidentally surface. Blind review by construction, not a display-time filter |

**Frontend** (`frontend/components/screening/`)

`screening-workspace.tsx`: paste a job description once, upload a candidate batch, watch it
process live (genuine polling against `GET .../status`, not a simulated progress bar), then rank,
open a candidate's full explainable breakdown (`candidate-detail.tsx`, reusing the same
`JobMatchReport` a single candidate sees of their own match, plus `ResumePreview` for the redacted
resume), select several for a side-by-side `comparison-matrix.tsx`, and shortlist.

**Verification** — all green:

```
backend    530 passed, 10 skipped (Redis, no server present)   ruff clean   mypy clean
frontend   42 passed   eslint clean   tsc --noEmit clean   next build clean
```

Verified live: created a recruiter session, pasted a job description, and confirmed
`POST /v1/screening` genuinely creates a screening context end to end against a running backend
(caught and fixed a stale-backend-process bug in the process - see Defects below). Full
click-through of bulk candidate upload wasn't driven through the browser automation tool available
this session, since it has no file-picker support - covered instead by the integration test suite,
which polls a real background `asyncio` task to completion the same way a real client would
(`tests/integration/test_screening_api.py`), not a mocked queue.

### Defects found and fixed during Phase 7

1. **Live smoke-testing against a stale backend process.** A backend process left running from
   earlier in the session (before this phase's code existed) was still bound to port 8000;
   `POST /v1/screening` 404'd against it. Not a code defect, but a reminder that "restart the
   server" means confirming the *new* code is actually running - `curl .../openapi.json` was used
   to verify the route existed before concluding anything about the endpoint itself.
2. No code defects found by the test suite this phase - the queue's retry/failure paths, the
   redaction patterns, and the full async upload→poll→rank→compare→shortlist flow all passed on
   first correct implementation, verified by tests written to fail if they didn't (e.g. asserting
   `attempts == 2` for a job that fails once then succeeds, not just "eventually completes").

### Known limitation

**Job cancellation on session destroy is passive, not active.** `DELETE /v1/session` deletes the
session's store namespace but does not reach into the job queue to cancel any of that session's
still-running candidate jobs (`JobQueue.cancel` exists but nothing calls it from session
lifecycle). In practice this is bounded, not unsafe: a job that finishes after its session was
destroyed calls `SessionManager.put_object` with an already-captured `SessionMeta` snapshot, which
does not re-check whether the underlying namespace still exists - the write can succeed and leave
an orphaned key, but that key carries the same TTL every session object already carries
(`CANDIDATE_TTL_SECONDS = 3600`) and is never reachable through the API regardless, since every
request for the destroyed session id fails session resolution before any handler runs
(`test_screening_data_is_destroyed_with_the_session` proves this reachability guarantee, not
instant store-level deletion). Worst case: an unreachable key lingers up to an hour, the same
bound Redis TTL expiry already relies on elsewhere - not a new privacy exposure, but an honest gap
between "destroyed" and "instantly purged from the store" worth closing by wiring session destroy
to `JobQueue.cancel` for any of that session's in-flight job ids. Tracked for Phase 8.

### Phase 8 — Production hardening

Not a new feature - a review pass over everything built so far, verifying claims already made in
SECURITY.md and ARCHITECTURE.md against what the code actually does, and closing what didn't
hold up. Six real defects were found this way, not assumed away.

| Area | What was found and fixed |
|---|---|
| Job cancellation gap (Phase 7's documented known limitation) | `DELETE /v1/session` now calls `JobQueue.cancel_for_session` before destroying the namespace. `JobQueue.enqueue` gained an optional `session_id` tag and `InProcessJobQueue` tracks a `session_id -> job_ids` index so cancellation can find the right jobs; `cancel_for_session` consumes (pops) that index so a repeat call is a no-op, not a double-cancel |
| Missing runtime dependencies | `backend/pyproject.toml`'s `dependencies` list never actually included `anthropic` or `playwright`, despite both being genuinely imported at runtime since Phases 5 - the project only worked because they happened to already be installed in this dev venv. A fresh clone + `pip install -e .` would have silently lost AI writing and PDF export (both "honestly unavailable" rather than crashing, which is exactly why nobody had noticed). Fixed by adding both |
| No backend dependency lockfile | `pyproject.toml` only declares floating `>=` lower bounds; no `uv.lock`/`requirements.txt`/equivalent exists. SECURITY.md previously claimed pinned lockfiles for "both stacks" - false for the backend. Documented honestly rather than manufactured under time pressure; adopting `uv` or pip-tools is tracked for Phase 9 |
| No automated dependency audit | SECURITY.md claimed CI runs `pip-audit`/`npm audit` - false, there is no CI pipeline at all yet. Ran both manually instead: `pip-audit` found nothing in the backend; `npm audit --audit-level=high` found 3 real high-severity advisories in `next`'s transitive `postcss`/`sharp` deps, fixable only via a breaking `next` major-version bump - not force-upgraded on the spot given no dedicated regression budget this session; `pip-audit` is now a declared dev dependency so re-running it is intentional, not ad hoc |
| Prompt injection mitigation was claimed but not implemented | SECURITY.md said "system prompts state that document content is never an instruction" - none of the five actual prompts in `app/ai/prompts.py` said any such thing. Added a shared `_IGNORE_EMBEDDED_INSTRUCTIONS` clause to all five (bumped `1.0.0` -> `1.1.0` per the module's own versioning rule), with `tests/unit/test_prompts.py` asserting every registered prompt actually carries it - a new prompt added later without this text now fails a test rather than shipping silently unprotected |
| `ai_tokens` counter existed but nothing ever incremented it | `SessionCounters.ai_tokens` has existed since early phases and was already visible via `GET /v1/session`, but no code path ever wrote to it - AI spend was untracked despite SECURITY.md claiming otherwise. Wired `tokens_used` through `app/ai/structured.py` (return type changed to `tuple[T \| None, int]`, summing both the original and repair attempt), `rewrite.py`, `tailor.py`, `cover_letter.py`, and `interview.py`, then incremented `ai_tokens` at each of the four calling endpoints. **A real bug was caught by the first test written for this**: two sequential `increment_counter(session, ...)` calls using the same stale `session` object silently discarded the first increment, since each call bases its update on the `meta` it's given rather than the store's current state - the second call's `_persist` overwrote the first. Fixed by chaining the returned updated `SessionMeta` into the second call at all four sites (`ai.py`, `career.py` x2, `tailor.py`) |
| No dedicated rate limits for AI calls or exports | SECURITY.md's rate-limit table listed "AI calls: 100/hour" and "Export: 60/hour" as if real; only session-create and upload limits were actually wired. Added `RATE_LIMIT_AI_CALLS_PER_HOUR` (default 100) and `RATE_LIMIT_EXPORTS_PER_HOUR` (default 60), enforced in `/v1/ai/rewrite`, `/v1/tailor` (only when the AI-assisted path actually runs - deterministic tailoring stays unbounded, since it costs nothing), `/v1/cover-letter`, `/v1/interview/questions`, and `/v1/export` |
| No observability beyond structured logs | Added `app/core/metrics.py`: an in-process, content-free registry (counters + latency averages, every label from a fixed closed set - route template, status category, job state - never user content). Wired into `RequestContextMiddleware` (every request) and `app.queue.inprocess` (every screening job: completed/failed/retried counts and duration). Exposed as JSON via `GET /metrics` (not a Prometheus exporter - none is configured in this environment), disabled in production the same way `/docs` is, since there's no auth layer to gate it behind otherwise. Queue depth (jobs currently in flight) is included; temp-storage bytes, cleanup success/failure, and active session count are explicitly **not yet wired** - the last needs a namespace-scan capability `SessionStore` doesn't expose (a full key scan is a real cost on Redis), so it wasn't added as a memory-backend-only half-measure |
| Bulk pipeline performance, unmeasured until now | Ran 100 candidates (`MAX_BULK_RESUMES`) through a live app instance end to end: upload request 0.18 s, full processing (all 100 candidates, worker concurrency 4) 0.31 s, ranking fetch for all 100 9 ms, zero failures. Caveat stated plainly: measured with small synthetic TXT resumes and `embedding_backend=none` (no real PDF extraction or embedding cost) - a realistic PDF-plus-embeddings production load will cost meaningfully more per candidate, but this confirms the queue/storage/ranking architecture itself has no obvious bottleneck at the documented scale ceiling |

**Verification** - all green:

```
backend    554 passed, 10 skipped (Redis, no server present)   ruff clean   mypy clean
```

No frontend code changed this phase beyond adding the new `tokens_used` field to four TypeScript
proposal interfaces for type accuracy (`frontend/lib/api-client.ts`) - Phase 8 was a backend/docs
hardening pass, not a feature phase, so `npm test`/`typecheck`/`lint`/`build` were re-run to
confirm nothing broke but no new frontend tests were needed.

### Phase 9A — Architecture & product baseline

Reviewed the full repository (backend, frontend, tests, API surface, all architecture docs)
against [PHASE_9_IMPLEMENTATION_PLAN.md](PHASE_9_IMPLEMENTATION_PLAN.md) before changing anything.
No gaps found beyond what Phase 8 already documented as known limitations. Proceeded to 9B.

### Phase 9B — Privacy & consent

**Frontend** (`frontend/components/session/consent-gate.tsx`)

A mandatory, explicit consent step - genuinely gating, not a checkbox easy to miss - shown before
either "Start candidate session" / "Start screening session" button is reachable. Two actions:
"I agree — continue" (reveals the existing mode-selection screen) and "Decline" (routes back to
the landing page). Consent lives in plain React component state, written to no storage at all
(not even `sessionStorage`, which already only holds `session_id`/`session_mode` per
PRIVACY_ARCHITECTURE.md section 4) - a reload asks again, since consent is tied to the act of
starting *this* session, not a saved preference. An already-active session (rejoined after a
reload) skips the gate, since consent was already given when that session was created.

Content covers: no account/no database, the TTL and immediate-deletion option, that AI features
send only the minimum necessary text to a configured provider (never more, and features report
themselves honestly unavailable with none configured), and an explicit warning that closing the
tab does not delete data instantly - deletion is server-enforced on the stated schedule, not
browser-enforced. `components/session/session-status.tsx`'s destructive action was renamed "End
session" → "End session & delete data" to say plainly what it does.

**Verification** — all green:

```
frontend   42 passed   eslint clean   tsc --noEmit clean   next build clean
```

Verified live end to end against a running backend: landing → workspace shows the consent gate
first (not the mode cards) → Decline routes back to `/` → Agree reveals the mode cards → starting
a session works normally → reloading an active session skips the gate and rejoins directly →
"End session & delete data" fires `DELETE /v1/session` (`204`) and returns to the consent gate.
Zero console errors throughout.

### Phase 9C — Resume extraction & reconstruction reliability

Built a battery of realistic synthetic resume layouts (real-world templates, not just the
existing single-column fixtures) and stress-tested the extraction pipeline against each one.
Five real, previously-undiscovered defects were found this way and fixed - not assumed correct
because the existing test suite passed, which it did the whole time these were live.

| Defect | Root cause | Fix |
|---|---|---|
| Multi-column PDF text reads in the wrong order | `page.extract_text()` groups words into lines purely by vertical position - on a two-column page, a left-sidebar word and a right-column word at the same height land on the same reconstructed line, e.g. `"Jordan Vance EXPERIENCE"` from a name and an unrelated section header | `app/documents/extract/pdf.py::_column_aware_text` crops the page to each column and extracts each independently, so pdfplumber's own line-grouping never sees content from the other column |
| Column detection missed asymmetric sidebar layouts | The old heuristic only checked a fixed 45-55% centre band, which only catches near-equal-width columns - a common narrow-sidebar-plus-wide-main-column resume template has its gutter anywhere from ~25-40% | Replaced with `_find_gutter`: sorts every word's horizontal midpoint and finds the single widest gap within a central search band, so the gutter position is measured, not assumed |
| Title and organisation on separate lines silently dropped the organisation | `_split_header_and_dates` only recognised "Title, Org" combined on one line; when they're on two entirely separate lines (a common template pattern, not just a PDF-extraction artefact), the organisation line and the date line were both misfiled as fake bullets | Extended `_split_header_and_dates` with a conservative fallback (`_looks_like_subheader_line`: short, no bullet marker, no sentence-ending punctuation) that folds a plausible organisation line into the header before re-checking for a date on the line after it. Deliberately **not** applied to projects (`merge_subheader=False`), where a single line after the title is legitimately a description, not an organisation - the two shapes are not distinguishable, and projects already has a correct path for that line |
| Short all-caps abbreviations misread as new section headers | The ALL-CAPS section-header fallback (built for genuine unrecognised headers like "AWARDS") required only 3+ uppercase letters - "MBA", "PMP", "CFA" sitting alone on their own line (extremely common for a degree or certification) satisfied it just as well, silently truncating whatever section they appeared inside | Raised the minimum length for the fallback to 5 (`app/documents/heading_split.py`) - real section-header words are essentially never this short, while degree/certification abbreviations almost always are |
| DOCX layout tables read in the wrong order (the DOCX analogue of the PDF bug above) | DOCX has no native CSS-style column layout most sidebar resume templates actually want, so a borderless table is the usual real-world workaround - `_table_text` joined every row's cells with `" | "`, interleaving sidebar and main-column content onto one line exactly like the PDF case | `app/documents/extract/docx.py::_table_text` now reads column-major (one full column before the next) once a table looks like a layout device (≥4 rows, ≥2 columns) rather than a small genuine data table like "Skill \| Level" (which stays row-major, unaffected) |

**Verification** — all green:

```
backend    563 passed, 10 skipped (Redis, no server present)   ruff clean   mypy clean
```

Every defect above has a dedicated regression test reproducing the exact failure mode, plus new
realistic fixtures (`make_sidebar_resume_pdf_bytes`, `make_sidebar_table_docx_bytes`) that were
not needed before because nothing in the existing fixture set exercised an asymmetric or
table-based two-column layout. Verified with direct end-to-end runs (extract → structure) printed
and inspected by hand for each defect before writing the test that locks the fix in, not just
"the assertion I wrote passes."

### Not yet covered in 9C

Time-bounded this pass to defects actually found by testing, not an exhaustive enumeration of
every item PHASE_9_IMPLEMENTATION_PLAN.md's 9C section lists. Explicitly not yet stress-tested:
OCR-derived text (no Tesseract in this environment - Phase 2's existing gap), truly ragged/merged
DOCX table cells beyond the `IndexError` fallback, and a wider variety of real degree/date
notations (season+year, academic-year ranges like "2019/2020"). None were found broken by what
*was* tested; they are simply outside what got exercised this pass, named here rather than
silently assumed fine.

### Phase 9D + 9E — Extraction review UI and frontend redesign

Implemented together as one coordinated effort, on a shared design system built first, per the
approved design spec (design/UX proposal → user-approved requirements list → this implementation).
No backend changes were needed - every screen below reuses existing API contracts.

**Design system** (`frontend/lib/design-tokens.ts`, `frontend/app/globals.css`)

Fixed 6-step type scale (`--text-display` … `--text-micro`) and a spacing rhythm
(`--space-section`/`--space-card`/`--space-inline`) so redesigned components stop inventing their
own sizes ad hoc. The existing OKLCH neutral/accent/semantic palette, radius, and motion rules
(including `prefers-reduced-motion`) are unchanged - no gradients, no new decorative colour.

**Shared primitives** (`frontend/components/ui/`)

* `ProgressRail` - communicates the recommended journey without forcing it: every step stays
  visible, disabled steps explain why (`aria-label`d), `aria-current="step"` on the active one,
  collapses to a `3/8 · Review` fraction under `sm`. Candidate and recruiter modes get separate
  step sets rendered by separate call sites - never one shared rail with irrelevant steps grayed
  out.
* `AiProposalCard` - the one interaction pattern (idle → loading → proposal-with-fact-guard-
  findings → accept/discard, or a calm unavailable/error state) now reused by bullet/summary
  rewriting, cover letters, and interview questions alike (`ai-rewrite-control.tsx` and
  `career-panel.tsx` were both rebuilt on top of it).
* `ConfidenceHint` - a quiet "Check this" affordance shown only on genuinely low-confidence
  extracted fields (`provenance.kind === "extracted" && confidence < 0.55`); nothing else in the
  UI shows a confidence percentage or badge.
* `SectionCard` - a plain heading + content grouping, replacing card-in-a-card-in-a-card nesting
  on the Health/Match/Career screens.

**Extraction review** (`frontend/components/builder/extraction-review.tsx`, extended
`section-editor.tsx`, new `date-range-editor.tsx`)

The mandatory confirmation boundary the plan called for: Upload → Extraction (automatic) →
Review/Edit → **Confirm resume & continue** → everything downstream. Built on the existing
`SectionEditor`/`resume-edit.ts` machinery rather than a new editing paradigm - the gaps identified
during design review are now closed:

* Dates are editable everywhere (`DateRangeEditor`: start/end month + a Present toggle).
* `custom_sections` has a full editor (title + bullets) for the first time.
* Projects gained `description`; Education gained `field_of_study` and `location`.
* **"Move to..."** reclassifies an entry between structurally compatible sections
  (`lib/resume-edit.ts::moveEntryToSection` + `compatibleSections`): experience ↔ projects ↔
  custom sections, and education ↔ certifications ↔ custom sections. Every direction has a
  field-mapping conversion function that folds non-mapping data into the closest text field
  (a bullet, a note) rather than silently dropping it; moving marks the entry `user_provided`,
  same as any other edit.
* "View original extraction" reuses the version already created at upload time (`version 1`) - no
  second persistent copy, just `GET /v1/resume/versions/{id}` on demand.
* Confirming persists the edited resume as a new version (existing `POST /v1/resume/versions`) and
  sets a client-only `hasConfirmedResume` flag that gates `ProgressRail` reachability - not a new
  kind of persisted state, and re-derivable from "does this document have ≥1 version" on reload.

**Candidate journey** (`frontend/components/workspace/candidate-workspace.tsx`, new; replaces the
deleted `resume-analyzer.tsx` and `resume-builder.tsx`)

The flat "everything stacked on one page" workspace is now a rail-driven journey: Upload → Review
→ Health → Match → Gaps → Improve → Career AI → Export. Not a wizard - every reachable step is
directly clickable; a step is gated only by an actual data dependency (a resume, a confirmation, a
match), never by "have you visited the previous step." Health/Match no longer show the internal
`methodology`/version string; Career AI reuses the job/match already computed in the Match step
instead of asking for the job description a second time, and shows a calm "Run a job match first
to unlock Career AI" empty state when there isn't one yet. Export shows the version label next to
the download buttons.

**Recruiter workspace** (`frontend/components/screening/screening-workspace.tsx`)

Gained its own `ProgressRail` (Job → Upload Candidates → Rank → Compare/Shortlist → Export) laid
over the existing continuous-scroll layout via anchor ids, without restructuring the working
upload/poll/rank/compare/shortlist logic. "Export" is honestly marked not-built-yet (`reachable:
false`) rather than a fake step - there is no bulk-export capability in the backend and none was
added, per the "don't introduce fake functionality" rule already established in earlier phases.

**Content cleanup**

Removed from the user-facing UI: the "Phase N of the build is live" banner, the raw server-
capability badges (`llm: not configured`, `embeddings: available`, …), the post-upload parser
statistics grid (replaced with a one-line confirmation), and the `methodology`/version string on
Health and Match. All of that information remains available - the banner text simply isn't
reproduced anywhere else, since it was development-log language, not product copy.

**Privacy wording correction**

`consent-gate.tsx` no longer implies that closing the tab deletes data immediately - it now states
plainly that data is temporary and auto-deleted on the stated schedule, that a reload within the
window restores the session, and that "End session & delete data" is the immediate option. It also
now distinguishes *this application's* temporary session storage from *processing by Google
Gemini* when an AI feature is explicitly invoked, rather than the earlier, broader "AI provider"
phrasing.

**Verification** — all green:

```
frontend   52 passed (10 new, moveEntryToSection/compatibleSections/formatDateRange)   eslint clean   tsc --noEmit clean   next build clean
backend    563 passed, 10 skipped (unchanged - no backend code touched this phase)
```

Verified live end to end against a running backend (`.venv`, memory session store): consent →
decline → re-agree → candidate session → upload a realistic multi-section TXT resume → extraction
review renders all sections including the ALL-CAPS "AWARDS" section correctly mapped to a custom
section → moved an experience entry to Projects via "Move to..." and confirmed the conversion
(bullets, dates, and technologies all preserved) → viewed the original extraction side by side →
confirmed the resume → auto-advanced to Health (score rendered, no methodology text) → pasted a
job description and matched → Gaps showed the same bucketed breakdown with a "See what to learn
next" link → Career AI reused the match with no JD re-entry, cover letter correctly reported itself
unavailable (no `LLM_PROVIDER` configured) while Learning Priorities worked with no key at all →
Export showed the current version label → "End session & delete data" returned to the mode-select
screen → started a recruiter session and confirmed its separate rail renders independently of the
candidate one. Zero browser console errors throughout. (File upload was driven by dispatching a
synthetic `File`/`DataTransfer` onto the input via the browser tool's JS execution, since the
automation tool available this session has no native file-picker support - the same limitation
noted in Phases 5-7.)

### Phase 9F — Gemini AI integration

`GeminiProvider` implemented behind the existing `LLMProvider` abstraction, alongside
`AnthropicProvider` (not replacing it - both are selectable via `LLM_PROVIDER`). Architecture kept
exactly as required: `Feature -> LLMProvider -> GeminiProvider -> Gemini API`; no feature imports
the `google-genai` SDK directly.

* `app/ai/providers.py::GeminiProvider` - uses the official Google GenAI SDK (`google.genai`,
  `Client(...).aio.models.generate_content`), not the OpenAI-compatible endpoint. Confined the same
  way `AnthropicProvider` confines the `anthropic` SDK. Any failure (invalid key, timeout, rate
  limit, network) is caught broadly and resolves to `None` - honest unavailability, never a
  fabricated response, matching `AnthropicProvider`'s existing behaviour exactly.
* `app/config.py` - added `gemini_api_key`, `llm_model_gemini` (default `gemini-3.6-flash` -
  see the live-verification defect below for why), and `llm_provider` gained a `"gemini"` option. Added
  `is_configured_api_key()`: a value matching a known placeholder (`.env.example`'s literal
  `YOUR_GEMINI_API_KEY_HERE`, plus a few generic placeholders like `changeme`) is treated as *not
  configured* rather than a real credential - copying the example file verbatim into a real `.env`
  degrades to the honest "unavailable" state instead of the provider attempting (and failing) a
  real request with a dummy string. Applied consistently to the existing Anthropic key too.
  `capabilities()["llm"]` and `validate_runtime()`'s production check both use it.
* `.env.example` / `backend/.env` (gitignored, never committed) - `GEMINI_API_KEY`,
  `LLM_MODEL_GEMINI` documented; see "Environment setup" below for exactly what to replace.
* `backend/pyproject.toml` - added `google-genai>=1.0`.
* **Real defect found and fixed while wiring this up**: adding `backend/.env` for local testing
  broke `Settings()`'s test-suite defaults, since pydantic-settings loads `.env` unconditionally
  and several tests construct `Settings()` without pinning every field. Fixed by disabling
  `env_file` loading whenever `PYTEST_VERSION` is set (pytest sets it for the whole session,
  before collection) - tests are now hermetic regardless of what a developer's local `.env`
  contains, which was a latent gap this phase's own local file happened to expose.

**Testing** - everything that doesn't require a live request: placeholder-detection, provider
selection (`get_llm_provider` dispatch, including falling back to `NullLLMProvider` for a
placeholder-only "gemini" selection), capability reporting, request construction (model,
`contents`, `system_instruction`, `max_output_tokens` all asserted against a monkeypatched async
client), successful-response parsing (text + `prompt_token_count`/`candidates_token_count` ->
`LLMResponse`), an empty-response edge case, and four failure modes (invalid key, timeout, rate
limit, network) all resolving to `None` - plus a test asserting the API key never appears in logs
even when the call raises. `backend/tests/unit/test_gemini_provider.py`, 17 new tests.

```
backend    573 passed, 10 skipped   ruff clean   mypy clean
```

**Live verification (Phase 9J) — complete.** A real `GEMINI_API_KEY` was provided (placed directly
into `backend/.env` by the user, never pasted into chat or printed by any command run here) and
every AI feature was exercised against the real Gemini API through the running application, not a
script that bypasses it. Two real defects were found and fixed this pass - exactly the kind of
thing "successful HTTP response" testing alone would have missed:

1. **`gemini-2.5-flash` (this project's original model choice) returned `404 NOT_FOUND`** - "This
   model ... is no longer available to new users" - live, on the very first real request. The
   error response itself named the replacement: `gemini-3.6-flash`. Fixed by updating the default
   (`app/config.py`, `.env.example`, `backend/.env`) - exactly the one-line fix `LLM_MODEL_GEMINI`
   being configurable rather than hardcoded exists to make.
2. **Real Gemini output was silently truncated into a garbled sentence fragment** once the model
   swap above was made. Root cause: `gemini-3.6-flash` reserves part of its `max_output_tokens`
   budget for mandatory internal "thinking" tokens the caller never sees - a live diagnostic call
   showed 44 thinking tokens consumed against a 50-token budget, leaving 2 tokens for the visible
   answer. The five prompt budgets in `app/ai/prompts.py` (120-1200) were sized for Claude, which
   has no equivalent hidden token tax, and the smaller ones left no room for a real answer once
   thinking was subtracted - the app returned `available: true` with unusable text as "success."
   Fixed by raising every `PromptSpec.max_output_tokens` (bullet/summary/tailor rewrite: 120/200 ->
   1024; cover letter: 700 -> 2048; interview questions: 1200 -> 3072) - confirmed live afterward
   producing clean, fact-preserving output. A larger cap only raises the ceiling before truncation
   can occur; it does not force a provider to write a longer answer than the content needs.

**Every AI feature verified end-to-end with real Gemini output, through the running app's
`/v1/...` endpoints (not a bypass script) and, for the accept/reject and proposal-card states,
through the actual browser UI:**

| Feature | Endpoint | Result |
|---|---|---|
| Bullet rewrite | `POST /v1/ai/rewrite` | Clean rewrite, zero fact-guard findings, `tokens_used: 193`. Verified in the browser: "Asking AI…" -> before/after card -> Accept -> field updated with the exact generated text |
| Summary rewrite | `POST /v1/ai/rewrite` | First call returned meta-commentary leaked into the visible text (see "Model variability" below); a second call returned a clean rewrite. Accepted live in the browser UI |
| Resume tailoring | `POST /v1/tailor` + `POST /v1/tailor/apply` | Deterministic proposals (skill reorder, skill reminders) verified live; re-uploaded with a bullet mentioning a job-relevant skill by name to also exercise the AI-assisted path - two real `bullet_rewrite` proposals (`requires_ai: true`, 247 and 242 tokens), applied, producing a new `source: "ai_tailored"` immutable version with the accepted text and everything else preserved |
| Cover letter | `POST /v1/cover-letter` | Real structured JSON parsed correctly into `salutation`/`body_paragraphs[]`/`closing`; grounded in the actual resume (correct employers, correct technologies, six years correctly stated); generic salutation since no hiring-manager name was given, exactly as instructed. Verified live in the browser Career AI panel |
| Interview questions | `POST /v1/interview/questions` | Real structured JSON, 6 questions, correct categories, each with a rationale and a `grounded_in` citation traceable to a specific resume/job line. Verified live in the browser |

**Model variability, observed and handled correctly, not hidden:** one of the two summary-rewrite
calls returned the model's own internal checklist text ("Professional tone: Yes. ... Number: 'six
years' (stated)") instead of a rewritten summary. This is real LLM non-determinism, not an
application defect - and the architecture's existing safety net caught it exactly as designed: the
fact guard flagged the leaked words ("Yes", "Number") as unverifiable, and the proposal is never
auto-applied regardless, so a user would see clearly nonsensical text in the before/after card and
reject it. The **fact guard was not weakened** to make this or any other Gemini response "pass" -
several genuine outputs also tripped mild false positives (common words like "Skilled",
"Previously", "Leveraging" flagged as "may have been invented"), which is the fact guard's existing
conservative-by-design behaviour, unchanged.

**Token accounting, verified live:** `GET /v1/session` after 8 real AI calls across every feature
above showed `ai_calls: 8, ai_tokens: 2709` - correctly summed across `/v1/ai/rewrite`,
`/v1/tailor`, `/v1/cover-letter`, and `/v1/interview/questions`. The session-token-budget
enforcement itself (`RATE_LIMIT_AI_TOKENS_PER_SESSION`) was deliberately *not* re-tested by
exhausting real quota - Phase 9G's mocked test (a budget of 15 against a `FakeLLMProvider`
reporting 20 tokens/call, second call rejected with `429` before reaching the provider) already
proves the enforcement path independent of which provider is configured, since the check runs
before the provider is ever called.

**Error handling, verified via the existing mocked test suite rather than by deliberately
triggering real provider failures** (an invalid key, a real timeout, or exhausting Gemini's rate
limit against the live account was explicitly out of scope per the request): invalid key, timeout,
rate-limit-shaped, and network-failure exceptions all resolve to `None` (`test_gemini_provider.py`,
4 parametrised failure modes) - honest unavailability, never a fabricated response.

**`/ready` reports the real state:** `{"llm": true, ...}` confirmed live with the real key
configured, without exposing the key itself anywhere in the response, logs, or this document.

**Privacy, re-confirmed live:** a fresh browser tab loading `/workspace` made **zero** requests to
the backend before any user action (`read_network_requests` on a clean tab showed an empty list) -
no AI call, no session call, nothing fires merely from the page loading. Every AI feature used
above was triggered by an explicit button click. The consent-gate wording (temporary storage vs.
Gemini processing on explicit AI use) was not changed this pass since it was already corrected in
9E and nothing in live verification contradicted it.

### Phase 9G — Bounded AI career workflow

The workflow itself already existed structurally from Phases 5-6 and 9E's redesign - resume
analysis -> job match -> skill gaps -> AI proposals (rewrite/tailor) -> fact guard -> career
actions (cover letter, interview prep, learning priorities) -> re-analysis by revisiting Health.
It is bounded by construction: every AI action is explicitly user-triggered (nothing runs
automatically), every generated proposal is fact-guarded before the caller ever sees it, and
nothing is applied to the resume without an explicit accept. What Phase 9G closed was the one
concretely open piece of "token-limited": a session-lifetime AI token budget, not just an
hourly call-count limit.

* `RATE_LIMIT_AI_TOKENS_PER_SESSION` (default 200,000) - `app.core.ratelimit.
  enforce_session_ai_token_budget` checks `SessionCounters.ai_tokens` before `/v1/ai/rewrite`,
  `/v1/cover-letter`, `/v1/interview/questions`, and the AI-assisted path of `/v1/tailor`, raising
  the same `429 RATE_LIMITED` the hourly limiter uses once the cumulative session spend reaches
  the cap. Closes the Phase 8 known gap ("`ai_tokens` is tracked but not enforced").

```
backend    9 new tests (test_ratelimit.py, test_ai_export_ratelimits.py)   all green
```

Verified against a real endpoint call, not just the unit-level check: a session configured with a
token budget of 15 and a `FakeLLMProvider` reporting 20 tokens/call succeeds once, then the second
`/v1/ai/rewrite` call is rejected with `429` before ever reaching the provider.

### Phase 9H — Full product QA

Full backend and frontend suites as the regression gate, plus a live browser walkthrough with the
real Gemini key in place (see Phase 9F/9J for the AI-specific results):

```
backend    573 passed, 10 skipped   ruff clean   mypy clean
frontend   52 passed   eslint clean   tsc clean   next build clean
```

**Live browser QA performed this pass**, against a fresh tab each time (not a reused tab with
stale history), with console errors checked after every step:

* **Candidate flow, full journey**: consent -> agree -> candidate session -> upload a realistic
  synthetic resume -> extraction review renders all sections correctly -> "Improve with AI" on the
  summary (loading state -> real proposal -> Accept, field updated with the exact generated text)
  -> Confirm resume & continue -> Health (accepted edit correctly reflected, score computed) ->
  Match (pasted a JD, real score + skill gaps) -> Career AI (no JD re-entry - reused the match
  context) -> Generate cover letter (real content, live in the UI) -> Generate interview questions
  (real content, live in the UI) -> Export (correct version label shown) -> End session & delete
  data -> returned to the mode-select screen.
* **Session lifecycle**: ending a session mid-walkthrough (where consent had already been given
  this page load) correctly skips back to consent on the *next* page load - and a *reload* of an
  still-active session correctly **rejoins without re-showing consent** (confirmed after a
  brief async race on first read - the rejoin fetch completes and the workspace renders directly).
  Ending a *rejoined* session (where `consented` local state was never explicitly set this page
  load, by design) correctly falls back to asking for consent again - verified as intentional,
  privacy-preserving behaviour, not a regression.
* **Recruiter flow**: consent -> recruiter session -> its own separate `ProgressRail` (Job ->
  Upload Candidates -> Rank -> Compare/Shortlist -> Export) renders with no candidate-mode steps
  leaking in; "Export" honestly shows "Not built yet" rather than a fake control.
* **Privacy**: a completely fresh tab loading `/workspace` (before consent, before any click) made
  **zero** requests to the backend - confirmed via the browser tool's network log, not inferred
  from reading the code.
* **Responsive**: resized to a 375px mobile viewport and reloaded - no horizontal overflow
  (`scrollWidth` <= `clientWidth`), zero console errors.

Two real defects were found and fixed during this pass - both live-Gemini-specific, detailed in
Phase 9F above (the deprecated model id, and the truncated-output token-budget issue). No other
defects found; every other flow behaved as already documented in 9B-9E's verification notes.

### Phase 9I — CI, dependency lockfile

* `.github/workflows/ci.yml` (new) - backend job (install from `requirements-lock.txt`, `ruff`,
  `mypy`, `pytest`, `pip-audit`) and frontend job (`npm ci`, `eslint`, `typecheck`, `vitest`,
  `next build`, `npm audit`) on every push/PR to `main`. Both audit steps are `continue-on-error`
  (advisory, not yet a merge gate) so a known, already-triaged finding doesn't block unrelated
  work. **Not yet run against a live GitHub Actions runner** - validated locally (YAML parses,
  every command it runs was run manually against the same repo state in this session) but not
  confirmed against the actual CI environment, since this session has no way to trigger one.
* `backend/requirements-lock.txt` (new) - a pinned `pip freeze` snapshot of the environment every
  test in this phase ran against (Python 3.13, including `google-genai`). `pyproject.toml` stays
  the source of truth for floating lower bounds; this is what a reproducible install or CI uses.
  Closes the Phase 8 known gap ("no backend dependency lockfile").
* **`npm audit` findings — investigated in depth (Phase 9J), not just re-run.** Full analysis in
  [SECURITY.md](SECURITY.md) section 9; summary: `postcss <=8.5.22` is hard-pinned by `next` itself
  across the entire `15.x` line (confirmed via `npm view next@15.5.24 dependencies` - even the
  latest `15.x` patch still requires exactly `postcss@8.4.31`; only `next@16.3.3` bundles a fixed
  version), so no compatible fix exists short of the major bump - and this app's own PostCSS input
  is only its own trusted `globals.css`/Tailwind classes, never attacker-controlled CSS, so real
  exposure is low. `sharp <0.35.0` is an *optional* dependency that only matters if `next/image` is
  used - confirmed via `grep` that it is never imported anywhere in this codebase, so exposure is
  effectively none; a compatible override to `sharp@0.35.3+` is possible without the major bump but
  was not applied, since it would "fix" a finding with zero real exposure while adding an
  integration risk `next@15.x` never tested against. The major upgrade itself is deferred, not
  silently dropped: `next@16` raises the minimum Node requirement to `>=20.9.0` and touches the
  build pipeline, App Router, and `next/image` broadly enough to warrant its own dedicated
  regression pass against the full 9D/9E redesign, not a bundled side effect of this session.
* **Not done:** a real metrics exporter, staging/production environment configs, and container
  hardening - out of scope for what was requested; still tracked below.

### Phase 9J — Final acceptance

Reviewed the complete candidate and recruiter journeys, the full test/lint/type/build gate, and
the production-readiness posture together, against the 32-item acceptance checklist the 9D+9E
approval message originally specified plus everything 9F-9I added. See the "Production readiness"
section below for what is and is not verified beyond local development, and the "Final response"
summary the user received at the end of this session's work for the itemised result.

**Everything below is genuinely true as of this update**, not aspirational:

* Consent gate works; Decline blocks access; a fresh tab makes zero backend requests before consent
* Accountless, database-free architecture unchanged (ADR-0003) - no accounts, no permanent storage
  of resumes, jobs, AI history, or candidate data introduced anywhere in Phases 9D-9J
* Session TTL, reload/rejoin, release-grace, and immediate deletion all re-confirmed live
* PDF/DOCX extraction defects from 9C remain fixed (full backend suite includes their regression
  tests; unchanged this phase, none of Phases 9F-9I touched `app/documents/`)
* Structured resume hierarchy, extraction review, "Move to...", dates, custom sections all working
  (unchanged since 9D; re-confirmed live during this phase's browser walkthrough)
* Confirm Resume works; resume versions remain immutable; downstream features read the confirmed
  version (re-confirmed live: the AI-accepted summary edit was present in Health after Confirm)
* Candidate and recruiter navigation both verified live, structurally separate
* Career AI reuses match context - no second JD paste, re-confirmed live
* AI proposal pattern unified across every feature, verified live with real Gemini responses
* Gemini stays server-side; the key was never exposed in a response, a log line, a test, or this
  document at any point
* Unnecessary UI text and debug information remain removed (unchanged since 9E)
* Responsive behaviour spot-checked at a 375px viewport this phase; accessibility patterns
  (skip link, focus-visible, `aria-current`, `aria-live`) unchanged since 9D/9E and not regressed
  by any change in 9F-9I (no UI code was touched in those phases)
* Backend (573 passed, 10 skipped), frontend (52 passed) tests, lint, type-check, and build all
  pass; no rule was weakened or test deleted to make anything pass
* `git status` clean, no secrets staged (verified explicitly - see "Final git review" below)

**What Phase 9J does *not* claim**, because it would not be true: a staging or production
deployment exists or has been verified; the CI workflow has run on a live GitHub Actions runner;
`npm audit`'s three findings are resolved; or that every possible resume layout/edge case has been
exercised beyond what 9C's regression suite and this phase's synthetic test resume covered.

## Production readiness

No staging or production environment has ever been deployed for this project - everything below
is scoped to what is implemented and what has been verified in this local development environment.

| Area | Implemented | Tested locally | Staging verified | Production verified |
|---|---|---|---|---|
| Environment variables / config validation | Yes (`app/config.py`, `.env.example`) | Yes - `/ready` checked live with both `llm: false` and `llm: true` configurations | No | No |
| Redis session store | Yes (`RedisSessionStore`, conformance-tested against the same suite as memory) | Partially - 10 conformance tests skip without `TEST_REDIS_URL`; memory backend is what every other test and this session's live verification used | No | No |
| Session TTL / lifecycle | Yes | Yes - idle/absolute TTL, release grace, reload-rejoin, and explicit deletion all re-confirmed live this phase | No | No |
| CORS | Yes (explicit allowlist; wildcard rejected in production) | Yes (unit tests) | No | No |
| HTTPS / HSTS | Implemented (headers, redirect assumptions) | No - this environment serves plain HTTP only; TLS termination was never exercised | No | No |
| Health / readiness (`/health`, `/ready`) | Yes | Yes - both hit live this phase, `/ready` confirmed reporting `llm: true` with the real key | No | No |
| Rate limiting (session, upload, AI calls, AI tokens, export) | Yes | Yes - unit + integration tests for every limit, including the Phase 9G token budget; not re-tested against real concurrent load | No | No |
| AI configuration (Gemini) | Yes | **Live-verified this phase** against the real API - the deepest verification any area in this table has | No | No |
| Logging (structured, redacted) | Yes | Yes - redaction observed live in `uvicorn_live.log` during this phase (raw error text absent, structural markers present) | No | No |
| Metrics (`/metrics`) | Partial - request latency and screening job outcomes only; active session count and temp-storage bytes are explicitly not covered (Phase 8 known gap) | Informally, not re-verified this phase | No | No |
| Export (PDF/DOCX) | Yes (Playwright Chromium, python-docx) | Yes - unit-tested; the Export screen's version-label display was re-confirmed live, though a downloaded file's bytes were not re-inspected this phase | No | No |
| CI pipeline | Yes (`.github/workflows/ci.yml`) | Locally-equivalent commands all re-run and passing | **Not run on a live GitHub Actions runner** - no way to trigger one from this environment | No |
| Container hardening | Not built | N/A | No | No |

## Planned

Nothing. Phase 9 (9A-9J) is complete as scoped. Remaining open items are the ones this document
names explicitly rather than leaving implicit: live GitHub Actions confirmation, a staging/
production deployment, the `next@16` migration, a real metrics exporter, and container hardening.
Any of these becoming a new priority is a new, explicitly-requested phase - not an unscheduled
surprise found later.

## Environment setup (Phase 9F)

* **Location:** `backend/.env` (gitignored - never committed; `.env.example` at the repo root is
  the committed, secret-free template both files are kept in sync with).
* **Variable to replace:** `GEMINI_API_KEY`. It currently holds a value you supplied directly by
  editing the file - the correct channel, since it's never pasted into chat or logged anywhere by
  this session. `LLM_PROVIDER=gemini` and `LLM_MODEL_GEMINI` are already set, so no other edit is
  needed.
* Everything else in the app already treats that value as configured: `get_llm_provider` returns
  `GeminiProvider`, `/ready` reports `llm: true`, and every AI-backed screen's "Improve with AI" /
  cover letter / interview prep controls will attempt a real call the next time they're used.
* **Restart required:** yes - `Settings` is loaded once at process startup (`get_settings()` is
  `lru_cache`d) and pydantic-settings reads `.env` at that point, so the backend process must be
  restarted (`uvicorn app.main:app --reload` picks this up on its own reload; a non-`--reload`
  process needs a manual restart) for a changed key to take effect. No code change is required.
* **`LLM_MODEL_GEMINI`** was updated to `gemini-3.6-flash` during live verification (Phase 9F/9J) -
  the originally-chosen `gemini-2.5-flash` returned `404` live ("no longer available to new
  users"). If Google deprecates the current model again in the future, the same one-line fix
  applies: update `LLM_MODEL_GEMINI` in `backend/.env`, no code change needed.
* **Live verification status: complete**, not pending. Every AI feature (bullet/summary rewrite,
  tailoring's AI-assisted path, cover letter, interview questions) was exercised against the real
  Gemini API through the running application this session - see Phase 9F/9H/9J above for the full
  results, the two defects found and fixed, and exactly what was and wasn't re-tested against the
  live account (e.g. real provider rate-limiting was deliberately not triggered, to avoid
  unnecessary account usage - covered instead by the existing mocked failure-mode tests).

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
# Backend (from backend/) - reproducible install from the pinned lockfile (Phase 9I):
#   ../.venv/Scripts/python.exe -m pip install -r requirements-lock.txt && pip install -e ".[dev]"
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
| No staging/production deployment exists | Every "verified" claim in this document is scoped to local development | Phase 9J's "Production readiness" table states this explicitly per area rather than leaving it implicit |
| 3 high-severity `npm audit` findings | Transitive `postcss`/`sharp` vulnerabilities via `next`, fixable only via a breaking `next` major-version upgrade | Found in Phase 8, still open in Phase 9I - deliberately not force-upgraded without a dedicated regression pass; now surfaced automatically by CI (`npm audit` step) instead of needing a manual re-check |
| Active session count, temp-storage bytes, and cleanup success/failure are not in `/metrics` | Phase 8's metrics registry covers request latency and screening job outcomes only | Active session count needs a `SessionStore` namespace-scan capability that doesn't exist yet (a full key scan is a real cost on Redis) - not added as a memory-backend-only half-measure. Still tracked; no real metrics exporter (Prometheus etc.) exists either |
| No staging/production environment configs or container hardening | Phase 9I's CI pipeline covers tests/lint/audit only, not deployment | Out of scope for what's been requested so far; tracked as remaining Phase 9I/9J work |

## Current blockers

None.

## Open questions (non-blocking; defaults chosen and documented)

1. **Hosting target** — undecided; architecture stays platform-neutral until Phase 9.
2. **LLM credentials** — resolved. `GEMINI_API_KEY` is set in `backend/.env` and every AI-backed
   feature (rewriting, tailoring's AI-assisted bullets, cover letters, interview prep) has been
   live-verified against the real Gemini API (Phase 9F/9J). Every deterministic path (matching,
   deterministic tailoring, learning priorities) needs no key at all and is also confirmed working.
3. **Session TTL defaults** — 60 min idle / 8 h absolute / 120 s release grace; revisit against real usage.
