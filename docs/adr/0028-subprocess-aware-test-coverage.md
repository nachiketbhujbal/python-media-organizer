# ADR 0028: Measure subprocess-aware test coverage

- Status: Accepted
- Date: 2026-08-22

## Context

Most user-facing tests invoke the real `pymo` CLI in child Python processes.
Ordinary parent-only coverage therefore reported 42 percent and hid exercised
command paths, making the number misleading rather than actionable.

## Decision

Configure Coverage.py's subprocess patch with parallel data collection in
`pyproject.toml`. Keep direct unit tests for adversarial state changes and error
branches, and run `pytest --cov=pymo` as a release review gate rather than on
every local commit.

## Consequences

The same 127-test suite now measures child CLI execution and reports 86 percent
total coverage at this release. Coverage identifies untested branches without
replacing behavior assertions, real FFmpeg integration, or risk-based review.
