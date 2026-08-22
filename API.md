# API

**Version:** v1 · **Base path:** `/v1` · **Last updated:** 2026-08-22

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
| `DELETE` | `/v1/session` | Destroy the session namespace immediately. Safe to call via `sendBeacon`. Always `204`. |

## Documents

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/documents` | Upload one PDF/DOCX/TXT (`file`, `kind=resume\|job_description`). Validates, extracts, structures. Returns `document_id`, extraction confidence, layout signals, and `ocr_used`. |
| `GET` | `/v1/documents/{id}` | Extraction result and structured output for a document in this session. |
| `DELETE` | `/v1/documents/{id}` | Remove a document and everything derived from it. |

Limits: `MAX_UPLOAD_BYTES` (default 10 MB), `MAX_PDF_PAGES` (default 20), MIME verified by magic
bytes, DOCX decompression bounded.

## Resume

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/resume` | Current structured resume with per-field provenance and confidence. |
| `PUT` | `/v1/resume` | Replace the structured resume (builder saves). Fields default to `USER_PROVIDED`. |
| `PATCH` | `/v1/resume/sections/{section_id}` | Update or reorder one section. |
| `GET` | `/v1/resume/versions` | List in-session versions (`original`, `ats_optimized`, named tailored versions). |
| `POST` | `/v1/resume/versions` | Snapshot the current resume as a named in-session version. |
| `POST` | `/v1/resume/versions/{id}/restore` | Make a version current. |

Versions exist only inside the session and disappear with it.

## Analysis

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/analysis/resume` | Full resume health: six sub-scores, each with inputs, weights, evidence and recommendations. |
| `POST` | `/v1/analysis/ats` | ATS compatibility: parsing simulation (name/contact/sections/dates/titles/skills), formatting risks (multi-column, tables, text boxes, images, header/footer content, glyph issues), actionable fixes. |
| `GET` | `/v1/analysis/{analysis_id}` | Retrieve a completed analysis from this session. |

Every score response carries `components[]` with `{key, score, weight, evidence[], explanation}` and
a `methodology` block. No endpoint returns a bare number.

## Job descriptions

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/jobs` | Create a JD from pasted text or an uploaded `document_id`. Extracts title, requirements split into `required` / `preferred` / `optional`, experience and education thresholds, certifications, responsibilities, soft skills — each with its source span. |
| `GET` | `/v1/jobs/{id}` | Parsed JD. |
| `PATCH` | `/v1/jobs/{id}/requirements/{req_id}` | Correct a requirement's importance or text (user override wins over extraction). |

## Matching

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/match` | Body `{resume_version_id?, job_id, profile?}`. Returns `overall` plus component scores, matched/missing requirements with evidence, and an explanation. |
| `POST` | `/v1/match/gaps` | Skill gap analysis: `strong` / `moderate` / `missing` / `insufficient_evidence` with evidence spans and role-tied learning priorities. |
| `GET` | `/v1/match/profiles` | Available scoring profiles and their weights. |

Example response shape:

```json
{
  "overall": 88,
  "components": {
    "required_skills":   { "score": 94, "weight": 0.40, "evidence": [] },
    "preferred_skills":  { "score": 72, "weight": 0.15, "evidence": [] },
    "experience":        { "score": 91, "weight": 0.20, "evidence": [] },
    "education":         { "score": 100, "weight": 0.05, "evidence": [] },
    "project_relevance": { "score": 86, "weight": 0.10, "evidence": [] },
    "semantic_relevance":{ "score": 79, "weight": 0.10, "evidence": [] }
  },
  "degraded": [],
  "methodology": { "profile": "default", "version": "1.0.0" }
}
```

## AI assistance

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/ai/rewrite` | Improve one bullet/summary/description. Returns proposals with before/after diff and fact-guard findings. Never mutates the resume. |
| `POST` | `/v1/ai/tailor` | Tailoring proposals for a `job_id`: per-change rationale, diff, and guard status. Applying is a separate explicit call. |
| `POST` | `/v1/ai/tailor/apply` | Apply selected proposals, creating a new in-session version. |
| `POST` | `/v1/cover-letter` | Generate a cover letter grounded in session facts. |
| `POST` | `/v1/interview/questions` | Interview preparation set with a "why this is asked" rationale per question, traced to a resume or JD span. |

When no LLM provider is configured these return `503` with `code: AI_UNAVAILABLE` and a
user-readable message. They never return fabricated content.

## Recruiter screening

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/screening` | Start a screening context for a `job_id`. |
| `POST` | `/v1/screening/{id}/candidates` | Bulk upload resumes (multi-file). Enqueues one job per file, returns `job_ids`. Bounded by `MAX_BULK_RESUMES` (default 100). |
| `GET` | `/v1/screening/{id}/status` | Aggregate progress plus per-job state (`PENDING/PROCESSING/COMPLETED/FAILED/RETRYING`). |
| `GET` | `/v1/screening/{id}/ranking` | Ranked candidates with component scores, matched/missing requirements and evidence. Supports pagination, filtering and sorting. |
| `GET` | `/v1/screening/{id}/candidates/{cid}` | One candidate's full explainable breakdown ("why ranked #1"). |
| `POST` | `/v1/screening/{id}/compare` | Comparison matrix over selected candidate IDs. |
| `POST` | `/v1/screening/{id}/shortlist` | Mark/unmark shortlisted candidates (session-scoped). |

Screening responses expose `redaction: {applied: true, fields: [...]}` documenting which protected
attributes were removed before scoring. Ranking never exposes an unexplained number.

## Export

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/export/resume` | `{format: "pdf"\|"docx", version_id, template_id}` → streamed document. |
| `POST` | `/v1/export/report` | `{type: "analysis"\|"match"\|"screening", ...}` → streamed PDF report. |

Exports are rendered in memory and streamed with `Content-Disposition: attachment`. No download URL
outlives the response; nothing is written to a server export directory.

## Health

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness. No dependency checks. |
| `GET` | `/ready` | Readiness: session store reachable, embedding runtime loaded, plus a capability map (`ocr`, `llm`, `embeddings`, `pdf_export`) so the frontend can hide or honestly disable features. |
