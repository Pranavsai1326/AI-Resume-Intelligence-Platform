# AI Resume Intelligence Platform

A unified resume intelligence system for candidates and recruiters — building, analysis, ATS
compatibility, job matching, tailoring, interview preparation, and explainable recruiter screening —
that requires **no account** and keeps **no persistent user data**.

## The core property

Everything a user provides lives in an ephemeral, server-side session with a TTL and is destroyed
when that session ends. There is no application database, no user table, no resume store, no
candidate store. The privacy guarantee is enforced by architecture, not by a policy paragraph, and is
verified by a dedicated privacy test suite.

Deletion never depends on browser tab-close events alone. Four layers cooperate: best-effort client
cleanup, authoritative TTL expiry, a periodic janitor sweep, and a startup sweep for crash recovery.

## Status

**Phase 4 complete** — paste a job description and a just-analyzed resume is now matched against
it: six explainable components (required/preferred skills, experience, education, project and
semantic relevance) plus a Strong/Moderate/Missing/Insufficient-Evidence skill-gap breakdown.
Semantic matching runs on local embeddings (fastembed, ADR-0005) — no API key, nothing leaves the
server — and degrades honestly if the model can't load rather than faking a score. Phase 5
(resume builder, and the first LLM-backed features) is next.
See [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Running it locally

No Docker, no Redis, no database and no API key required.

```bash
# Backend — from backend/
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000

# Frontend — from frontend/
npm install && npm run dev        # http://localhost:3000
```

Copy `.env.example` to `backend/.env` to change any defaults.

## Documentation

| Document | Contents |
|---|---|
| [PRD.md](PRD.md) | Problem, personas, modules, acceptance criteria, non-goals, honest-claims policy |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System shape, stack, layout, session model, data flows, scoring engine, failure posture |
| [AI_ARCHITECTURE.md](AI_ARCHITECTURE.md) | Three AI layers, provider abstraction, structured output, anti-hallucination, token discipline |
| [PRIVACY_ARCHITECTURE.md](PRIVACY_ARCHITECTURE.md) | Threat model, cleanup layers, storage policies, isolation, logging, privacy tests |
| [API.md](API.md) | v1 endpoints, conventions, error envelope, response shapes |
| [SECURITY.md](SECURITY.md) | Upload security, session security, rate limits, hardening, prompt injection, secrets |
| [docs/adr/](docs/adr/) | Architecture decision records |

## Stack

Next.js 15 · TypeScript · Tailwind · shadcn/ui — FastAPI · Python 3.13 · Pydantic v2 —
ephemeral session store (memory in dev, Redis in production) — local ONNX embeddings ·
Claude via a provider-agnostic AI service.

## What this project will not do

No accounts, no permanent storage of user content, no `localStorage` for resume data, no fabricated
AI output or placeholder metrics, no unexplained candidate ranking, and no use of protected
attributes in screening. These are hard architectural rules, not preferences.
