# ADR 0020: Support POSIX platforms in the current release line

- Status: Accepted
- Date: 2026-08-22

## Context

The append-only action journal uses `fcntl` advisory locks. Importing that module
is not portable to Windows, while media collections themselves may still carry
Windows metadata when moved between systems.

## Decision

The current package supports macOS and Linux. Continue ignoring common Windows
filesystem metadata for portable drives, but do not claim Windows runtime
support until same-file locking and the mutation suite are verified there.

## Consequences

Package metadata and documentation state the actual boundary. Cross-platform
locking requires a future ADR, implementation, and Windows integration tests.
