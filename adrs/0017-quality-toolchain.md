# ADR 0017: Gate commits with Ruff, Black, and mypy

- Status: Accepted
- Date: 2026-08-22

## Context

The pre-validation review found type-narrowing defects, inconsistent imports,
and no reproducible local quality gate. Overlapping tools would add noise.

## Decision

Use Ruff for linting and import modernization, Black for formatting, mypy for
static typing, and pre-commit for local enforcement plus basic file hygiene.
Keep all Python tool versions in the uv lock. Do not add overlapping Flake8,
Pyright, or pydocstyle gates without a new ADR.

## Consequences

Commits are blocked when source or tests fail the selected checks. The full
pytest suite remains a release gate rather than a slow per-file pre-commit hook.
