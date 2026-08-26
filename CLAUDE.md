# Claude Code entry point

@AGENTS.md is the authoritative instruction file for this project. Follow it
exactly. This file is navigational only: it points at the authoritative records
and states the reading order, and it deliberately introduces no project
requirement of its own, so the two records cannot disagree. See
[ADR 0077](docs/adrs/0077-multi-assistant-coordination.md).

Before changing behavior, read `HANDOFF.md` completely, then the relevant
source, tests, `docs/ROADMAP.md`, `docs/RESEARCH.md`, `docs/CHANGELOG.md`,
`docs/CODE_REVIEW.md`, and `docs/adrs/`.

The assistant-coordination conventions — branch prefixes, ADR-number reservation,
release ownership, cross-review, disagreement arbitration, and the subagent
reading rule — are recorded in `AGENTS.md` and in ADR 0077. They are
deliberately not repeated here.
