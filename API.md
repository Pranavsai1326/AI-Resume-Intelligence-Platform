# API

**Version:** v1 · **Base path:** `/v1` · **Last updated:** 2026-08-25 (Phase 7)

## Conventions

* **Session header:** every endpoint except `/v1/session` (POST), `/health` and `/ready` requires
  `X-Session-Id`. A missing, unknown or expired session returns `410 SESSION_EXPIRED`.
* **Content type:** JSON in/out; uploads are `multipart/form-data`; exports stream binary.
* **Idempotency:** processing endpoints accept `Idempotency-Key`; a repeat with the same key inside
  the session returns the original result instead of recomputing.
* **Errors** are uniform and sanitised — no stack traces, no filesystem paths, no provider details:

```json
{
  "error": {
    "code": "FILE_TOO_LARGE",
    "category": "validation",
    "message": "The file exceeds the 10 MB limit.",
    "retryable": false,
    "request_id": "01J8..."
  }
}
```

Categories: `validation`, `session`, `rate_limit`, `unavailable`, `timeout`, `internal`.

* **Rate limits** return `429` with `Retry-After`.
* **Degradation:** any response whose score depends on an unavailable component includes
  `"degraded": ["semantic_relevance"]`. Clients must render it.

---

## Session

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/session` | Create an ephemeral session. Body: `{ "mode": "candidate" \| "recruiter" }`. Returns session metadata incl. `expires_at`. |
| `GET` | `/v1/session` | Current session metadata and counters. Refreshes idle TTL. |
| `POST` | `/v1/session/heartbeat` | Extend idle TTL without other work. Never extends the absolute cap. |
| `DELETE` | `/v1/session` | Destroy the session namespace immediately (explicit "end session"). Idempotent, always `204`, and reveals nothing about whether the id existed. |
| `POST` | `/v1/session/release` | Beacon endpoint for page teardown: shortens the session to a grace window (default 120 s) instead of destroying it. Body is `{"session_id": "..."}` sent as `text/plain`. Always `204`. |

### Why release rather than destroy

`navigator.sendBeacon` cannot set headers, so `/v1/session/release` takes the id in the body; and
an `application/json` content type would trigger a CORS preflight an unloading page may never
finish, so the body is sent as `text/plain` (CORS-safelisted) and parsed server-side.

It shortens rather than destroys because `pagehide` fires on a reload and on ordinary navigation
as well as on a real tab close, and the browser offers no way to tell them apart. Destroying there
would discard the user's work on every refresh. Collapsing the deadline keeps the cleanup benefit
for a genuinely closed tab - it dies in ~2 minutes rather than an hour - while a page that returns
resumes the session and its full idle TTL. Object TTLs are collapsed and restored with it, so
nothing outlives its session.

## Documents

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/documents` | Multipart upload: `file` + `kind` (`resume` default, or `job_description`). Validates, extracts, and — for `kind=resume` — structures. Returns a summary; fetch the full structured resume via GET. |
| `GET` | `/v1/documents/{id}` | Full extraction result and structured resume for a document in this session. |
| `DELETE` | `/v1/documents/{id}` | Remove a document and everything derived from it. Idempotent, always `204`. |

Type is determined by magic-byte sniffing, never by the client's `Content-Type` or filename.
Limits: `MAX_UPLOAD_BYTES` (default 10 MB, enforced streaming — an oversized upload is aborted
mid-transfer, never fully buffered), `MAX_PDF_PAGES` (default 20), DOCX zip structure bounded
(≤2,000 entries, ≤200 MB uncompressed, per-entry compression ratio capped) before any XML parser
opens it. Re-uploading identical bytes within the same session is a cache hit (`cached: true`) —
nothing is re-parsed or re-structured (AI_ARCHITECTURE.md section 6). Uploads are rate-limited per
session (`RATE_LIMIT_UPLOADS_PER_HOUR`, default 120/hour).

`kind=job_description` runs extraction only — no structured resume is produced, since requirement
extraction is Phase 4 work; `resume_summary` is `null` in that response rather than a fabricated
empty structure.

`POST /v1/documents` response:

