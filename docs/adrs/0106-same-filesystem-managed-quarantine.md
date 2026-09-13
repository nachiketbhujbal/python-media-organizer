# ADR 0106: Manage retained quarantine on one filesystem

- Status: Proposed
- Date: 2026-09-13
- Applies: ADR 0083, ADR 0084, ADR 0087, ADR 0103, ADR 0105

## Context

The migration coordinator can retain a reviewed duplicate tree in the working
collection or acknowledge that an operator moved it elsewhere. The latter path
still requires manual shell choreography and records no pymo-authored movement
evidence. Version 0.6.9 owns only the safer case where the working review tree
and an explicitly selected retained destination share one filesystem, so an
atomic rename remains available.

Cross-filesystem movement requires a distinct copy, verification, capacity,
publication, and recovery protocol and begins version 0.7. Permanent deletion
remains outside both plans.

## Proposed decision

Add a dry-run-first managed disposition that plans one exact relocation of the
reviewed `dups` tree to an explicit same-filesystem retained destination. Apply
must require stable descriptor-pinned source evidence, complete destination
preflight, descriptor-relative atomic no-replace movement, append-only journal
records, post-apply verification, and an exact undo plan.

The migration coordinator may advance only from the reviewed successful
without-`dups` simulation through that verified journaled operation. Restart,
interactive, unattended, synopsis, and report contracts must distinguish the
managed move from retained-in-place and unverified human-managed external
quarantine. No mode may infer deletion or cleanup authority.

The final design must fail closed on aliases, nesting, occupied destinations,
changed source evidence, path substitution, different filesystems, interrupted
lifecycle state, or an inexact restoration path. It must never copy as a
fallback, overwrite, or delete media.

## Consequences

- A same-filesystem quarantine no longer requires manual shell movement.
- Pymo can report exactly what it moved and can undo the reversible operation.
- Cross-filesystem quarantine remains version 0.7.0; queueing, scheduling, and
  irreversible cleanup remain later or unpromoted work.
