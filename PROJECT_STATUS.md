# PROJECT STATUS

**Last updated:** 2026-08-25 · **Current phase:** Phase 8 complete → Phase 9 ready to start

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

## In progress

Nothing. Phase 8 is committed.

## Next task — Phase 9 (deployment)

1. CI pipeline: lint, type-check, test, `pip-audit`, `npm audit` on every push - closes several
   of Phase 8's "not yet automated" gaps at once
2. Adopt a backend dependency lockfile (`uv` or pip-tools) - Phase 8 found this missing
3. Resolve the 3 high-severity `npm audit` findings (transitive `postcss`/`sharp` via `next`) via
   a planned, tested major-version upgrade rather than a forced one mid-hardening-pass
4. Environments (dev/staging/production config), health checks wired to a real orchestrator,
   DEPLOYMENT.md and TESTING.md
5. A real metrics exporter (Prometheus or equivalent) behind the recording calls Phase 8 already
   added, plus the "not yet wired" gauges noted above (temp-storage bytes, cleanup success/
   failure, active session count - the last needs a `SessionStore` capability that doesn't exist
   yet)
6. Convert the `ai_tokens` counter from observability-only into an actual enforced per-session
   budget, if wanted

## Planned

Nothing beyond Phase 9 - it's the last phase in the original roadmap (PRD.md's M1-M14 modules and
the 9-phase build order are now fully scheduled). Anything found after Phase 9 ships becomes a new
entry here rather than an unscheduled surprise.

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
| No LLM key | Layer 3 (AI writing, tailoring, cover letters, interview prep) cannot run | `/ready` reports `llm: false`. `NullLLMProvider` reports every AI feature honestly unavailable rather than erroring or fabricating; deterministic tailoring (skill reordering, requirement reminders) and learning priorities work with no key at all. Semantic matching (Phase 4) needed no key and is confirmed working — ADR-0005's bet on local ONNX embeddings paid off |
| No CI pipeline yet | Gates run locally only; `pip-audit`/`npm audit` run manually, not automatically | Phase 9 |
| No backend dependency lockfile | Reproducible backend installs depend on nobody upgrading a dependency between two `pip install`s | Found in Phase 8's security review; adopting `uv` or pip-tools tracked for Phase 9 |
| 3 high-severity `npm audit` findings | Transitive `postcss`/`sharp` vulnerabilities via `next`, fixable only via a breaking `next` major-version upgrade | Found in Phase 8, deliberately not force-upgraded mid-hardening-pass without a regression budget; tracked for a planned, tested upgrade in Phase 9 |
| `ai_tokens` is tracked but not enforced | A session can exceed a token budget as long as it stays under the AI-call-count limit | Wired for observability in Phase 8 (`GET /v1/session` counters); converting it into an actual enforced cap is optional Phase 9 follow-up |
| Active session count, temp-storage bytes, and cleanup success/failure are not in `/metrics` | Phase 8's metrics registry covers request latency and screening job outcomes only | Active session count needs a `SessionStore` namespace-scan capability that doesn't exist yet (a full key scan is a real cost on Redis) - not added as a memory-backend-only half-measure. Tracked for Phase 9 alongside a real metrics exporter |

## Current blockers

None.

## Open questions (non-blocking; defaults chosen and documented)

1. **Hosting target** — undecided; architecture stays platform-neutral until Phase 9.
2. **LLM credentials** — needed before Phase 5/6's AI-backed features (rewriting, tailoring's
   bullet rewrites, cover letters, interview prep) can be exercised end to end with a real model;
   every deterministic path in both phases, plus learning priorities, needs no key at all.
3. **Session TTL defaults** — 60 min idle / 8 h absolute / 120 s release grace; revisit against real usage.
