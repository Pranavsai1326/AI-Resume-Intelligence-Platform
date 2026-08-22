# PRIVACY ARCHITECTURE

**Last updated:** 2026-08-22

Privacy here is an architectural property, not a policy sentence. The guarantee is: *no code path
exists that writes user content to durable storage.* This document defines that model, the layers
that enforce it, the tests that prove it, and — importantly — the limits we state honestly.

## 1. Threat model

| Concern | Mitigation |
|---|---|
| Operator or attacker reads stored resumes later | No durable store exists; nothing to read after TTL |
| Browser crash leaves data alive server-side | TTL is authoritative; tab-close is only an optimisation |
| One session reads another session's data | Namespaced keys + session-scoped authorisation on every access |
| Resume content leaks into logs/metrics/traces | Redaction processor + explicit privacy tests over log output |
| Temp files survive processing | Deleted in `finally`, plus janitor sweep, plus startup sweep |
| Third-party AI provider retains content | Data minimisation + redaction before sending; honest disclosure about provider retention |
| Exported documents linger on disk | Rendered in memory and streamed; no export directory |

## 2. Data classification

| Class | Examples | Storage |
|---|---|---|
| **User content** (never persisted) | resume file/text/JSON, name, email, phone, address, education, employment, skills, projects, certifications, JD text, candidate data, analyses, generated resumes, cover letters, interview content, AI conversations | Ephemeral session store with TTL only |
| **Session technical metadata** | `session_id`, timestamps, mode, counters | Ephemeral session store with TTL |
| **Operational metrics** (content-free) | latency, error category, queue depth, token counts | Aggregate metrics backend, no content, no per-user identity |
| **System configuration** | feature flags, weights, limits | Config files/environment, no user data |

## 3. The four cleanup layers

Tab-close events are explicitly **not** the deletion mechanism (Rule 12).

```
Layer 1  Client cleanup      pagehide/visibilitychange -> sendBeacon DELETE /v1/session   (best effort)
Layer 2  TTL expiry          every key carries its own TTL; idle TTL + absolute cap        (authoritative)
Layer 3  Janitor sweep       periodic task: expired namespaces, orphaned keys, temp files  (safety net)
Layer 4  Startup sweep       temp dir purged on boot; stale namespaces reconciled          (crash recovery)
```

Layer 2 alone is sufficient for correctness. Layers 1, 3 and 4 reduce the window and clean up after
crashes, forced termination, device shutdown, and network loss.

## 4. Browser storage policy

* **Never** in `localStorage`, persistent IndexedDB, or persistent cookies: resume content, JD
  content, candidate data, analyses, generated documents.
* Application state lives in **in-memory** stores (Zustand, React state, TanStack Query cache with a
  bounded `gcTime`). A page reload legitimately loses in-flight UI state; the server session is the
  source of truth until it expires.
* `sessionStorage` holds **only** `session_id` and `session_mode` — technical metadata. We document
  that `sessionStorage` survives reload and per-tab restore, which is why it may not hold content.
* A lint rule plus a test forbid `localStorage`/`indexedDB` usage outside an allowlisted theme
  preference module.

## 5. Server storage policy

* Uploaded bytes are processed from memory (`SpooledTemporaryFile`); they touch disk only when size
  forces spooling, into a dedicated temp directory with `0700` permissions and random names that
  never include the user's filename.
* Every temp path is created inside a context manager that deletes in `finally`, including on
  exception and cancellation.
* Extracted text, structured resumes, embeddings, analyses and generated documents live in the
  session store under TTL — never copied anywhere else.
* Exports are rendered to an in-memory buffer and streamed. There is no export directory and no
  download URL that outlives the response.

## 6. Session isolation

Every request carries `X-Session-Id`. Resolution:

1. Look up `sess:{id}:meta`. Missing or expired -> `410 SESSION_EXPIRED` (never auto-recreate
   silently into a stale context).
2. Check the absolute cap independently of idle TTL.
3. All subsequent reads/writes are constructed from the resolved session's namespace only. No API
   accepts a caller-supplied namespace, key or path.
4. Cross-session access is impossible by construction; a test asserts session B cannot read session
   A's objects by guessing any identifier.

## 7. AI provider privacy

* Only the minimum text needed for an operation is sent — a single bullet for bullet rewriting, not
  the whole resume (see [AI_ARCHITECTURE.md](AI_ARCHITECTURE.md) §7).
* Direct identifiers (name, email, phone, address, URLs to personal profiles) are replaced with
  stable placeholders before the call and restored locally afterwards, unless the operation
  genuinely needs them (e.g. a cover letter salutation the user asked for).
* For recruiter screening, protected attributes are redacted before any model sees the text.
* Provider responses are used and discarded with the session; never written elsewhere.
* We **do not** claim providers retain nothing. The UI states which provider is configured and links
  to its retention terms. Our own zero-persistence guarantee holds regardless of the provider.
* A "local-only mode" is supported: with no LLM provider configured, embeddings run locally and the
  entire deterministic pipeline works without any external network call.

## 8. Logging policy

Logs may contain: `request_id`, truncated `session_id` (8 chars), operation, status, duration,
error category, model name, token counts.

Logs must never contain: resume content, JD content, personal identifiers, filenames, file bytes,
full prompts or completions containing user data, or stack traces sent to users.

Enforcement: a structlog processor redacts known-sensitive keys and pattern-matches emails, phone
numbers and long free-text blobs; a privacy test drives a realistic resume through the full pipeline
and asserts that no distinctive token from it appears in captured log output.

## 9. Analytics policy

Anonymous aggregate operational metrics only. No cross-session tracking, no fingerprinting, no
advertising identifiers, no session ID reuse as a stable user key. Metric labels are drawn from a
fixed enum so user content cannot become a label value.

## 10. Privacy test suite (`backend/tests/privacy/`)

These are product requirements, not optional extras:

1. No resume content is written to any durable path — filesystem watcher over the whole workspace
   during a full pipeline run asserts only allowlisted temp paths are touched, and that they are gone
   afterwards.
2. No personal information persists after `DELETE /v1/session`.
3. Expired sessions are removed by TTL without any client call.
4. Temp files are deleted on success, on exception, and on cancellation.
5. A restarted app cannot restore data from a previous session.
6. A new session starts empty.
7. Session B cannot read session A's objects.
8. Logs contain no resume content.
9. Export responses leave no server-side artifact.
10. Job queue entries for an expired session are cancelled and their inputs dropped.

## 11. What we tell users — and what we refuse to claim

**We say:**

> No account required. Your resume is processed in a temporary session. We do not build a permanent
> resume profile. Temporary data is removed by a combination of client cleanup, session expiry, and
> automatic server-side cleanup.

**We do not say:** "deleted the instant you close the tab", "we never see your data", "zero
retention guaranteed end-to-end", or "fully anonymous". Where a limit exists — provider retention,
the TTL window, best-effort tab-close cleanup — the UI states it plainly.
