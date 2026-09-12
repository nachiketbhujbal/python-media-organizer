# ADR 0097: Pre-authorized unattended migration

- Status: Proposed
- Date: 2026-09-12
- Builds on: ADR 0089

## Context

Versions 0.6.0 through 0.6.4 retain the one-stage migration engine while adding
safe foreground advancement, terminal questions, an aggregate human synopsis,
explicit saved-context resume, and stable path-private reporting. They still
require an operator to answer each validation, reviewed-apply, external-
quarantine, and final-signoff checkpoint while the run is active.

Long-running local analysis makes that supervision burdensome. An operator who
already knows the exact decisions they are willing to approve needs a way to
state those decisions before the run without creating a general yes-to-all
switch or turning coordinator bookkeeping into evidence.

## Decision

Version 0.6.5 will add an explicit private pre-authorization contract over the
existing one-stage coordinator. It may cross only enumerated checkpoint
decisions whose expected current evidence is bound by the policy. Missing,
unknown, ambiguous, stale, or changed authority stops before the checkpoint is
crossed or a child is dispatched.

The final policy schema, invocation spelling, evidence bindings, consumption
rules, and status behavior will be specified here after inspection of the
current coordinator, state, outcome, interactive, and reporting contracts.

The mode will not move quarantine, delete media, weaken preview-before-apply,
broaden one authorization to a later checkpoint, fabricate evidence or human
sign-off, alter the action journal, change exact-media analysis, or add logging,
visibility, queue, or scheduling behavior.

## Consequences

- Unattended operation remains explicit, local, versioned, and fail closed.
- The existing one-stage engine and interactive/manual selectors remain
  compatible and authoritative for their current boundaries.
- Automatic duplicate disposition and permanent cleanup remain outside this
  release.
