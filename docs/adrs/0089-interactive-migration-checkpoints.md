# ADR 0089: Add conservative interactive migration checkpoints

- Status: Accepted
- Date: 2026-09-11
- Extends: ADR 0088

## Context

Version 0.6.0 can advance routine migration stages in one foreground process,
but it still returns control to the shell at every validation review, apply,
duplicate-disposition, and final-signoff boundary. Those boundaries are
necessary; requiring the operator to reconstruct and re-enter a long command
at each one is not.

An interactive driver must not become hidden preauthorization. It also cannot
infer consent from a terminal, an empty response, a warning-only validation
status, or a prior preview. Restart state must continue to show which human
decisions were actually accepted.

## Decision

Version 0.6.1 adds an explicit `migrate --interactive` selector over the same
restartable one-stage coordinator used by `--run` and `--run-next`. It requires
a usable terminal input and asks a conservative yes-or-no question only when
the current validated lifecycle reaches one of these boundaries:

- review of a successful or status-one validation;
- authorization of one pending reviewed apply stage;
- confirmation that the externally managed `dups` quarantine is absent; or
- final human sign-off after ordinary fresh verification.

Only `yes` or `y`, ignoring case and surrounding whitespace, authorizes the
current question. An empty or negative response stops normally. Invalid input,
end-of-file, or unavailable non-terminal input stops with a setup error.
Interruptions retain status 130 through the existing command boundary. No
answer authorizes a later checkpoint.

Accepted mutation questions still call the existing one-stage apply path and
must satisfy exact attempt, state-binding, and collection-identity transition
checks before the loop continues. Successful validation review and final
sign-off receive explicit private restart-state attempts so an interrupted
interactive session can resume without inventing consent. Existing status-one
acknowledgement and external-quarantine confirmation retain their current
actions and checks.

`--run`, `--run-next`, `--accept-status`, `--confirm-quarantine`, and
`--run-next --apply` remain noninteractive and compatible. This release does
not add saved command shortcuts, unattended authority, migration summaries,
machine-readable reports, duplicate movement, deletion, queues, or scheduling.

## Consequences

- One foreground process can cross routine and explicitly accepted human
  checkpoints without weakening the stage engine.
- Restart state records interactive review and sign-off decisions but remains
  private bookkeeping rather than preservation evidence or action history.
- Redirected or scripted answers are deliberately rejected; a separately
  designed preauthorization policy remains version 0.6.5 work.
- Tests must cover every accepted, declined, invalid, interrupted, stale-state,
  substituted-root, and resumed-decision boundary while proving no answer can
  authorize more than its current checkpoint.