```json
{
  "document_id": "18c8897582505bf185fcce96",
  "kind": "pdf",
  "layout": {
    "page_count": 1,
    "multi_column": false,
    "has_tables": false,
    "has_images": false,
    "has_text_boxes": false,
    "has_repeating_header_footer": false
  },
  "ocr_used": false,
  "text_length": 1204,
  "resume_summary": {
    "has_name": true, "has_email": true, "has_phone": true, "has_summary": true,
    "experience_entries": 2, "education_entries": 1, "skill_groups": 2,
    "project_entries": 1, "certification_entries": 1, "custom_sections": 1
  },
  "cached": false
}
```

`GET /v1/documents/{id}` additionally returns `text` (the full extracted plain text) and
`resume` — the structured `Resume` object, where every populated field is
`{"value": ..., "provenance": {"kind": "extracted", "confidence": 0.0-1.0, "source": null}}`
(AI_ARCHITECTURE.md section 5). No document has been parsed by an LLM: `provenance.kind` is
always `"extracted"` at this stage.

When a document has no extractable text (e.g. a scanned image saved as PDF) and OCR is not
configured on this deployment, the request fails with `422 NO_EXTRACTABLE_TEXT` — never an empty
or fabricated resume.

## Resume versions

Built as an explicit **version** model rather than the PUT/PATCH-a-current-resume shape sketched
in Phase 0: every builder save, AI rewrite acceptance, or tailoring apply creates a new immutable
`ResumeVersion` (never an in-place mutation), so a before/after comparison across edits is always
available within the session.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/resume/versions?document_id=...` | List versions for a document, newest lineage included (`version_id`, `label`, `source`, `created_at`, `based_on_version_id`). The first call for a document lazily creates an `"Original"` version from its extracted resume. |
| `POST` | `/v1/resume/versions` | Create a new version. Body: `{document_id, label, source?, resume?, based_on_version_id?}` — exactly one of `resume` (a full structured resume, e.g. a builder save) or `based_on_version_id` (branch from an existing version) is required. `source` defaults to `manual_edit`; tailoring's apply step sets it to `ai_tailored`. |
| `GET` | `/v1/resume/versions/{version_id}` | One version's full structured resume. |

`source` is one of `original` / `manual_edit` / `ai_tailored`. Versions exist only inside the
session and disappear with it.

```json
{
  "version_id": "a1b2c3d4e5f6a7b8c9d0",
  "document_id": "18c8897582505bf185fcce96",
  "label": "Tailored for Acme SRE role",
  "source": "ai_tailored",
  "resume": { "...": "full structured Resume" },
  "created_at": "2026-08-25T10:00:00Z",
  "based_on_version_id": "0f1e2d3c4b5a69788796"
}
```

## Analysis

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/analysis/resume` | Body `{"document_id": "..."}`. Full resume health for a previously uploaded document: six sub-scores, each with inputs, weight, evidence and explanation. |
| `GET` | `/v1/analysis/{analysis_id}` | Retrieve a previously computed analysis. `analysis_id` is the document's id. |

Analysis is compute-once, mirroring document upload: re-requesting analysis of the same
`document_id` in the same session returns the cached result rather than re-scoring
(AI_ARCHITECTURE.md section 6). ATS compatibility is one of the six components below rather than
a separate endpoint — there proved to be no reason to compute it independently, since it needs
exactly the same structured resume and layout signals as the other five.

`POST /v1/analysis/resume` response:

```json
{
  "overall": 90.0,
  "components": {
    "ats_compatibility": {
      "key": "ats_compatibility", "label": "ATS Compatibility", "score": 100.0, "weight": 0.2,
      "available": true,
      "evidence": [
        {"message": "A name was detected.", "severity": "positive"},
        {"message": "No common ATS formatting risks (columns, tables, images, text boxes) were detected.", "severity": "positive"}
      ],
      "explanation": "Simulates how an automated resume parser would read this document: whether contact details, work history and dates are detectable, and whether the layout is likely to confuse a parser."
    },
    "content_quality": { "...": "same shape" },
    "experience_quality": { "...": "same shape" },
    "skills_coverage": { "...": "same shape" },
    "formatting": { "...": "same shape" },
    "impact": { "...": "same shape" }
  },
  "degraded": [],
  "methodology": {"profile": "default", "version": "1.0.0"}
}
```

