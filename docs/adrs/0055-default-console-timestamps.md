# ADR 0055: Timestamp normal console logging by default

- Status: Accepted
- Date: 2026-08-22

## Context

Long-running media analysis already reports monotonic elapsed time, observed
rates, ETA, heartbeats, and exact-video stage durations. Those measurements
show how much work has elapsed but do not place individual console records on a
wall-clock timeline unless the user remembers to request `--timestamps` before
starting the command. That makes it harder to correlate ordinary runs with
other local events or compare copied excerpts from a long session.

Console timestamps are presentation data. They must not contaminate the stable
JSON produced by `scan` and `validate`, change any analysis or mutation
semantics, or determine elapsed durations. Some interactive uses also benefit
from the earlier plain presentation, so the change needs a direct opt-out.

## Decision

Prefix every physical line emitted through normal human-readable command
logging with a timezone-aware ISO timestamp by default. Add the global
`--no-timestamps` option to select plain console output. Retain `--timestamps`
as an accepted, idempotent spelling for backward compatibility and for callers
that want to state the default explicitly. The two options are mutually
exclusive.

Continue to disable console timestamp formatting for `scan --json` and
`validate --json` regardless of either global option. Help, version, and
argument-parser usage or error output occur before command logging is
configured and remain plain. Explicitly requested log files continue to carry
timestamps, levels, and logger names on every physical line regardless of the
console opt-out.

Keep duration, rate, ETA, and stage calculations on monotonic clocks. Wall-clock
timestamps are for correlation only and do not replace or influence those
measurements.

## Consequences

Ordinary console transcripts now contain useful time correlation without an
extra flag, including multi-line records and warnings or errors emitted after
command dispatch. Users who prefer compact terminal output can recover the
previous presentation with `--no-timestamps`, while existing automation that
passes `--timestamps` continues to work.

Structured consumers receive the same clean schema output as before, and the
release does not alter media discovery, analysis, dry-run, mutation, cache,
action-log, or verification behavior.
