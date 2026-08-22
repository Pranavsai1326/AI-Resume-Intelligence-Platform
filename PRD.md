# PRD — AI Resume Intelligence Platform

**Status:** Phase 0 (approved architecture baseline)
**Last updated:** 2026-08-22

## 1. Problem

Job seekers and recruiters both need resume intelligence, but every existing tool demands an
account and permanently stores the most sensitive document a person owns: full name, address,
phone, employment history, education. Recruiters uploading candidate CVs additionally hand third
parties a database of other people's personal data, which they usually have no right to give away.

## 2. Product thesis

One unified resume intelligence system that requires **no account** and keeps **no persistent user
data**. Everything lives in an ephemeral, server-side session that expires automatically. The
privacy property is enforced by architecture (no user tables exist, TTL on every object), not by a
policy paragraph.

## 3. Users

| Persona | Need | Session shape |
|---|---|---|
| **Candidate** | Build/analyze/tailor a resume, prep for a role | 1 resume + 0..n job descriptions |
| **Recruiter** | Screen, rank and compare a candidate pool against one role | 1 JD + 1..N candidate resumes |

No roles, permissions, or identities exist server-side. "Candidate mode" and "Recruiter mode" are
UI surfaces over the same ephemeral session primitives.

## 4. The unified flow (not a bag of tools)

```
Candidate:  Resume -> Resume Intelligence -> Job Description -> Matching -> Tailoring -> ATS -> Interview Prep -> Export
Recruiter:  Job Description -> Candidate Resumes -> Extraction -> Requirement Matching -> Screening -> Ranking -> Comparison -> Shortlist -> Export
```

Each stage consumes the *already-parsed, already-embedded* artifacts of the previous stage from the
same session. A resume is parsed once, structured once, embedded once, and reused by every module.

## 5. Modules and acceptance criteria

A module is done only when backend + frontend + validation + error handling + tests + docs exist.

| # | Module | Acceptance criteria |
|---|---|---|
| M1 | Ephemeral session | Session created without input; sliding TTL; server-side destruction verified by test after expiry and after explicit end |
| M2 | Document ingestion | PDF/DOCX/TXT; magic-byte + size + structure validation; text extraction with layout signals; OCR fallback when available, honest "unavailable" when not; temp bytes released in `finally` |
| M3 | Structured resume | Section detection, contact/experience/education/skills/projects/certs extraction; every field carries provenance; confidence per field |
| M4 | Resume analyzer | Six explainable sub-scores (ATS compatibility, content quality, skills coverage, experience quality, formatting, impact); every score exposes inputs, weights and evidence |
| M5 | ATS analyzer | Parsing simulation (name/contact/section/date/title/skill detection) + formatting risk detection (multi-column, tables, text boxes, images, header/footer content, glyph issues) + actionable fixes |
| M6 | JD analyzer | Title, required/preferred/optional requirement split, experience & education thresholds, certifications, responsibilities, soft skills; each requirement keeps its source span |
| M7 | Resume<->Job matching | Deterministic + semantic + LLM-explanation layers; configurable weights; per-component sub-scores; LLM never sets the number |
| M8 | Skill gap analysis | Strong / Moderate / Missing / Insufficient-evidence buckets with evidence spans; learning priorities tied to the target role only |
| M9 | AI tailoring | Proposals only, never silent rewrite; before/after diff per change; fact-guard blocks unsupported claims |
| M10 | Resume builder | Section editor, reorder, live preview, templates, AI assist, in-session versions, PDF + DOCX export |
| M11 | Cover letter | Grounded in session facts; no invented employer relationships or achievements |
| M12 | Interview prep | Technical / behavioral / project / resume-specific / gap questions, each with a "why this is asked" rationale traced to a resume or JD span |
| M13 | Recruiter screening | Bulk async ingest, per-candidate extraction, requirement matching, ranking with per-candidate explanation, comparison matrix, shortlist, report export |
| M14 | Export | Resume PDF/DOCX, analysis report, match report, screening report; generated on demand, streamed, never retained |

## 6. Explicit non-goals (v1)

Accounts, login, saved resumes, resume history, application tracking, job board integration,
payments/subscriptions, email delivery, ATS vendor integrations, mobile apps, multi-language
resumes (English first), collaborative editing.

## 7. Product guarantees and the language we use

**We say:** "ATS Compatibility", "Resume Compatibility", "Job Match Score", "processed in a
temporary session", "removed by client cleanup + session expiry + server-side sweeps".

**We never say:** "ATS score identical to <vendor>", "deleted the millisecond you close the tab",
"bias-free hiring", "zero data retention by our AI provider" (unless the configured provider's
contract actually supports it — the claim is rendered from configuration, never hardcoded).

## 8. Responsible screening commitment

Ranking consumes an allowlist of job-relevant features only: skills, experience, education,
certifications, projects, technical competencies, requirement coverage. Protected and irrelevant
attributes (name, photo, gender, age/DOB, marital status, nationality, religion, caste, race) are
redacted before scoring and before any LLM call. The product states plainly that this reduces, and
does not eliminate, bias.

## 9. Success criteria

1. A candidate completes upload -> analyze -> match -> tailor -> export with no account, and a
   privacy test proves nothing survives session end.
2. A recruiter screens 100 resumes asynchronously and can answer "why is this candidate ranked #1?"
   with concrete evidence for every ranked candidate.
3. Deterministic layers (M1-M8 core scoring) remain fully functional with **no LLM provider
   configured**; AI features degrade to an honest unavailable state rather than fabricating output.
4. Median resume analysis (parse + score, no LLM) under 3 s for a 2-page PDF.