`evidence[].severity` is `"positive"`, `"info"`, or `"warning"` — every component always returns
at least one item, so a strong resume is told what it does well, not just given a passing number.
`degraded` lists any component that could not be computed (excluded from `overall`, remaining
weights renormalised) — always empty in Phase 3, since every component here is fully
deterministic and needs no external dependency (AI_ARCHITECTURE.md section 1); a future
component that does need one (e.g. semantic relevance, needing embeddings) degrades the same way
rather than as a special case. No response ever returns a bare number without `evidence` and
`explanation` attached.

Analyzing a document uploaded with `kind=job_description` (no structured resume) returns
`422 VALIDATION_FAILED`.

## Job descriptions

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/jobs` | Body `{"text": "..."}` (pasted) or `{"document_id": "..."}` (a document uploaded via `/v1/documents` with `kind=job_description`) — exactly one. Extracts title, requirements split into `required` / `preferred` / `optional`, and each requirement's kind (`skill`, `soft_skill`, `experience`, `education`, `certification`, `responsibility`). |
| `GET` | `/v1/jobs/{job_id}` | The parsed job description. |

A requirement carries `min_years` (for `kind=experience`), `education_level` (for
`kind=education`, one of `none`/`associate`/`bachelor`/`master`/`phd`), and `keywords` — taxonomy
skills recognised in its text, used as the matching key. A requirement mentioning something
outside the recognised skill list keeps `keywords: []` and its full text, rather than being
dropped; the match endpoint reports these as "could not be automatically verified" instead of
silently marking them missed. Editing a parsed requirement (`PATCH`) is not implemented -
tracked as Resume Builder–adjacent follow-up work, not required for matching itself.

## Matching

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/match` | Body `{"document_id": "...", "job_id": "..."}`. Computes all six match components plus the skill-gap breakdown in one pass and caches the result per `(document_id, job_id)` pair. |

A separate gap-analysis endpoint was sketched in Phase 0 but not built: gap analysis reuses the
exact same deterministic checks the component scores already compute, so a second request would
only do that work twice.

Response shape:

```json
{
  "overall": 74.5,
  "components": {
    "required_skills":    { "score": 66.7, "weight": 0.40, "available": true, "evidence": [], "explanation": "..." },
    "preferred_skills":   { "score": 50.0, "weight": 0.15, "available": true, "evidence": [], "explanation": "..." },
    "experience":         { "score": 100.0, "weight": 0.20, "available": true, "evidence": [], "explanation": "..." },
    "education":          { "score": 100.0, "weight": 0.05, "available": true, "evidence": [], "explanation": "..." },
    "project_relevance":  { "score": 58.4, "weight": 0.10, "available": true, "evidence": [], "explanation": "..." },
    "semantic_relevance": { "score": 94.8, "weight": 0.10, "available": true, "evidence": [], "explanation": "..." }
  },
  "degraded": [],
  "methodology": { "profile": "default", "version": "1.0.0" },
  "skill_gaps": {
    "semantic_available": true,
    "entries": [
      {
        "skill": "kubernetes", "requirement_text": "Experience with Kubernetes and AWS",
        "importance": "required", "bucket": "strong",
        "evidence": "\"kubernetes\" is listed in your skills and demonstrated in your experience."
      }
    ]
  }
}
```

`required_skills` and `preferred_skills` compare each requirement's recognised keywords against
the resume's skills section and experience bullets (word-boundary matching, not substring — see
ARCHITECTURE.md section 7 for why that distinction matters). `experience` and `education` compare
the job's stated thresholds against the resume's total role duration and highest detected
education level; a job that states no threshold scores 100 with an informational note rather than
being treated as unmet. `project_relevance` and `semantic_relevance` need the embedding provider
(`EMBEDDING_BACKEND=fastembed` by default, ADR-0005) — when it is unavailable, both report
`"available": false`, appear in `degraded`, and the remaining four weights are renormalised to
sum to 1.0 (`ComponentScore.weight` always reflects the share actually used, not the raw config
value). `skill_gaps.semantic_available` mirrors the same fact for the gap breakdown: without
embeddings, every unmatched skill lands in `missing` rather than the finer-grained
`insufficient_evidence` bucket, which needs semantic similarity to distinguish "no evidence at
all" from "something plausibly related is listed."

