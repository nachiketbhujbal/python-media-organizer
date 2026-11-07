# ADR 0110: Copy retained quarantine across filesystems

- Status: Proposed
- Date: 2026-11-06
- Applies: ADR 0106, ADR 0109

## Contract

Version 0.7.0 adds explicit `quarantine-dups --copy` and a saved coordinator
copy mode. The existing same-filesystem atomic rename remains the default and
never falls back to copying. The copy mode preserves `COLLECTION/dups`, all
its original files, and every interrupted staging artifact. It never deletes,
truncates, overwrites, or claims reclaimed space. The copied result is an
additional retained copy, not proof that the working review tree is absent.

Preview is zero-write. Apply freshly binds the collection and source-tree
identities, complete source namespace and file states, every relative path and
byte hash, the explicit target spelling, and its parent's identity. Reject
aliases, nested destinations, unsafe ancestry, symlinks, multiply linked files,
special files, changing or unreadable entries, and an occupied destination.
Use descriptor-relative no-follow reads and exclusive writes throughout.

A separate portable tree digest covers relative names, directory structure,
file sizes, and SHA-256 content without assuming copied inodes are equal.
The source state digest separately binds exact filesystem observations. Copy
preserves file byte streams, including embedded metadata; it does not claim
portable ownership, ACL, extended-attribute, resource-fork, or whole-device
preservation. Unsupported filesystem metadata must be surfaced explicitly by
the implementation rather than silently described as preserved.

## Publication and interruption

Capacity preflight accounts for the full staged copy and a declared reserve;
free-space inspection is a preflight, not a storage reservation. Repeat it
before writes and treat disk-full errors as interrupted work. Never infer
available capacity from source duplicate estimates or apparent clone savings.

Append a dedicated strict copy operation to the collection action journal
before staging. Bind an exclusive staging name and destination parent; record
staging identity before copying any media. Scratch has its own separately journal-bound sibling directory outside the
publishable stage. Partial file writes use exclusive UUID scratch names. Each exclusive empty
file is synced and its token and device/inode are durably recorded before any
media bytes are written. Artifact completion records allocation, not copied
content; full tree verification establishes the latter. Unknown names and
replacement leaf identities are refused. A crash before the leaf identity
record leaves an unadoptable orphan requiring operator review. A complete file
is synced, freshly verified, and published
inside the staged tree with an atomic no-replace rename. Failed scratch files
remain retained and cannot satisfy the copied manifest.

Verify the full staged tree against fresh source evidence, revalidate both
namespaces, sync the staged files and directories, and atomically publish the
complete tree under the exact destination leaf without replacement. Reopen and
verify the published target, revalidate the source again, then append completion
and commit. Source bytes and their location remain unchanged throughout.

Recovery requires the same explicit source, destination, and copy selector.
Strictly validate the journal and bound directory identities before reading
or writing staging. Distinguish: no stage yet; incomplete stage; complete stage
not published; published target awaiting journal commit; and completed copy.
The published target must be the exact directory inode recorded for staging;
its pathname and content digest alone cannot authorize an impostor. Sync each
new staging directory and its parent before recording its identity, and sync
that journal record before writing media. Recognize only the exact recorded
stage or target, never adopt unrelated data.
Rehash completed staged files before reuse. Retain interrupted scratch files;
never truncate one to resume. An occupied conflicting target, substituted
parent, altered source, malformed history, or unexplained namespace stops.
A crash before staging identity is durably recorded may leave an orphan that
requires explicit operator review; do not adopt it merely from its name.

## Workflow and undo

The coordinator preserves distinct preview and apply checkpoints. Every copy
apply retries through strict recovery-or-fresh inspection, including a child
commit that precedes a lost coordinator result. This never adopts an occupied
target without its matching committed copy journal. Its saved
mode and exact copied plan become part of private state and policy bindings.
Successful copying advances only to an explicitly named source-retained
disposition. Final fresh validation and ordinary verification include the
source review tree until a separately reviewed human operation removes it.
Reports distinguish copied bytes, source-retained bytes, and zero reclaimed
space; copying never silently becomes external-quarantine confirmation.

There is no destructive undo for a retained copy. Reject ordinary `--undo`
for copy mode rather than deleting its destination or pretending the copy was
removed. Source changes, target retirement, restoration after human cleanup,
and any new destructive action require separate reviewed contracts. Existing
same-filesystem undo is unchanged. A committed copy continues to protect the
source review namespace: overlapping forward actions and dependency-aware undo
are refused. There is no automatic release of that dependency in this version.
Before later coordinator execution or sign-off, rehash both the retained copy
and source and require their exact recorded identities. Structured reports
remain projections of historical outcomes and do not perform media reads.
Copied-retention journal entries must not
silently turn into generic rename/undo operations.

Private restart state advances to schema 6; private outcomes, unattended policy,
and public migration reports advance to schema 4. Copy selection and the
explicit reserve are saved options, distinct from move authority. The required
`--copy-reserve-bytes` has no guessed default. Public reports disclose only
aggregate extended-attribute observations and unknowns, and never claim ACL,
resource-fork, or other filesystem metadata preservation. No metadata is
silently counted as preserved merely because an API could not inspect it.

## Acceptance

Prove zero-write preview; exact copied bytes and source immutability; strict
journal parsing and mode binding; occupied-target and path-swap refusal;
capacity failure before writes; interruption at every publication boundary;
verified completed-file reuse; no deletion or truncation during recovery;
copy-specific reporting; exact policy binding; and unchanged rename/undo.
Use synthetic distinct-filesystem fixtures for actual cross-device proof and
controlled failures for boundary attacks. Repeated real-collection pilots are
not required. This proposed ADR is a design reservation, not shipped behavior.
