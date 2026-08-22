# ADR 0010: Rename deterministically without visual guessing

- Status: Accepted
- Date: 2026-08-21

## Context

Source filenames vary widely, while visual AI would add complexity, latency,
and privacy concerns.

## Decision

Build names from the collection slug, media kind, stable sequence, trustworthy
embedded or filename timestamps, and conservative cleaned descriptors. Use
`undated` when evidence is absent.

## Consequences

Names are predictable and reversible but do not claim to describe visual
content. Local AI suggestions remain future opt-in work.
