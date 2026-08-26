# ADR 0002: Default mutations to previews and never delete media

- Status: Accepted
- Date: 2026-08-21

## Context

Organization mistakes can destroy irreplaceable media or overwrite a different
file with the same name.

## Decision

Every mutating command is a dry run unless `--apply` is explicit. pymo never
deletes media and never overwrites an occupied path. Applied moves are verified.

## Consequences

Users review an extra step and manually delete isolated duplicates if desired.
Safety failures stop the run instead of guessing.
