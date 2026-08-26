# ADR 0064: Reuse exact-state whole-file hash observations

- Status: Accepted
- Date: 2026-08-22

## Context

Exact-video inspection repeatedly reads every complete file to calculate the
same SHA-256 before probing, even when a prior run already established that
byte identity. Checksum scans perform the same work for same-size media
candidates. The shared cache schema already has optional whole-file hashes on
file observations, but it did not define a safe producer or reuse policy.

A pathname and size are insufficient cache keys. Collections may be renamed,
an external cache may hold records for several collections, and an applied
duplicate move must never rely exclusively on disposable derived state.
Checksum scan must also retain its strict zero-write contract.

## Decision

Namespace each observation with the current collection root directory's
device and inode, without persisting its name or absolute path. Reuse a SHA-256
only when that scope, collection-relative path, device, inode, size,
modification time, and change time all match the current stable file snapshot.
Any mismatch is a cache miss, never evidence that two files differ.

Exact-video inspection reads and writes these observations unless
`--no-cache` is selected. It still opens every video through the existing
collection-anchored no-follow descriptor before probing. Newly computed hashes
are published in bounded, configurable atomic batches so interruption retains
completed batches without forcing one full cache replacement and directory
sync per video. The packaged batch size is 32 and may be overridden through
`performance.cache_publication_batch_size`.

Before an applied exact-video move, re-read every cached whole-file hash that
participated in the result through a stable descriptor and require it to match.
This content recheck happens before pymo creates a duplicate directory, action
history, or move. Ordinary file-state checks remain in force through journal
commit.

Checksum scan may reuse exact current observations from the collection cache or
an explicit `--cache PATH`. It opens the cache through the zero-write snapshot
reader, never creates a lock or cache, never publishes newly computed hashes,
and reports aggregate cache-hit and computed-hash counts. Its direct checksum
reads are descriptor-pinned rather than pathname-based.

All observation writers use the shared validated, locked, atomic publication
service. First-time lock creation uses an explicit exclusive create-or-open
sequence so concurrent initial writers serialize on macOS and Linux. Cache
status treats observations from another collection scope as stale rather than
testing their relative paths against the selected collection.

## Consequences

Repeated video runs avoid rereading unchanged files solely to reconstruct their
byte keys, and checksum scans can benefit from previously warmed observations
without becoming stateful. New or changed files require only their own hash;
moving the entire collection preserves its root identity, while copying it or
selecting another collection deliberately invalidates path observations.

The cache remains disposable acceleration, not preservation proof. A dry run
may use exact-state observations, but any mutation depending on them performs a
fresh content read. Scan-computed hashes are not persisted because changing
that command's zero-write contract would require a separate product decision.
