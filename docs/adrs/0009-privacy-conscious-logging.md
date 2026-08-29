# ADR 0009: Use Python logging without persistent logs by default

- Status: Accepted
- Date: 2026-08-21

## Context

Operational output is useful, but filenames and paths can be private.

## Decision

Route command output through standard-library logging. Console output is normal;
persistent logs require `--log-file`. Ignored names require the separate
`--show-ignored` opt-in and are collection-relative.

## Consequences

Normal runs leave no log artifact. Explicit logs and detailed path output must
be treated as private data.