## AI assistance

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/ai/rewrite` | Improve one bullet or summary. Body: `{document_id, kind: "bullet"\|"summary", text}`. Returns a proposal — never mutates the resume; the caller saves the accepted result via `POST /v1/resume/versions`. |
| `POST` | `/v1/tailor` | Tailoring proposals for a `job_id` against a resume version. Body: `{document_id, job_id, version_id?}`. Returns a list of proposals: deterministic (skill reordering, required-skill reminders — always available) plus AI-assisted bullet rewrites (needs a configured LLM, capped at 3 bullets per generation). |
| `POST` | `/v1/tailor/apply` | Apply only the proposals the user accepted. Body: `{document_id, version_id?, label, proposals}`. Creates a new `source: "ai_tailored"` resume version; does not mutate any existing version. |

`POST /v1/ai/rewrite`'s response shape (also used internally by tailoring's per-bullet proposals):

```json
{
  "before": "Built the billing service.",
  "after": "Migrated the billing pipeline to event sourcing, cutting reconciliation time in half.",
  "fact_guard_findings": [],
  "available": true,
  "unavailable_reason": null
}
```

With no LLM provider configured, `available` is `false` and `after` is `null` — an honest
unavailable state (`"unavailable_reason": "AI writing is not configured on this deployment."`),
returned with `200`, never a fabricated rewrite and never an error that looks like a bug.
`fact_guard_findings` lists any number, organisation, or technology in the generated text that
does not appear anywhere in the user's own resume content (AI_ARCHITECTURE.md section 5) — surfaced
to the user, never silently dropped or silently trusted.

## Career intelligence

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/cover-letter` | Body: `{document_id, job_id, version_id?}`. A `{salutation, body_paragraphs, closing}` proposal grounded in the resume and the job's title/requirements. |
| `POST` | `/v1/interview/questions` | Body: `{document_id, job_id, version_id?}`. 5-8 interview questions, each with a `category`, a rationale, and the specific resume/job detail it's grounded in. |
| `POST` | `/v1/learning-priorities` | Body: `{document_id, job_id, version_id?}`. Phase 4's skill gaps reordered into a ranked "what to learn next" list — purely deterministic, works with no LLM key configured. |

All three reuse Phase 5's versioned resumes (`version_id` optional — defaults to the document's
latest version, same as tailoring) and Phase 4's job/skill-gap machinery; none introduces new
session-storage state of its own.

`POST /v1/cover-letter` response shape:

```json
{
  "salutation": "Dear Hiring Team",
  "body_paragraphs": [
    "I'm excited to apply for the Senior Backend Engineer role. My experience migrating the billing pipeline to event sourcing at Cascade Systems is directly relevant.",
    "I also bring hands-on experience with Python and Kubernetes."
  ],
  "closing": "Sincerely,",
  "fact_guard_findings": [],
  "available": true,
  "unavailable_reason": null
}
```

With no LLM configured, `available` is `false`, every text field is `null`/empty, and
`unavailable_reason` explains why — the same honest-unavailable shape as `/v1/ai/rewrite`, never
an error or a fabricated letter. The letter never invents a company name or hiring-manager name;
it addresses the letter generically ("Dear Hiring Team") unless one is actually given.

`POST /v1/interview/questions` response shape:

```json
{
  "questions": [
    {
      "question": "Walk me through migrating the billing pipeline to event sourcing.",
      "category": "technical",
      "rationale": "You mention this migration directly in your experience section.",
      "grounded_in": "Migrated the billing pipeline to event sourcing",
      "fact_guard_findings": []
    }
  ],
  "available": true,
  "unavailable_reason": null
}
```

`category` is one of `behavioral` / `technical` / `situational` / `role_fit`. Both endpoints parse
the model's JSON response, validate it against a schema, and make one bounded repair attempt on a
malformed response before giving up as unavailable (AI_ARCHITECTURE.md section 4) — never a
partially-filled or garbled result.

`POST /v1/learning-priorities` response shape:

```json
{
  "priorities": [
    {
      "skill": "docker",
      "requirement_text": "Docker",
      "importance": "required",
      "bucket": "missing",
      "reason": "Not found anywhere in your resume - the most direct gap to close."
    }
  ],
  "semantic_available": false
}
```

