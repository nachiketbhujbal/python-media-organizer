# ADR 0073: Establish migration coverage from fresh directional byte evidence

- Status: Accepted
- Date: 2026-08-23

## Context

A migrated collection may have a different root name, directory layout, and
filenames. File counts and total storage therefore cannot establish
preservation. Duplicate review also deliberately reduces copies, so a mirror
comparison would incorrectly call safe multiplicity reduction data loss.

The source may contain unreadable namespace entries or change during a run.
Silently omitting those entries would produce a dangerous success claim. A
cached historical hash can accelerate comparison but cannot prove that the
current file remains readable, so the first preservation contract needs fresh
content reads.

## Decision

Add directional `pymo verify-migration SOURCE DESTINATION` and define version
0.5.0's contract as exact coverage of unique, in-scope source byte streams.
Identify content by complete SHA-256 plus byte length, independent of paths and
names. Hash both trees freshly through collection-anchored, no-follow stable
descriptors after a complete best-effort namespace inventory.

Report duplicate multiplicity separately. One readable destination file can
represent several byte-identical source copies without losing a unique stream.
Destination-only content does not invalidate source coverage.

Use three verdicts. `complete` means every in-scope readable source identity
has a readable destination representative. `incomplete` means source evidence
is complete and identities are definitely absent from a complete destination
inventory. `unproven` means source evidence is incomplete, or missing content
could be hidden by incomplete destination evidence. Ignored entry points are
reported and remain explicitly outside the v0.5.0 scope; version 0.5.3 will
apply the stricter final-sign-off boundary.

Exclude pymo configuration, cache, lock, staging, and canonical action-history
files from the media-byte contract. Never write derived or authoritative state
to either tree. Reject identical and nested roots so the two inventories cannot
consume one another.

## Consequences

Version 0.5.0 can prove exact byte preservation across safe renaming,
organization, and byte-identical duplicate reduction. It does not yet treat a
metadata-varied image or remuxed video as represented; those content-equivalent
layers belong to versions 0.5.1 and 0.5.2.

Fresh hashing can be expensive, particularly on spinning storage, but it is
the honest default for preservation evidence. The command remains sequential
and path-private while representative performance data is gathered. Cache
acceleration may be added only as an explicit, strictly validated evidence mode
without weakening fresh final sign-off.
