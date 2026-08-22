# ADR 0062: Inspect cache state without creating cache state

- Status: Accepted
- Date: 2026-08-22

## Context

The shared cache needs an operator-facing health and coverage report before
warming and additional evidence producers are added. The existing coordinated
cache reader intentionally opens or creates `.pymo.sqlite3.lock`, which is
appropriate for duplicate analysis but would violate a strictly read-only
status command. A status check must also work when the media collection is
read-only and the inspected cache lives at an explicit separate location.

SQLite schema validity alone is not enough for a useful report. Known evidence
payloads have producer-specific rules, file observations can become stale, and
algorithm compatibility is distinct from runtime compatibility. Status output
must remain path-private and must not imply that content-keyed evidence is
currently reusable when no current file observation or runtime check proves it.

## Decision

Add `pymo cache status COLLECTION [--cache PATH] [--json]`. The default path is
the collection-local `.pymo.sqlite3`; `--cache` selects an external cache for
this inspection only and does not enable external writes in another command.

Open the cache directory and database through no-follow descriptors in
read-only SQLite mode. Do not create or acquire the persistent cache lock, a
database, a directory, a sidecar, an action log, or any other collection state.
Recheck the public cache and directory identity after inspection. If an atomic
publisher changes either one concurrently, fail the status snapshot instead of
presenting stale results as current.

Validate SQLite integrity, the exact shared or legacy schema, every generic
row, and every known exact-video payload. Report aggregate evidence types and
namespaces, current versus stale algorithm records, file-observation freshness,
and evidence linkage to observations. Walk each observed relative path through
collection-anchored no-follow directory descriptors. Never print the
collection root, cache path, filenames, scopes, hashes, algorithms, or runtime
strings. Runtime compatibility is explicitly not checked; the consuming
command remains authoritative for runtime-specific reuse.

Machine-readable output uses cache-status report schema 1. Missing and healthy
legacy/current caches return 0, an unsafe, unreadable, corrupt, malformed, or
incompatible cache returns 1, and invalid command setup returns 2. A legacy
cache is reported as healthy with migration pending and remains byte-for-byte
unchanged.

## Consequences

Operators can safely see whether expensive evidence exists and whether its
recorded file identities remain current before running another command. A
missing cache is ordinary rather than an error, and status can inspect a cache
outside a read-only collection without placing any state in the collection.

The report deliberately cannot promise exact-video cache hits because it does
not invoke FFmpeg to compare runtime versions or hash unobserved current files.
Future warm, stable-hash, probe, image, and validation releases can populate
observations and add known evidence validators without changing the read-only
snapshot boundary.
