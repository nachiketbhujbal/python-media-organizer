# ADR 0087: Make operator experience the version 0.6 theme

- Status: Accepted
- Date: 2026-09-11
- Extends: ADR 0084

## Context

Version 0.5.13 began controlled use of the released migration workflow on
existing real collections. Multiple end-to-end trials reached complete preservation
verdicts and reproduced the previously accepted content outcomes without
silent deletion or overwrite. The transformation and evidence layers behaved
as designed across healthy media, validation findings, extension correction,
organization, deterministic renaming, exact duplicate isolation, cache reuse,
and final verification.

The trials also exposed an operator problem that synthetic acceptance coverage
did not make sufficiently visible. A complete migration requires roughly two
dozen nearly identical coordinator invocations, special mutually exclusive
modes for status acknowledgement and quarantine confirmation, repeated root and
log-directory arguments, and a manual duplicate-review-tree move. Expensive
exact-video analysis can leave the operator supervising the workflow for hours,
yet the coordinator emits no concise end-of-run account of what changed, what
storage is reclaimable, what evidence was reused, or why the final result is
safe.

The real collection identities, paths, statistics, and detailed timings are
private operational evidence and remain outside this public repository. The
generic conclusions are sufficient to set product priorities.

## Decision

Version 0.6 will prioritize an operator-first migration experience over adding
new media transformations. The existing restartable stage engine, fresh
preservation evidence, preview-before-apply boundaries, exact child statuses,
no-overwrite behavior, and explicit human decisions remain the safety
foundation.

The promoted sequence uses one primary acceptance purpose per release:

1. versions 0.6.0 and 0.6.1 add safe automatic stage advancement and then
   in-process interactive checkpoints;
2. versions 0.6.2 through 0.6.5 add the human synopsis, saved invocation
   context, a stable machine-readable report, and deliberately pre-authorized
   unattended execution as separate contracts;
3. versions 0.6.6 and 0.6.7 separate logging surfaces and levels before deciding
   coherent visibility and privacy profiles;
4. versions 0.6.8 through 0.6.10 add retained-in-place duplicate disposition,
   same-filesystem managed quarantine, and explicit cross-filesystem quarantine
   separately;
5. versions 0.6.11 through 0.6.14 add manifest validation, sequential execution,
   per-collection recovery, and queue reporting separately; and
6. versions 0.6.15 through 0.6.17 measure storage topology before enabling
   bounded intra-collection and then cross-collection scheduling.

The first driver release may advance routine successful stages automatically,
but it must stop at every existing decision boundary. Interactive checkpoint
handling is a following release rather than hidden inside the loop foundation.
A still-later deliberately pre-authorized non-interactive mode may cross
reviewed mutation boundaries only under a separately specified contract; it
may never convert a warning, failed proof, or ambiguous state into implicit
consent.

Rich local visibility is a valid usability goal, but console detail, durable
path-bearing logs, restart bookkeeping, and machine-readable summaries are
different surfaces. Any change from the current path-private and opt-in
persistence defaults requires its own explicit compatibility and privacy
decision.

Duplicate detection remains non-deleting. The existing without-`dups`
simulation may support an honest retained-in-place disposition without
claiming that storage was reclaimed. Same-filesystem quarantine,
cross-filesystem quarantine, and any future permanent cleanup require distinct
evidence, capacity, interruption, journal, and confirmation semantics. A
convenience flag must not make irreversible deletion an accidental consequence
of migration. Permanent deletion remains outside the version 0.6 plan.

This ADR and its documentation release change no runtime, package,
configuration, command, report, cache, journal, migration, or media behavior.

## Consequences

- The next major value is reducing supervision and ambiguity around already
  reliable work, not broadening the set of automatic transformations.
- A human-readable outcome synopsis becomes a primary product result rather
  than an agent-authored after-action note; its stable machine-readable schema
  follows as a separate compatibility boundary.
- Queue input must describe complete collection roles and policy; a
  newline-only list may be a convenience frontend but is not an adequate safety
  contract by itself.
- Image and video work, later-collection cache warming, and cross-collection
  execution are candidates for dependency-aware scheduling, not assumed-safe
  parallel work.
- One primary owner retains version 0.6 integration, release publication, and
  real-collection acceptance. Supporting sessions on other devices may own
  non-overlapping contribution branches and perform substantial bounded
  implementation, analysis, tests, and benchmarks through Agent Relay. The
  primary owner vets and integrates their exact contributions; an author does
  not independently review its own work. Contribution-branch ownership does
  not silently transfer release ownership. Agent Relay coordinates ownership
  and evidence; it is not the product scheduler.
