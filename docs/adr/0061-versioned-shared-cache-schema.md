# ADR 0061: Use a versioned shared derived-cache schema

- Status: Accepted
- Date: 2026-08-22

## Context

The collection-local SQLite database began as one exact-video fingerprint
table. Its descriptor-pinned reads, process lock, private staging, and atomic
publication are reusable, but the unversioned video-specific schema cannot
safely hold whole-file hashes, probes, image fingerprints, or validation
evidence. Migration verification must also be able to analyze a read-only media
root while placing disposable evidence at a separate writable location.

Existing valid video caches may contain expensive completed decodes. Silently
discarding them would waste work, while mutating a public cache during an
ordinary read would violate the read-only and crash-safety boundaries.

## Decision

Keep `.pymo.sqlite3` as disposable derived state and JSONL action history as the
only authoritative mutation journal. Move cache filesystem coordination into a
schema-neutral service whose pinned cache directory is independent of the
media root being analyzed.

Schema version 1 contains exactly three tables:

- one singleton schema-version record;
- generic derived evidence keyed by whole-file SHA-256, evidence type,
  algorithm version, and runtime version, with a validated JSON payload;
- file observations keyed by an explicit analysis scope and relative path,
  retaining device, inode, size, modification/change times, and an optional
  verified whole-file SHA-256.

Validate SQLite integrity, exact tables and columns, the single supported
version, and every row before reuse. Reject unknown objects, future versions,
malformed JSON, invalid hashes, and unsafe relative paths without deleting or
rewriting the database.

Continue reading the prior exact-video table through a read-only descriptor.
Do not upgrade it on lookup. On the next successful cache write, copy the
validated legacy database into the private in-memory build, migrate its rows to
generic exact-video evidence, merge the new record, validate and sync the
staged database, and publish it through the existing atomic exchange boundary.
The public legacy database remains byte-for-byte intact if any step fails.

## Consequences

Current exact-video users retain completed work and receive an automatic,
atomic format upgrade only when new evidence is durably saved. Invalid caches
continue to fail closed and remain available for inspection or manual move-aside
recovery.

Later cache commands can add evidence types without creating parallel database
files or weakening algorithm/runtime invalidation. File observations establish
the identity vocabulary needed for stable-hash reuse, but an observation or
cache record is never proof that current bytes remain readable; commands must
recheck the file state required by their own safety contract.

The cache-location/media-root separation is now available below the CLI. Public
external-cache selection, status, warming, and additional evidence producers
remain separate releases.
