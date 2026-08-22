# ADR 0007: Build with Hatchling and derive versions from Git

- Status: Accepted
- Date: 2026-08-21

## Context

Static versions can disagree across source, metadata, wheels, and tags.

## Decision

Use Hatchling with hatch-vcs. Annotated `vX.Y.Z` Git tags are authoritative;
source does not contain another editable version string.

## Consequences

Release discipline includes tagging before final artifact verification.
Untagged builds receive a PEP 440 development version.
