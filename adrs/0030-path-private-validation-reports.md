# ADR 0030: Keep validation reports path-private by default

- Status: Accepted
- Date: 2026-08-22

## Context

Validation findings are useful but filenames and collection structure can be
sensitive. Machine-readable output also needs a stable contract that cannot be
polluted by progress or runtime messages.

## Decision

Default text and schema-1 JSON aggregate findings by severity and code without
collection names, roots, or filenames. `--show-files` explicitly adds sorted
collection-relative affected paths, and `--show-ignored` separately controls
ignored paths. JSON suppresses human progress and CLI completion records.

## Consequences

Routine reports are safe to inspect or redirect without casually disclosing
names. Actionable per-file reports remain available through a deliberate,
local privacy opt-in.
