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
staging identity before copying any media. Partial file writes use exclusive
scratch names. A complete file is synced, freshly verified, and published
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
Recognize only the exact recorded stage or target, never adopt unrelated data.
Rehash completed staged files before reuse. Retain interrupted scratch files;
never truncate one to resume. An occupied conflicting target, substituted
parent, altered source, malformed history, or unexplained namespace stops.
A crash before staging identity is durably recorded may leave an orphan that
requires explicit operator review; do not adopt it merely from its name.

## Workflow and undo

The coordinator preserves distinct preview and apply checkpoints. Its saved
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
same-filesystem undo is unchanged. Copied-retention journal entries must not
silently turn into generic rename/undo operations.

## Acceptance

Prove zero-write preview; exact copied bytes and source immutability; strict
journal parsing and mode binding; occupied-target and path-swap refusal;
capacity failure before writes; interruption at every publication boundary;
verified completed-file reuse; no deletion or truncation during recovery;
copy-specific reporting; exact policy binding; and unchanged rename/undo.
Use synthetic distinct-filesystem fixtures for actual cross-device proof and
controlled failures for boundary attacks. Repeated real-collection pilots are
not required. This proposed ADR is a design reservation, not shipped behavior.
