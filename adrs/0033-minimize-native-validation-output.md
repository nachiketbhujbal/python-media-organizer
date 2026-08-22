# ADR 0033: Minimize native validation output

- Status: Accepted
- Date: 2026-08-22

## Context

ffprobe and FFmpeg can emit detailed diagnostics containing filenames, stream
metadata, and decoder internals. Validation needs a small structural result,
not arbitrary tool diagnostics, and default output must remain path-private.

## Decision

Request only the ffprobe stream and format fields used by validation, capture
only its JSON standard output, and discard its diagnostic stream. Full FFmpeg
decode validation discards both output streams. User-facing failures use stable,
generic descriptions instead of relaying native-tool output.

## Consequences

Validation retains the metadata needed for deterministic health findings while
reducing memory, disclosure, and unstable-output risks. Low-level decoder text
is intentionally unavailable in ordinary reports; a future diagnostic mode
would require a separate privacy decision.
