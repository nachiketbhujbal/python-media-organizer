# ADR 0013: Keep video fingerprints in disposable SQLite state

- Status: Accepted
- Date: 2026-08-21

## Context

Exact video decoding is expensive and should not be repeated between a reviewed
dry run and apply. Derived data is not authoritative history.

## Decision

Store fingerprints in collection-local `.pymo.sqlite3`, keyed by content,
algorithm, and FFmpeg version. Save successful misses incrementally. Keep action
history in JSONL; `--no-cache` disables cache reads and writes.

## Consequences

The cache can be deleted and rebuilt. Moving a collection preserves useful
derived work without coupling undo to a database.
