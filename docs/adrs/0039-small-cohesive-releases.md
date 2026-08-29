# ADR 0039: Prefer small cohesive release tags

- Status: Accepted
- Date: 2026-08-22

## Context

Several independent safety, performance, reporting, and user-interface changes
were initially grouped into a few broad patch targets. That would make review,
regression diagnosis, and rollback needlessly coarse.

## Decision

Assign one primary purpose to each patch release. Split independently useful
changes into separate tags even when this produces double-digit patch numbers.
A patch may include tests, documentation, and tightly coupled fixes required to
make its primary change correct. Use a minor release for a coherent new
subsystem or an intentional compatibility boundary.

## Consequences

The release history is longer but easier to audit, bisect, install, and revert.
The roadmap names intended patch boundaries; the changelog remains the source
of truth for what each tag actually contains.
