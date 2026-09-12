# ADR 0099: Separate logging surfaces and levels

- Status: Proposed
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

Reserve version 0.6.6 for explicit separation of console logging, opt-in
durable diagnostics, migration-private state and stage logs, human synopses,
and structured reports, together with compatible conventional log-level
selection for applicable human-readable commands.

The implementation must preserve opt-in persistence, existing path privacy,
structured-output purity, console timestamp behavior, migration state
semantics, and the current `--verbose` and `--quiet` interfaces. Visibility
profiles and any `--debug` alias remain version 0.6.7 work.

## Consequences

- Logging-level selection grants no path-disclosure or persistence authority.
- Restart state, stage outcomes, action history, and reports are not ordinary
  diagnostic log destinations.
- Automatic logs, duplicate disposition, queueing, scheduling, quarantine
  movement, deletion, and exact-media changes remain outside version 0.6.6.
