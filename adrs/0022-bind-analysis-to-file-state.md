# ADR 0022: Bind exact analysis to stable file state

- Status: Accepted
- Date: 2026-08-22

## Context

Image pixels and decoded video fingerprints are conclusions about particular
file contents. A file can be edited or replaced after analysis, making a
previous duplicate group unsafe to apply even when its pathname is unchanged.

## Decision

Capture device, inode, size, modification time, and change time before exact
analysis and require the same regular-file state afterward. Revalidate every
duplicate-group member before mutation, each retained original while moves are
performed, and all retained originals before committing the action-log run.

## Consequences

Changing inputs are skipped during analysis or cause an applied run to stop
safely. This is deliberately conservative: a metadata-only change also
requires another analysis pass rather than risking a stale exact-match result.
