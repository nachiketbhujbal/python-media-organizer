# ADR 0018: Test only with synthetic, collection-neutral data

- Status: Accepted
- Date: 2026-08-21

## Context

Real media collections and their names are private and must never enter source,
fixtures, output snapshots, or Git history.

## Decision

Tests create temporary synthetic pictures, videos, metadata, paths, and generic
collection names. Repository safeguards ignore common media and collection
layouts.

## Consequences

Integration tests may generate tiny local FFmpeg fixtures. Release sweeps check
tracked files and history for private collection references.
