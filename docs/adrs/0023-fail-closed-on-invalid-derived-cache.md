# ADR 0023: Fail closed on an invalid derived cache

- Status: Accepted
- Date: 2026-08-22

## Context

The video fingerprint database is disposable, but silently treating a corrupt
or incompatible database as empty can waste hours of decoding before a later
write fails. Malformed rows must never become trusted exact-match evidence.

## Decision

Open an existing cache read-only, validate the expected schema query and every
returned hash and count, and stop before decoding when the cache is invalid.
Do not automatically delete or replace it. Explain that the user may move the
cache aside or deliberately bypass it with `--no-cache`.

## Consequences

Cache damage is visible immediately and cannot create false duplicate groups.
Recovery requires an explicit user choice, preserving the unexpected file for
inspection and honoring pymo's no-surprise deletion policy.
