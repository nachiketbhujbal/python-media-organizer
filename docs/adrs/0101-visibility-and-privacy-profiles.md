# ADR 0101: Define visibility and privacy profiles

- Status: Proposed
- Date: 2026-09-12

## Context

Pymo currently exposes console severity and path disclosure through separate
global and command-local flags. The controls are individually conservative,
but operators must remember several spellings to request a coherent rich,
private, or quiet view. Version 0.6.7 owns one compatibility-preserving profile
layer over those existing controls.

## Proposed direction

Define explicit full, private, and quiet visibility profiles while preserving
the current path-private default. Specify deterministic compatibility with
`--verbose`, `--quiet`, `--show-files`, `--show-ignored`, explicit log-level
selectors, timestamps, structured output, and migration restart/resume state.
Reject ambiguous explicit combinations before collection or persistent work.

This ADR will be completed before behavior changes are accepted. It does not
authorize automatic diagnostic persistence, default path disclosure, report
schema changes, migration authority, duplicate disposition, queueing,
scheduling, quarantine movement, deletion, or exact-media changes.
