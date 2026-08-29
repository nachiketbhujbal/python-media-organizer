# ADR 0071: Make validation evidence reuse explicit and exact

- Status: Accepted
- Date: 2026-08-23

## Context

Fresh full validation is the strongest current health check because an older
healthy record cannot prove present readability. Repeating full image and video
decodes is nevertheless expensive when the user deliberately accepts cached
evidence for an unchanged collection. This performance mode must be visibly
distinct from ordinary validation and must preserve warnings, errors, privacy,
and health exit status.

A content hash alone is insufficient. Compatibility also depends on the
requested profile, validation algorithm, extension and detected-kind context,
Pillow or native-tool versions, and the exact current file observation. A file
may also change between selecting a cache row and reporting it.

## Decision

Add `--reuse-validation` to standard and full validation. The mode first
performs normal descriptor-backed discovery and resolves the applicable current
runtime versions. It reuses a result only when one coordinated cache snapshot
contains an exact-state file observation with a complete hash and strict
validation evidence matching profile, algorithm, semantic context, and runtime.

Every proposed hit is then reopened through the collection-anchored stable
descriptor boundary without reading its content. A changed, replaced, or unsafe
path is rejected as a hit. Every miss is freshly validated and published under
the v0.4.11 rules. Cached findings become ordinary report findings, including
their warning/error health and exit status.

`--reuse-validation` may use the collection-local or explicit external cache
but cannot be combined with `--no-cache`. Missing evidence is an ordinary miss.
Invalid known evidence remains a fail-closed error. Schema-2 JSON reports mode,
reused records, freshly validated files, fresh-execution status, and records
written without revealing paths.

## Consequences

- Ordinary `validate` and `validate --full` remain always fresh and report zero
  reused records.
- The explicit mode can avoid Pillow and FFmpeg decoding for exact compatible
  hits, but must still resolve/version native video tools to prove runtime
  compatibility.
- A cached error remains an error; reuse is not a health override.
- Migration certification and any workflow requiring current readability
  should use the fresh default, not this performance mode.
