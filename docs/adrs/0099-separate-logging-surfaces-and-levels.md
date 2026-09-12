# ADR 0099: Separate logging surfaces and levels

- Status: Accepted
- Date: 2026-09-12
- Applies: ADR 0087

## Context

Pymo currently routes human-readable command output through Python logging,
offers `--verbose` and `--quiet`, writes a durable log only when `--log-file`
is explicit, and gives `migrate --log-dir` separate ownership of private
restart state and per-stage logs. Human synopses and structured JSON reports
are further distinct surfaces with their own privacy and compatibility rules.

The operator roadmap assigns version 0.6.6 one narrow purpose: make those
surfaces and their conventional severity selection coherent without changing
visibility or path-disclosure policy.

## Decision

Version 0.6.6 separates five surfaces:

1. ephemeral human-readable console logging;
2. one explicitly requested append-only diagnostic `--log-file`;
3. the migration coordinator's explicitly requested private restart directory,
   per-stage logs, and typed outcomes;
4. the path-private human migration synopsis; and
5. structured JSON reports with their own versioned schemas.

The first two surfaces accept independent conventional thresholds through
`--console-log-level` and `--file-log-level`. The accepted values are `DEBUG`,
`INFO`, `WARNING`, `ERROR`, and `CRITICAL`, case-insensitively. The console
selector conflicts with the compatible `--verbose` and `--quiet` aliases.
Without an explicit selector, the console remains at `INFO`, `--verbose`
selects `DEBUG`, and `--quiet` selects `WARNING`. An explicit diagnostic file
remains at `INFO` by default; `--verbose` retains its historical `DEBUG` file
default, while `--quiet` no longer suppresses informational file evidence.

`--file-log-level` requires `--log-file` for ordinary commands. For `migrate`,
the same option controls the already-explicit per-stage files in `--log-dir`;
the console and file thresholds are saved with the rest of the exact
coordinator invocation in private restart-state schema 3 and recovered by
`--resume`.

An ordinary diagnostic log remains opt-in, is opened at its exact leaf without
following a symbolic link, rejects non-regular or multiply linked leaves,
appends rather than truncates, and is created with mode `0600`. Pymo never
rotates, prunes, replaces, or deletes it. Retention is therefore an explicit
operator decision, not a time- or size-based automatic policy.

The implementation preserves opt-in persistence, existing path privacy,
structured-output purity, console timestamp behavior, migration stage and
evidence semantics, and the current `--verbose` and `--quiet` interfaces.
Selecting a threshold grants neither filename disclosure nor persistent-output
authority. Visibility profiles and any `--debug` alias remain version 0.6.7
work.

## Consequences

- Logging-level selection grants no path-disclosure or persistence authority.
- Restart state, stage outcomes, action history, and reports are not ordinary
  diagnostic log destinations.
- Existing v0.6.5 migration restart state is deliberately not accepted by the
  schema-3 v0.6.6 coordinator; a migration remains bound to the pymo version
  that created it.
- Explicit diagnostic and stage logs accumulate until the operator archives or
  removes them. Pymo does not claim a retention period or automatic cleanup.
- Automatic logs, duplicate disposition, queueing, scheduling, quarantine
  movement, deletion, and exact-media changes remain outside version 0.6.6.
