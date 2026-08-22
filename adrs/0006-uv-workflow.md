# ADR 0006: Use uv for environments and locking

- Status: Accepted
- Date: 2026-08-21

## Context

Development needs a reproducible virtual environment without requirements-file
duplication.

## Decision

Use uv for environment creation, dependency resolution, the committed lockfile,
tool execution, builds, and local tool installation. Dependencies remain in
`pyproject.toml`.

## Consequences

Contributors need the documented uv version. Standards-compatible pip installs
remain supported because uv is not the build backend.
