# ADR 0038: Centralize durable engineering documentation

- Status: Accepted
- Date: 2026-08-22

## Context

Research, planned work, shipped behavior, architecture decisions, review
findings, and operational handoff details had accumulated at the repository
root and in one combined research/backlog file. That made current commitments
difficult to distinguish from exploratory ideas.

## Decision

Keep `README.md`, `AGENTS.md`, and `HANDOFF.md` at the repository root. Keep a
future license at the root for reliable host and package discovery. Store the
roadmap, research notebook, changelog, adversarial review, contribution guide,
and ADR ledger under `docs/`, with `docs/README.md` as the index.

`ROADMAP.md` contains promoted, scheduled work. `RESEARCH.md` contains product
audits, design evidence, licensing cautions, and uncommitted questions.
`CHANGELOG.md` contains shipped behavior. These documents may link to one
another but must not duplicate their full inventories.

## Consequences

The root stays focused while durable documentation has a discoverable home.
Moving the changelog under `docs/` is less conventional than keeping it at the
root, so the root README must link to it prominently. Package metadata and
build rules must use the new paths.
