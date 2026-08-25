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
