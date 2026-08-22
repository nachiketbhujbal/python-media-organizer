# ADR 0041: Run the release-quality gate in GitHub Actions

- Status: Accepted
- Date: 2026-08-22

## Context

Local pre-commit and release checks are reproducible but can still be skipped,
and tag-derived versions need complete Git history. Video integration tests
also require a known native FFmpeg runtime.

## Decision

Run least-privilege Ubuntu, Fedora, and macOS GitHub Actions jobs on every
branch push, pull request to `main`, push to `main`, and `v*` tag. Pin
third-party actions and the Fedora container by immutable digest, pin uv
0.12.5, install Python from `.python-version`, sync the lock, install system
FFmpeg, then run pre-commit, subprocess-aware pytest coverage, and both
distribution builds. Fetch complete Git history and verify that a tag run's
CLI version matches its tag.

Begin with Python 3.11 on representatives of the supported Debian-family Linux,
Red Hat-family Linux, and macOS operating-system families. Linux CI also
exercises the execution model used by WSL. Add Python-version breadth or other
Unix runners only when support claims, runner availability, or evidence justify
their cost.

## Consequences

All `quality` platform jobs become required merge and tag checks. CI downloads
locked development dependencies and the platform FFmpeg package, but it never
receives private collections or credentials and has read-only repository
permission. Action, tool, and container pins require deliberate maintenance.
macOS runner minutes cost more than Linux minutes, but testing each supported
platform family is necessary for the stated boundary.
