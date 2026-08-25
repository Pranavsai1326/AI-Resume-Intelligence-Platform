# AI ARCHITECTURE

**Last updated:** 2026-08-22

## 1. Three layers, in order of preference

```
Layer 1  Deterministic processing   parsing, section detection, skill/keyword matching,
                                    experience arithmetic, education rules, formatting checks,
                                    readability, quantification detection, all scoring
Layer 2  Semantic intelligence      embeddings: skill similarity, requirement relevance,
                                    project/experience relevance, near-duplicate detection
Layer 3  LLM reasoning              explanation, gap narrative, rewriting, tailoring proposals,
                                    cover letters, interview questions, JD ambiguity resolution
```

Rule: never use an LLM for something deterministic code does reliably. Date arithmetic, skill exact
matching, section presence, bullet counts, keyword coverage and every score are Layer 1. The LLM
explains and writes; it does not measure.

## 2. Service abstraction

```
Application code
      |  (never imports a provider SDK)
AIService  ── PromptRegistry (versioned, id + template + schema + token budget)
      |
ProviderAdapter (LLMProvider | EmbeddingProvider)
      |
Anthropic | OpenAI-compatible | Null(unavailable)      fastembed(local) | remote
```

* `app/ai/providers/` is the only place a vendor SDK is imported. A test asserts no `anthropic` or
  `openai` import exists elsewhere in the codebase.
* `NullLLMProvider` is a first-class adapter used when no key is configured: every call returns a
  structured `AIUnavailable` result, so the UI shows an honest unavailable state instead of failing
  or faking output.
* Models are configuration, not literals: `LLM_MODEL_REASONING` (default `claude-sonnet-5`),
  `LLM_MODEL_BULK` (default `claude-haiku-4-5`).

## 3. Prompt registry

Every prompt is a versioned record: `id`, `version`, `purpose`, `input schema`, `output JSON
schema`, `max input tokens`, `max output tokens`, `temperature`, `model tier`. Prompts live in
`app/ai/prompts/` as data, not inline strings scattered through business logic. Changing a prompt
bumps its version so evaluations stay comparable.

## 4. Structured output and validation

Requests use tool/JSON-schema-constrained output. Every response passes through:

1. **Parse** — strict JSON parse; on failure, one bounded repair attempt with the parser error fed
   back, then give up cleanly.
2. **Schema validate** — Pydantic model; missing/extra/mistyped fields rejected.
3. **Semantic validate** — enum values in range, scores in bounds, referenced section IDs exist in
   the session, no requirement IDs invented.
4. **Fact guard** (§5) — for any generated resume/cover-letter text.
5. **Fallback** — on unrecoverable failure return a typed `AIUnavailable`/`AIInvalidOutput` with an
   error category. Never surface raw provider errors or partial JSON to the user.

Handled failure modes: invalid JSON, missing fields, hallucinated references, timeout, rate limit,
provider 5xx, content filter, truncated output, empty completion.

## 5. Anti-hallucination system

**Provenance.** Every resume field carries one of:

```
USER_PROVIDED   typed by the user
EXTRACTED       parsed from an uploaded document (with source span + confidence)
AI_SUGGESTED    proposed by AI, not yet accepted
AI_GENERATED    AI text the user accepted
```

Provenance is stored on the field, survives edits, and is visible in the UI. AI never mutates
content in place: it emits proposals, the user accepts, and accepted text is relabelled
`AI_GENERATED` with the original retained for the session so before/after is always available.

**Fact guard.** Before any generated text is shown it is checked against a session fact index built
from the user's own content: numbers and percentages, dates and durations, organisation names, job
titles, technologies, degrees, certifications, metric-bearing claims.

* A number, employer, technology, or achievement that does not appear in the source is flagged
  `UNSUPPORTED_CLAIM`.
* Unsupported claims are either blocked (tailoring, cover letters) or surfaced as a highlighted
  warning the user must resolve. They are never silently emitted.
* The prompt layer additionally forbids inventing metrics, employers, technologies,
  responsibilities, achievements, user counts, revenue and performance improvements — but the guard
  is code, because prompts are not a control.

