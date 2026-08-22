# ADR-0003: No application database

Status: Accepted (2026-08-22)

## Context
Conventional SaaS architecture starts with Postgres plus an ORM. Here the product requirement is
zero persistence of user data, and a database is the single largest risk of accidental persistence:
migrations, backups, replicas, query logs and connection-pool traces all retain content.

## Decision
Ship no application database. No ORM, no migrations, no users/resumes/candidates tables. All user
content lives in the ephemeral session store under TTL. Configuration and feature flags come from
environment and config files. Metrics go to a content-free aggregate metrics backend.

## Consequences
The zero-persistence guarantee becomes structural: there is no durable table to write to. Operations
get simpler (no backup or migration surface). If a genuinely non-user operational need for durable
storage appears later, it requires a new ADR that explicitly states why it cannot hold user content.
