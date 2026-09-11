# ADR 0088: Add a foreground safe migration operator loop

- Status: Accepted
- Date: 2026-09-11
- Extends: ADR 0084

## Context

The guided migration coordinator deliberately executes one stage per
invocation. That restartable boundary is safe and auditable, but operational
trials showed that manually repeating the same command for every routine stage
is tiring and error-prone. The safety problem is not the stage engine; it is
the lack of a foreground driver that can reuse it without treating a decision
as routine work.

## Decision

Version 0.6.0 adds a foreground operator loop over the existing restartable
one-stage coordinator. The loop may automatically advance only stages that
finish successfully and require no operator decision. It stops at every
validation review, mutation authorization, duplicate quarantine, final-signoff,
nonzero-status, ambiguous-state, and unsafe-state boundary. Because validation
warnings return status 0, the loop conservatively pauses after every successful
validation rather than trying to infer a warning-free result from exit status.

The one-stage engine and its persisted attempt lifecycle remain authoritative.
The loop reloads and validates that lifecycle after each successful child,
requiring the exact prior attempt prefix plus one successful non-apply attempt
for the dispatched stage and a one-stage advance. It retains its root,
tool-version, option, and creation binding, and verifies both collection
directory identities between stages. Existing stage-at-a-time operation remains
supported. The loop does not add
interactive prompts, pre-authorized mutation, reporting contracts, saved
invocation shortcuts, duplicate disposition, queueing, or parallel execution.

## Consequences

- Routine read-only work can proceed in one foreground invocation without
  weakening an existing checkpoint.
- A stopped loop leaves the same durable coordinator state that a manual
  one-stage invocation would leave.
- Later releases may add in-process checkpoint prompts or explicit
  preauthorization as separate policy layers; neither is implied here.
- Tests must prove both continued one-stage compatibility and stop behavior at
  every decision category.
