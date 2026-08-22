# ADR 0003: Use one fixed collection layout

- Status: Accepted
- Date: 2026-08-21

## Context

All commands need predictable ownership without per-command folder arguments.

## Decision

A media collection uses `pics`, `vids`, and `dups`; image review owns
`dups/pics`, while video review owns `dups/vids`. These paths are package
invariants centralized in `CollectionLayout`, not user configuration.

## Consequences

Commands can validate readiness and remain independent across media kinds.
Collections using different folder names must be organized first.