Ordered required-before-preferred, and within the same importance, a flat `missing` before
`insufficient_evidence` ("worth confirming") before `moderate` (partial evidence already exists).
`strong` skill-gap entries are never gaps and are excluded entirely. Needs no LLM provider at all
— it only reorders and explains data `/v1/match`'s skill-gap computation already produces.

## Recruiter screening

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/screening` | Body: `{job_id}`. Starts a screening context; 404s if the job doesn't exist yet. |
| `POST` | `/v1/screening/{id}/candidates` | Bulk upload resumes (multipart, field name `files`, repeated). Reads and size-bounds every file at request time, then enqueues one background job per candidate and returns `202 Accepted` with `{candidate_ids}` immediately - it does not wait for processing. Bounded by `MAX_BULK_RESUMES` (default 100) per session, cumulative across calls. |
| `GET` | `/v1/screening/{id}/status` | Aggregate counts (`total`, `pending`, `processing`, `completed`, `failed`) plus a per-candidate `{candidate_id, state, error}` list. `state` is one of `pending`/`processing`/`retrying`/`completed`/`failed`. Poll this until `completed + failed == total`. |
| `GET` | `/v1/screening/{id}/ranking` | Completed candidates only, sorted by `match.overall`. Query params: `min_score`, `limit` (default 20), `offset` (default 0), `descending` (default `true`). Returns `{total, candidates}` - `total` reflects the filtered count, not the page size. |
| `GET` | `/v1/screening/{id}/candidates/{candidate_id}` | One candidate's full result: its `JobMatchResult` (the same shape `/v1/match` returns), its redacted resume, and its shortlist flag. |
| `POST` | `/v1/screening/{id}/compare` | Body: `{candidate_ids: [...]}`. A matrix of already-computed scores - no recomputation, no extra LLM calls. |
| `POST` | `/v1/screening/{id}/shortlist` | Body: `{candidate_id, shortlisted: bool}`. Session-scoped; returns the updated candidate result. |

Every candidate result carries `redaction: {applied: bool, fields: [...]}` naming which categories
were actually found and removed (never a category that found nothing) - `name`, `email`, `phone`,
`links` are structural and always cleared when present; `gender`, `marital_status`,
`nationality`, `religion`, `race_or_ethnicity`, `age_or_dob` are free-text pattern matches, so
`fields` reflects what this specific candidate's resume happened to disclose. The **redacted**
resume is the only one ever stored or returned - blind review by construction (PRD section 8,
SECURITY.md section 10), not a filter a response could forget to apply. Ranking order is always
deterministic (`overall`, computed once per candidate), never an LLM's opinion.

```json
{
  "candidate_id": "a1b2c3d4e5f6a7b8c9d0",
  "match": { "overall": 74.5, "components": { "...": "same shape as /v1/match" }, "...": "..." },
  "redaction": { "applied": true, "fields": ["email", "links", "name", "phone"] },
  "resume": { "contact": { "full_name": null, "email": null, "...": "..." }, "...": "..." },
  "shortlisted": false
}
```

## Export

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/export` | Body: `{document_id, version_id?, format: "pdf"\|"docx"}` → streamed document (`application/pdf` or `application/vnd.openxmlformats-officedocument.wordprocessingml.document`). |

`/v1/export/report` (analysis/match/screening report export) is not yet built — Phase 8+ concern.

PDF is rendered by headless Chromium from a shared HTML/CSS template (ADR-0006); DOCX by
python-docx's object API. Both are rendered in memory and streamed with `Content-Disposition:
attachment; filename="..."` — no download URL outlives the response, nothing is written to a
server export directory. The filename is derived from the version's label reduced to an
`[A-Za-z0-9-]` allowlist (never the raw label), which rules out both path traversal and
`Content-Disposition` header injection. If Chromium isn't available on the deployment, PDF export
returns `503 SERVICE_UNAVAILABLE` rather than a broken or empty file; DOCX has no such external
dependency and is always available.

## Health

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness. No dependency checks. |
| `GET` | `/ready` | Readiness: session store reachable, embedding runtime loaded, plus a capability map (`ocr`, `llm`, `embeddings`, `pdf_export`) so the frontend can hide or honestly disable features. |
