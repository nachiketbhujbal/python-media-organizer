# ADR 0016: Remove compatibility only at semantic boundaries

- Status: Accepted
- Date: 2026-08-22

## Context

Legacy CSV manifests, grouped duplicate output, and fixed action-log names no
longer fit the shared architecture, but patch releases must not silently remove
interfaces.

## Decision

Warn during the prior minor line and remove incompatible behavior only at a new
minor version. Document migration and retain persisted schema identifiers unless
another explicit compatibility decision supersedes them.

## Consequences

Version 0.2 removed interfaces deprecated in 0.1.5. Future removals follow the
same staged process.
