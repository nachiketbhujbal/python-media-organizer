# ADR 0041: Run the release-quality gate in GitHub Actions

- Status: Accepted
- Date: 2026-08-22

## Context

Local pre-commit and release checks are reproducible but can still be skipped,
and tag-derived versions need complete Git history. Video integration tests
also require a known native FFmpeg runtime.

## Decision

Run one least-privilege Ubuntu GitHub Actions job on every branch push, pull
request to `main`, push to `main`, and `v*` tag. Pin third-party actions by full
commit SHA, pin uv 0.12.5, install Python from `.python-version`, sync the lock,
install system FFmpeg, then run pre-commit, subprocess-aware pytest coverage,
and both distribution builds. Fetch complete Git history and verify that a tag
run's CLI version matches its tag.

Begin with one Python 3.11 job. Add platform or Python-version matrices only
when support claims or evidence justify their cost.

## Consequences

The `quality` job becomes the required merge and tag check. CI downloads locked
development dependencies and the Ubuntu FFmpeg package, but it never receives
private collections or credentials and has read-only repository permission.
Action and tool pins require deliberate maintenance.
