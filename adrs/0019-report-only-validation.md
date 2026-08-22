# ADR 0019: Introduce validation as report-only

- Status: Accepted
- Date: 2026-08-22

## Context

Corrupt, truncated, mismatched, or ambiguous media must be understood before any
repair or quarantine workflow is safe.

## Decision

The first `pymo validate COLLECTION` release only reports health findings. It
does not delete, repair, quarantine, rename, move, or append action history.

## Consequences

Validation can evolve independently of mutation policy. Any future quarantine
or repair command requires a separate ADR and shared action-log integration.
