# ADR 0042: Integrate changes through short-lived branches

- Status: Accepted
- Date: 2026-08-22

## Context

Direct commits to `main` provide no pre-merge remote gate. The project has one
maintainer today, so a policy that requires approval from another person would
also deadlock routine releases.

## Decision

Develop each cohesive change on a short-lived branch, push it, and require the
CI `quality` result before merging into `main`. Preserve a merge boundary and
tag the verified merge commit. Configure GitHub branch protection to require a
pull request, successful `quality` status, and resolved conversations, while
not requiring a second person's approval until another maintainer exists.

Repository rules are an external administrative setting. They are enabled
deliberately after the check exists; the deploy key alone does not provide
GitHub API or pull-request authentication.

## Consequences

Every release has an inspectable branch, CI result, merge, and tag. A one-time
bootstrap merge is necessary to place the workflow on `main` before the status
check can be made required. Future automation needs authenticated GitHub CLI,
an appropriately scoped token, or an interactive web session separate from the
repository deploy key.
