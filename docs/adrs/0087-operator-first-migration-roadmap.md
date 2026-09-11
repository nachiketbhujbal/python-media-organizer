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

The promoted sequence is:

1. add a single-invocation operator driver and a useful final migration report;
2. unify console visibility, persistent diagnostics, restart state, and report
   output under explicit privacy profiles;
3. replace manual duplicate-review-tree shell choreography with a pymo-owned,
   dry-run-first disposition workflow;
4. add a manifest-backed multi-collection queue that is sequential by default;
   and
5. add bounded parallel scheduling only after storage-aware benchmarks prove a
   material wall-time benefit.

The driver may advance routine successful stages automatically, but it must
stop for unexpected findings, mutation authorization, irreversible decisions,
and unsafe or changed state. A later deliberately pre-authorized non-interactive
mode may cross reviewed mutation boundaries only under a separately specified
contract; it may never convert a warning, failed proof, or ambiguous state into
implicit consent.

Rich local visibility is a valid usability goal, but console detail, durable
path-bearing logs, restart bookkeeping, and machine-readable summaries are
different surfaces. Any change from the current path-private and opt-in
persistence defaults requires its own explicit compatibility and privacy
decision.

Duplicate detection remains non-deleting. External quarantine and any future
permanent cleanup require distinct evidence, capacity, interruption, journal,
and confirmation semantics. A convenience flag must not make irreversible
deletion an accidental consequence of migration.

This ADR and its documentation release change no runtime, package,
configuration, command, report, cache, journal, migration, or media behavior.

## Consequences

- The next major value is reducing supervision and ambiguity around already
  reliable work, not broadening the set of automatic transformations.
- A human-readable and machine-readable outcome synopsis becomes a primary
  product result rather than an agent-authored after-action note.
- Queue input must describe complete collection roles and policy; a
  newline-only list may be a convenience frontend but is not an adequate safety
  contract by itself.
- Image and video work, later-collection cache warming, and cross-collection
  execution are candidates for dependency-aware scheduling, not assumed-safe
  parallel work.
- Version 0.6 work can be split across devices only as separately owned product
  branches with explicit interfaces and exact-SHA review. Agent Relay
  coordinates ownership and evidence; it is not the product scheduler.
