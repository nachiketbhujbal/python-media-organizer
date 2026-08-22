# ADR 0043: Classify descriptor bytes through standard input

- Status: Accepted
- Date: 2026-08-22

## Context

Descriptor-pinned classification originally passed `/dev/fd/N` to the system
`file` utility. BSD `file` on macOS followed that path to the regular content,
but GNU `file` on Ubuntu classified the descriptor link/device itself. Linux CI
therefore treated valid images and videos as non-media.

## Decision

When a stable descriptor is available, rewind it and make it the `file`
subprocess's standard input, using `-` as the content source. Continue using the
ordinary pathname form only when no pinned descriptor was supplied.

## Consequences

Classification reads the same pinned bytes on supported macOS and Linux
systems without depending on `/dev/fd` filename semantics. The subprocess
inherits the descriptor only as standard input, and existing MIME policy and
filename fallback behavior remain unchanged.
