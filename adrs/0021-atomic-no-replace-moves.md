# ADR 0021: Require atomic no-replace file moves

- Status: Accepted
- Date: 2026-08-22

## Context

A destination can appear after preflight but before an ordinary rename, and a
path component can be exchanged for a symbolic link. Cross-filesystem copy and
unlink cannot provide the same atomic safety or crash behavior.

## Decision

Open source and destination parents through no-follow directory descriptors and
use macOS `renameatx_np` or Linux `renameat2` with the platform's no-replace
flag. Refuse cross-filesystem file moves rather than silently copying.

## Consequences

Concurrent destination creation never causes overwrite, and ancestor swaps do
not redirect Linux operations. A collection spanning mount points must first be
consolidated onto one filesystem; pymo reports the refusal without moving data.
