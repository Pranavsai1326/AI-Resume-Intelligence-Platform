# SECURITY

**Last updated:** 2026-08-22

The platform accepts untrusted binary documents from anonymous users and forwards derived text to an
AI provider. Those two facts drive the whole security posture.

## 1. Trust boundaries

```
Anonymous browser  --untrusted-->  API  --untrusted-->  Document parsers
                                    |
                                    +-->  Session store (trusted, ephemeral)
                                    +-->  AI provider (external, minimised + redacted payloads)
                                    +-->  Chromium renderer (untrusted content, sandboxed)
```

## 2. Upload security

Uploaded files are hostile input until proven otherwise:

* **Size** — enforced by streaming counter *before* buffering (`MAX_UPLOAD_BYTES`, default 10 MB);
  the request is aborted mid-stream rather than after full receipt.
* **Type** — magic-byte sniffing, not the client-supplied `Content-Type` or extension. Allowlist:
  PDF, DOCX (ZIP+OOXML), TXT (UTF-8/latin-1 decodable).
* **Structure limits** — max PDF pages, max embedded objects, max DOCX uncompressed size and entry
  count (zip-bomb defence), max archive nesting depth.
* **XML safety** — DOCX OOXML parsed with `defusedxml`: no external entities, no DTDs, no entity
  expansion.
* **PDF safety** — parsing runs with JavaScript and external resource resolution disabled; no
  embedded file extraction; parser runs under a wall-clock timeout and memory ceiling.
* **Filenames** — never trusted, never echoed into a path. Temp names are random; the original name
  is used only as a display label after sanitisation, and is not logged.
* **Timeouts** — every parse stage is bounded; a hung parse fails the job rather than the process.

## 3. Session security

* `session_id` = 256 bits from `secrets.token_urlsafe`, opaque, unguessable, not a user identifier.
* Transported as `X-Session-Id` (not a cookie), which sidesteps CSRF for session-bearing requests
  because a cross-origin form or image cannot set custom headers.
* Strict CORS allowlist from `CORS_ORIGINS`; wildcard-with-credentials is rejected at startup.
* Every data access derives its key from the server-resolved session; no endpoint accepts a
  caller-supplied key, namespace, or path.
* Sessions expire on idle TTL and on an absolute cap that activity cannot extend.
* Session IDs are logged truncated (8 chars) and never used as an analytics key.

## 4. Rate limiting and abuse control

Token-bucket limits, backed by the same store as sessions, applied per IP and per session:

| Bucket | Default |
|---|---|
| Session creation per IP | 30 / hour |
| Uploads per session | 120 / hour |
| Bulk resumes per session | 100 concurrent max, `MAX_BULK_RESUMES` |
| AI calls per session | 100 / hour, plus a token budget |
| Export per session | 60 / hour |
| Global request rate per IP | configurable, `429` with `Retry-After` |

AI spend is additionally bounded by per-session token counters so one anonymous session cannot
exhaust the provider budget. Limits are configuration, tuned before production launch.

## 5. HTTP hardening

* HTTPS only in production; HSTS with a long max-age.
* `Content-Security-Policy` with no `unsafe-eval`; script sources restricted to self.
* `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `X-Frame-Options: DENY` / `frame-ancestors 'none'`, `Permissions-Policy` denying camera,
  microphone, geolocation.
* `Cache-Control: no-store` on every API response carrying user content, and on exports.
* Request body size capped at the reverse proxy as well as in the app.
* Request ID assigned per request and returned to the client for support correlation.

## 6. Output and injection safety

* React escapes by default; `dangerouslySetInnerHTML` is banned by lint rule. Any rendered
  document/AI text is treated as text, not markup.
* Export templates escape all user content; PDF rendering runs with a sandboxed browser context,
  no network access, and a render timeout.
* **Prompt injection:** uploaded documents may contain instructions aimed at the model. Mitigations:
  user content is passed in clearly delimited, labelled fields marked as data; system prompts state
  that document content is never an instruction; outputs are schema-constrained; and no model output
  is allowed to trigger a side effect — the LLM cannot call tools, change scores, alter weights,
  modify session state, or apply an edit. Applying a proposal is always an explicit user action.
* Generated file names are sanitised; `Content-Disposition` values are quoted and stripped of CR/LF.

## 7. Secrets

* Provider keys come from environment or a secret manager only. No key is committed, printed,
  logged, or included in an error response or health payload.
* `/ready` reports capability booleans (`llm: true`), never key material or provider endpoints.
* Startup validates that required secrets exist for the selected providers; a missing key selects
  the Null provider (honest degradation) rather than crashing in production traffic.
* Repository has a secret-scanning pre-commit hook and CI check.

## 8. Error handling

A single exception middleware maps every error to the sanitised envelope in [API.md](API.md). Users
receive a category, a readable message and a `request_id`. Stack traces, file paths, library
versions, SQL/Redis errors and provider payloads stay in server logs — themselves redacted per
[PRIVACY_ARCHITECTURE.md](PRIVACY_ARCHITECTURE.md) §8. Unhandled exceptions never propagate raw to
the client.

## 9. Dependency and supply-chain security

* Pinned lockfiles for both stacks; CI runs `pip-audit` and `npm audit` and fails on high severity.
* Dependency additions are justified in review — every new parser is new attack surface.
* Frontend has no CDN-loaded scripts; assets are self-hosted.
* Container images (when introduced in Phase 9) run as a non-root user with a read-only root
  filesystem except the temp directory, which is `noexec`.

## 10. Responsible-screening safeguards (security-adjacent, product-critical)

* `screening/redact.py` strips protected and irrelevant attributes — name, photo, gender markers,
  age/DOB, marital status, nationality, religion, caste, race — before scoring and before any model
  call, and records which categories were removed.
* Ranking features come from an explicit allowlist; adding a feature requires a code change and
  review, so a protected attribute cannot leak into scoring through configuration.
* Blind-review mode (candidate identity hidden until shortlisting) is the default in recruiter mode.
* The product states that these measures reduce bias; it never claims to eliminate it.

## 11. Testing and verification

Security tests live beside the privacy suite: oversized upload rejection, MIME spoofing, zip bomb,
XXE payload, malformed PDF, path traversal in filenames, cross-session access attempts, rate-limit
enforcement, security-header presence, error sanitisation (no stack trace, no path), and prompt
injection samples that attempt to make the model emit instructions or unsupported claims.
