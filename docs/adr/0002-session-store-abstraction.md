# ADR-0002: SessionStore abstraction with memory and Redis backends

Status: Accepted (2026-08-22)

## Context
The platform needs an ephemeral, TTL-driven store. Redis is the natural production choice, but the
development machine has neither Redis nor Docker installed. Requiring infrastructure to run the app
locally would slow every iteration; hardcoding Redis would make tests need a server.

## Decision
Define a SessionStore protocol (get/set/delete/expire/namespace-delete/scan) with two
implementations: MemorySessionStore (single-process, TTL heap plus janitor) for development and
tests, and RedisSessionStore (native key TTL, namespace index set) for production. Backend is
selected by SESSION_STORE_BACKEND.

## Consequences
Local development and the whole test suite run with zero infrastructure. Production gets Redis with
multi-worker safety. Startup validation refuses the memory backend when more than one worker is
configured, so the dev convenience can never become a production correctness bug. Both backends run
against the same conformance test suite, including TTL and namespace-deletion semantics.
