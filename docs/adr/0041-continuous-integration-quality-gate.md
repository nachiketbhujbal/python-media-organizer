# ADR 0041: Run the release-quality gate in GitHub Actions

- Status: Accepted
- Date: 2026-08-22

## Context

Local pre-commit and release checks are reproducible but can still be skipped,
and tag-derived versions need complete Git history. Video integration tests
also require a known native FFmpeg runtime.

## Decision

Run a least-privilege Ubuntu and macOS GitHub Actions matrix on every branch
push, pull request to `main`, push to `main`, and `v*` tag. Pin third-party
actions by full commit SHA, pin uv 0.12.5, install Python from
`.python-version`, sync the lock, install system FFmpeg, then run pre-commit,
subprocess-aware pytest coverage, and both distribution builds. Fetch complete
Git history and verify that a tag run's CLI version matches its tag.

Begin with Python 3.11 on both supported operating-system families. Linux CI
also exercises the execution model used by WSL. Add Python-version breadth or
other Unix runners only when support claims, runner availability, or evidence
justify their cost.

## Consequences

Both `quality` matrix jobs become required merge and tag checks. CI downloads
locked development dependencies and the platform FFmpeg package, but it never
receives private collections or credentials and has read-only repository
permission. Action and tool pins require deliberate maintenance. macOS runner
minutes cost more than Linux minutes, but testing both platform families is
necessary for the stated support boundary.
