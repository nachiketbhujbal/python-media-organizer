# ADR 0044: Conserve private-repository GitHub Actions usage

- Status: Accepted
- Date: 2026-08-22

## Context

GitHub Free includes 2,000 hosted-runner minutes per month for private
repositories. The complete Ubuntu, Fedora, and macOS matrix is valuable, but
running it for every branch push, pull request, mainline merge, and tag repeats
the same evidence and makes frequent small releases unnecessarily expensive.
macOS hosted-runner time also has a materially higher paid rate than Linux.

Local pre-commit, subprocess-aware coverage, real FFmpeg tests, and package
builds remain mandatory before a pull request. The project still needs remote
pre-merge evidence and independent verification of the resulting mainline
commit.

## Decision

Run the complete platform matrix automatically for pull requests targeting
`main` and pushes to `main`. Do not run it automatically for ordinary branch
pushes or version tags while the repository is private. Retain manual workflow
dispatch for deliberate pre-PR or tag investigation. Limit every platform job
to ten minutes and preserve cancellation of superseded runs on the same ref.

Verify hatch-vcs tag identity locally after tagging by reinstalling the package,
checking the exact CLI version, and rebuilding both distributions. The already
verified mainline commit and a tag differ only by Git reference metadata.

## Consequences

Each normal release uses two complete matrices instead of up to four or more:
one before merge and one after merge. A pushed branch has no remote result until
its pull request is opened unless a maintainer deliberately dispatches the
workflow. Tags no longer verify themselves remotely by default. When the
repository becomes public, a later ADR may liberalize triggers because standard
GitHub-hosted runners for public repositories are free, subject to GitHub's
operational and acceptable-use limits.

This decision supersedes only the trigger, timeout, and automatic tag-check
portions of ADR 0041. Its platform matrix, least-privilege permissions, pinned
tools, complete history, and quality commands remain in force.
