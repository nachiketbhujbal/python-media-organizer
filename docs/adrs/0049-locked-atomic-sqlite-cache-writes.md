# ADR 0049: Lock and atomically publish SQLite cache writes

- Status: Accepted
- Date: 2026-08-22

## Context

The video fingerprint cache was updated by checking its public pathname and
then asking SQLite to open that pathname for an in-place transaction. A
concurrent substitution could redirect writes outside the collection. Two pymo
processes could also race, and an interrupted transaction acted directly on the
only public cache even though the data is derived and rebuildable.

Incremental persistence remains valuable because exact video decoding is
expensive. Each completed fingerprint should survive interruption, but cache
durability must not weaken the package's no-follow, fail-closed boundaries.

## Decision

Use collection-root `.pymo.sqlite3.lock` as a persistent private regular-file
coordination point. Readers take a shared `fcntl` lock and writers take an
exclusive lock. Both the collection directory and lock entry remain open and
identity-checked while cache work occurs. `--no-cache` bypasses the lock as
well as all cache reads and writes.

Under the exclusive lock, reopen and fully validate the latest public cache
through its collection-anchored descriptor. Copy it into an in-memory SQLite
database, merge the completed fingerprints, and validate its exact schema,
integrity check, and every row. Serialize that database to a random
`.pymo.sqlite3.new.*` file created with descriptor-relative `O_EXCL` and mode
`0600`, sync it, reopen it read-only through the descriptor, and validate it
again.

If no public cache exists, publish the staging file with the platform's atomic
no-replace rename. If one exists, atomically exchange the two entries and
verify that the displaced inode is the exact cache validated under the lock.
Rollback a mismatched exchange. Sync the collection directory after the
publication boundary. Never give SQLite a writable public cache pathname.

Do not automatically remove an unpublished staging database after a failure or
interruption. It is ignored by every forward command and remains available for
inspection. After a verified successful exchange, removing the displaced prior
cache is replacement of pymo-owned derived state, never deletion of media or
action history.

## Consequences

Cooperating processes serialize writes and merge the newest records rather than
losing updates. A crash before publication leaves the prior cache byte-for-byte
intact; atomic publication leaves either the complete old database or complete
new database at the public path. A public-path or lock substitution is rejected
without writing through it, and successful updates create no SQLite journal,
WAL, shared-memory, or staging sidecars.

The current fingerprint-only cache is copied in memory for each incremental
write. Its rows are small relative to video decoding work, so the stronger
boundary is appropriate now. The version 0.4 shared cache service must measure
this cost and may adopt a different descriptor-safe construction strategy if
the schema grows materially.
