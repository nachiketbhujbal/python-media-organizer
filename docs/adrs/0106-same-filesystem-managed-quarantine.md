# ADR 0106: Manage retained quarantine on one filesystem

- Status: Accepted
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

## Decision

Add `pymo quarantine-dups COLLECTION DESTINATION` as the narrow movement and
undo primitive, and expose that same primitive at the coordinator's existing
duplicate-disposition checkpoint. The standalone and coordinated forms preview
by default. Every `--apply` invocation freshly derives and revalidates one exact
plan before moving. The coordinator additionally binds apply to its recorded
preview digest; the standalone command follows the established explicit-apply
contract without persisting preview authority. `--undo --apply` targets only
the exact active managed-quarantine run and explicit restoration path.

The coordinator saves an optional explicit quarantine destination with its
other invocation context. `--quarantine-dups` previews or applies that saved
destination at the existing checkpoint. Resume may recover it, interactive
operation may ask separately for preview and apply, and unattended operation
must bind both the destination and exact plan expectation into its private
policy. Retained-in-place and operator-confirmed external retention remain
separate choices.

Plan the directory as a complete, deterministic manifest of stable regular
files and safe directories opened without following links. Bind the source
directory identity, the destination parent identity and leaf name, the common
device, aggregate counts and bytes, and manifest digest into one decision
digest. Reject links, special or unreadable entries, unstable observations,
aliases, nesting, a missing or unsafe destination parent, an occupied target,
and different filesystems before journal or media writes.

Coordinator apply must rederive the exact plan and require its reviewed digest;
standalone apply must derive the plan and revalidate it within that invocation.
Each then appends a dedicated managed-quarantine lifecycle to the collection action history. The
physical transition is one descriptor-relative atomic no-replace directory
rename. It never decomposes the tree into separately movable file actions and
never falls back to copying. After rename, re-open and fully rehash the retained
tree before committing the run. A mismatch leaves an interrupted, fail-closed
journal lifecycle rather than a success claim.

Managed-quarantine journal records use a dedicated `QUARANTINE_TREE` operation
inside the existing strict schema-1 lifecycle. Existing operation meanings do
not change. The parser requires this operation to belong only to the managed
quarantine tool and validates its exact `dups` source, path-private destination
binding, parent identity, and tree identity. The operator must supply the same
destination spelling for status or undo. Journal recovery binds the recorded
parent identity and recognizes only source-present/target-absent or
source-absent/target-exact states; every other combination is a conflict.

Undo preflights the entire retained tree again, refuses an occupied
`COLLECTION/dups`, and performs the inverse atomic no-replace rename. It then
rehashes the restored tree before committing an append-only undo lifecycle.
Undo is a new reviewed plan bound to the destination's current parent identity;
the journal's destination digest and the retained tree's exact manifest plus
inode must still match. This permits an explicitly reviewed restoration after a
legitimate remount while plan-to-apply parent substitution remains refused.
Later active collection actions touching `dups` block the undo, while an active
managed quarantine blocks undo of the duplicate-isolation runs that produced
that tree.

The migration coordinator may advance only from the reviewed successful
without-`dups` simulation through the verified journaled apply. Restart state
records preview and apply outcomes as bookkeeping, not movement evidence.
Synopsis and report contracts distinguish managed same-filesystem retention
from retained-in-place and unverified human-managed external quarantine. They
may report bytes removed from the working collection but must report that pymo
reclaimed no physical storage on the shared filesystem. No mode may infer
deletion or cleanup authority.

The final design must fail closed on aliases, nesting, occupied destinations,
changed source evidence, path substitution, different filesystems, interrupted
lifecycle state, or an inexact restoration path. It must never copy as a
fallback, overwrite, or delete media.

## Consequences

- A same-filesystem quarantine no longer requires manual shell movement.
- Pymo can report exactly what it moved and can undo the reversible operation.
- A collection journal containing the new managed-tree operation remains valid
  schema-1 history for v0.6.9 and later; older strict readers safely reject the
  unknown future operation rather than misinterpreting it.
- Cross-filesystem quarantine remains version 0.7.0; queueing, scheduling, and
  irreversible cleanup remain later or unpromoted work.
