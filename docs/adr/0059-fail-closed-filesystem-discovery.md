# ADR 0059: Fail closed on incomplete filesystem discovery

- Status: Accepted
- Date: 2026-08-22

## Context

Python's recursive directory traversal may report an unreadable directory to
an optional callback and otherwise continue with a partial result. A mutation
plan, undo simulation, or completed-layout verdict built from that result can
incorrectly treat undiscovered content as absent. Immediate directory listing
for an exact duplicate finder fails noisily, but without the same controlled,
path-private no-state boundary.

Report-only scan and validation commands have a different purpose: they keep
processing readable neighbors and preserve traversal problems as visible
health findings. Mutation planning and verification instead require a complete
view of every namespace location within their declared ownership boundary.

## Decision

Use shared fail-closed discovery primitives for recursive and flat namespace
enumeration. Recursive discovery accumulates traversal errors so callers never
receive an apparently successful final plan after an omitted subtree. Flat
discovery converts listing failures to the same controlled error type.

Organization and renaming stop before creating destinations, action history,
or file moves when discovery is incomplete. Undo snapshot construction stops
before simulation or mutation. Each duplicate finder requires complete listing
of only its owned `pics` or `vids` directory and creates no duplicate tree,
cache, or action history after a discovery failure. Organizer verification
reports failure if a post-operation namespace cannot be read completely.

Configured ignore rules remain intentional traversal pruning and do not count
as discovery errors. Symlink and stable-file rules remain unchanged. Generic
errors do not disclose collection paths unless a command's existing explicit
reporting contract permits them.

## Consequences

Commands no longer infer absence from an incomplete directory walk. A
transient permission or I/O failure may require a clean rerun, which is safer
than applying or approving a partial plan. Report-only health commands continue
to collect all usable evidence and surface unreadable locations rather than
aborting at the first affected file.
