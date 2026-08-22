# ADR 0014: Make scan strictly read-only

- Status: Accepted
- Date: 2026-08-22

## Context

Users need aggregate collection facts before deciding whether expensive or
mutating work is worthwhile.

## Decision

`pymo scan` reports inventory, readiness, duplicate potential, estimated work,
and local state without moving media or creating action/cache state. JSON is
path-private unless ignored paths are explicitly requested.

## Consequences

Fast same-size and optional checksum results are estimates, not substitutes for
exact pixel or playback matching.
