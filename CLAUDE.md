# Claude Code entry point

@AGENTS.md is the authoritative instruction file for this project. Follow it
exactly. This file deliberately contains no rules of its own and must never
restate them, so the two records cannot drift.

Before changing behavior, read `HANDOFF.md` completely, then the relevant
source, tests, `docs/ROADMAP.md`, `docs/RESEARCH.md`, `docs/CHANGELOG.md`,
`docs/CODE_REVIEW.md`, and `docs/adr/`.

The assistant-coordination conventions that used to live here — branch prefixes,
ADR-number claiming, default cross-review, and the subagent reading rule — are
now recorded in `AGENTS.md` and in
[ADR 0077](docs/adr/0077-multi-assistant-coordination.md). They are deliberately
not repeated here.
