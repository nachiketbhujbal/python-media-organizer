# ADR 0048: Descriptor-pin SQLite cache reads

- Status: Accepted
- Date: 2026-08-22

## Context

The video fingerprint cache was checked for a regular-file pathname and then
opened read-only through its resolved path. A concurrent process could replace
that pathname with a symbolic link after the checks but before SQLite opened
it, redirecting a transient read to an unrelated local database outside the
media collection.

The cache is disposable, but that does not make unrelated local-file access
acceptable. Existing invalid-cache behavior must continue to fail closed before
expensive decoding and must preserve the unexpected file for inspection.

## Decision

Capture the existing cache's regular-file state and open it with the shared
collection-relative, component-by-component no-follow primitive. Give SQLite a
read-only URI for the pinned `/dev/fd` descriptor and close the connection
before revalidating both the descriptor and public pathname.

A missing cache remains an ordinary empty-cache state. A symbolic link,
non-regular file, path outside the collection, or pathname change during the
read is an explicit cache safety error. Never retry through the changed path.

## Consequences

A path substitution cannot redirect SQLite to unrelated local content. Even if
the pinned original database was read successfully, a changed public pathname
stops the command so later cache writes cannot proceed on a stale assumption.

The implementation uses the existing supported POSIX descriptor model on
macOS and Linux. Cache-write serialization and atomic replacement remain a
separate release because they require a dedicated lock and publication
protocol rather than this read-only boundary.
