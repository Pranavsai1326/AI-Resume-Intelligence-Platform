# AI ARCHITECTURE

**Last updated:** 2026-08-25 (Phase 8)

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

* `app/ai/providers.py` is the only place a vendor SDK is imported (as built — a lazy, in-method
  import inside `AnthropicProvider`, confined behind a `TYPE_CHECKING`-only reference for typing so
  the SDK need not even be importable at module load time). Every other module reaches the LLM
  only through the `LLMProvider` protocol.
* `NullLLMProvider` is a first-class adapter used when no key is configured: every call returns
  `None`, and the calling code (`app/ai/rewrite.py`, `app/ai/tailor.py`) turns that into an
  explicit `available: false` result with a human-readable reason, so the UI shows an honest
  unavailable state instead of failing or faking output.
* Models are configuration, not literals: `LLM_MODEL_REASONING` (default `claude-sonnet-5`),
  `LLM_MODEL_BULK` (default `claude-haiku-4-5`).
* Real gotcha worth documenting: the installed `anthropic` SDK's `messages.create()` does not
  accept `temperature` as a typed keyword argument on this version, though the underlying Messages
  API accepts it as a top-level JSON field. Passed via `extra_body={"temperature": temperature}`,
  which merges into the raw request body regardless of what the Python wrapper's stub exposes.

## 3. Prompt registry

Every prompt is a versioned, frozen `PromptSpec` record: `system` prompt, `max_input_chars`,
`max_output_tokens`, `temperature`. Specs live in `app/ai/prompts.py` as data, not inline strings
scattered through business logic — `REWRITE_BULLET`, `REWRITE_SUMMARY`, `TAILOR_BULLET`,
`COVER_LETTER`, `INTERVIEW_QUESTIONS` (Phase 6), all five sharing one explicit anti-invention
instruction string (forbidding fabricated numbers, employers, technologies, dates, outcomes) and,
since Phase 8, one explicit prompt-injection mitigation string telling the model that resume/job
text is data to work with, never instructions to obey (SECURITY.md section 6;
`tests/unit/test_prompts.py` asserts every registered prompt actually carries both). Changing a
prompt's wording bumps its version - the Phase 8 addition took every prompt from `1.0.0` to
`1.1.0`. Formal evaluation re-runs keyed to that version bump are not yet built — see section 10.

## 4. Structured output and validation

Two shapes exist, both built on the same `LLMProvider.complete()` — a plain text completion; there
is no provider-specific tool-use/JSON-schema-constrained call anywhere in the codebase, a
deliberate choice (Phase 6) to keep the provider abstraction a single, simple contract any
text-completion API can implement.

**Plain text** (Phase 5 — a rewritten bullet, a rewritten summary): the raw string *is* the
result. Every response still passes through:

1. **Emptiness/failure check** — a provider exception, timeout, or an empty completion is treated
   identically: the caller gets `available: false` with a specific reason, never a partial or
   garbled result.
2. **Fact guard** (§5) — every generated string, before it is ever returned to the client.
3. **Fallback** — `LLMProvider.complete()` returns `None` on any failure (network, timeout, rate
   limit, provider 5xx); the raw provider exception is logged (model name and category only, never
   response content) and never surfaced to the client.

**JSON-in-prompt** (Phase 6 — cover letters, interview questions: genuinely multi-field output a
single string can't carry). The prompt asks for JSON directly and states the schema in plain
English; `app/ai/structured.py::complete_structured` then runs:

1. **Strict parse** — strip a markdown code fence if present, take the outermost `{...}` span if
   the model wrapped the object in prose despite instructions, `json.loads`.
2. **Schema validate** — a Pydantic model; missing/extra/mistyped fields rejected.
3. **One bounded repair attempt** — on either failure, the broken output and the specific parser
   or validation error are sent back with "return ONLY the corrected JSON," and the result is
   parsed and validated again.
4. **Fallback** — a second failure returns `None`, exactly the same "unavailable" signal as no
   provider configured. Callers never see two different failure branches to handle.
5. **Fact guard** (§5) — applied to whichever generated fields carry claims about the candidate
   (a cover letter's body paragraphs, an interview question's rationale) before the result is
   returned.

No semantic-validation pass beyond Pydantic's own field types exists yet (no cross-field checks
like "does this referenced section id actually exist in the session") — nothing built so far has
needed one; Phase 7's recruiter ranking, if it ever generates structured LLM output referencing
specific candidates, is the likely place that requirement would first appear for real.

## 5. Anti-hallucination system

**Provenance.** Every resume field carries one of:

```
USER_PROVIDED   typed by the user
EXTRACTED       parsed from an uploaded document (with source span + confidence)
AI_SUGGESTED    proposed by AI, not yet accepted
AI_GENERATED    AI text the user accepted
```

Provenance is stored on the field, survives edits, and is visible in the UI. AI never mutates
content in place: it emits proposals, the user accepts, and the accepted result is saved as a new
resume version (never an in-place edit) so before/after is always available via version history.

**Known limitation (Phase 5):** the `Resume` model tracks provenance per experience *entry*, not
per bullet, so an accepted single-bullet AI rewrite cannot currently be labelled `AI_GENERATED` at
the bullet level — the entry-level provenance stays `EXTRACTED` or `USER_PROVIDED` even after one
of its bullets was AI-rewritten. Documented in `app/ai/tailor.py::apply_proposals` rather than
silently gapped; version history (which version a bullet's text came from, and the proposal's
rationale shown at review time) is the practical substitute until per-bullet provenance exists.

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
| Learning priorities (reordering Phase 4's skill gaps) | 1 |
| Ranking order | 1 — never 3 |

## 10. Evaluation

`backend/tests/unit/test_fact_guard.py` exercises the guard directly against deliberately
hallucinated samples (a fabricated number, a fabricated technology, a genuine paraphrase that must
*not* false-positive) using a `FakeLLMProvider` (`backend/tests/ai_fakes.py`, mirroring the
`FakeEmbeddingProvider` pattern from Phase 4) rather than live API calls, so the suite stays fast,
hermetic, and free. Phase 6 extended this with coverage for the job-context widening (a job title
referenced verbatim must not be flagged, but a genuine resume-fact violation must still be caught
regardless) and for `app/ai/structured.py`'s JSON parse/schema-validate/one-repair-attempt/give-up
pipeline directly (malformed JSON, a schema mismatch, and a repair that succeeds on the second
attempt, each asserted against the exact number of provider calls made). A dedicated fixture
corpus of synthetic resumes/JDs with scored extraction-accuracy and prompt-version-tracked
evaluation runs — closer to a proper eval harness — is still not built; tracked as a Phase 7+
follow-up once recruiter screening gives the eval suite meaningfully more surface to measure.
