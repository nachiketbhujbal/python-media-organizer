# ADR 0068: Keep shared cache input policy inside the cache subsystem

- Status: Accepted
- Date: 2026-08-23

## Context

The video duplicate module originally owned writable cache-target validation
and complete-file descriptor hashing. Once image fingerprints became another
cache producer, importing those primitives from a video command would give
shared safety policy misleading ownership and create command-to-command
dependencies.

## Decision

Place writable local or explicit cache-target resolution in `pymo.cache.paths`.
An explicit target requires an existing, non-symbolic-link parent and does not
create that parent during resolution. Place complete SHA-256 hashing of an
already opened descriptor in `pymo.cache.hashes`, alongside observation reuse
and publication policy.

Image, video, and cache-warming consumers use these shared primitives. Media
equivalence remains separately owned by the image and video duplicate modules.

## Consequences

All cache producers now interpret external write targets and complete-byte
hashing consistently without depending on another command. Future cache
producers have one policy owner, while the move does not change cache paths,
schemas, CLI spellings, or media behavior.