## 6. Compute-once pipeline

```
Upload -> parse ONCE -> structure ONCE -> embed ONCE -> reuse for every module
```

Session-scoped cache keyed by content hash: extracted text, structured resume, section embeddings,
skill embeddings, JD requirement embeddings, analysis results, match results. Cache entries live and
die with the session; nothing is persisted for caching purposes. Re-analysis of unchanged content is
a cache hit with zero token cost.

## 7. Token discipline

* Never send a whole resume when a section will do. Bullet rewriting sends one bullet plus minimal
  role context; summary generation sends the skills list plus role titles, not the full document.
* Deterministic pre-computation goes first; the LLM receives *the analysis*, not the raw document —
  e.g. gap explanation receives the computed matched/missing requirement lists, not both source
  texts.
* Bulk screening runs Layers 1 and 2 for **all** candidates and calls the LLM only for the
  shortlist the recruiter actually opens — explanations are generated on demand, per candidate.
* Per-prompt token budgets are enforced before dispatch; oversized inputs are truncated at section
  boundaries with an explicit notice rather than silently.
* Per-session AI call and token counters power quotas and cost metrics. Counters record numbers, not
  content.

## 8. Embeddings

Built in Phase 4 (`app/matching/embeddings.py`), consumed by `project_relevance` and
`semantic_relevance` (`app/matching/semantic.py`) and by the skill-gap `insufficient_evidence`
bucket (`app/matching/gaps.py`).

* Default backend: **fastembed** with `bge-small-en-v1.5` (ONNX, CPU) running in-process — resume
  and job-description text never leaves the server for semantic matching (ADR-0005). One model
  instance per process (`@lru_cache`), loaded lazily on first use; the ~130 MB of weights
  download to a local cache the first time, not on every request.
* Alternative: remote embedding adapter (`EMBEDDING_BACKEND=remote`) - interface exists, no
  provider implemented yet.
* Vectors are computed fresh per request and never stored - not even session-scoped. A match
  result's *conclusions* (scores, skill-gap buckets) are cached per `(document_id, job_id)`
  (AI_ARCHITECTURE.md section 6), but the embedding vectors themselves are not a durable
  artefact anywhere; there is no vector database and no cross-session index.
* Similarity is cosine, rescaled onto 0-100 against an empirically calibrated range (bge-small
  clusters related professional text around 0.5-0.85 and unrelated text around 0.3-0.45 -
  raw cosine values do not map linearly onto "how good a match", so a fixed floor/ceiling is
  applied and documented at the point of use rather than left as an unexplained magic number).
* If the embedding package or model cannot load (`FastEmbedProvider.is_available()` is false),
  `project_relevance` and `semantic_relevance` report `available: false` and the scoring engine
  renormalises the remaining weights with a visible `degraded` list
  (`app.analysis.scoring_utils.apply_degrade_and_renormalize`) - the first component in the
  product to actually exercise the degrade mechanism Phase 3 built for this.

## 9. Where AI is and is not allowed

| Task | Layer |
|---|---|
| Section detection, contact extraction, date parsing, tenure arithmetic | 1 |
| Skill exact/alias matching, keyword coverage, action verbs, quantification | 1 |
| Formatting/ATS parsing risk detection | 1 |
| All scores and sub-scores | 1 (config-weighted) |
| Skill and requirement similarity, project relevance | 2 |
| Ambiguous requirement classification (required vs preferred) | 1 with 3 assistance on ambiguity only |
| Explanations, gap narrative, recommendations | 3 |
| Bullet/summary rewriting, tailoring, cover letters, interview questions | 3 (fact-guarded) |
| Ranking order | 1 — never 3 |

## 10. Evaluation

`backend/tests/ai/` holds a fixture corpus of synthetic resumes and JDs (authored for the project, no
real personal data) with expected extractions and score bands. Evaluations cover extraction accuracy,
required/preferred classification, score stability across runs, fact-guard catch rate on deliberately
hallucinated samples, and schema-validity rate. Prompt version changes re-run the suite.
