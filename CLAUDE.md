# Claude Code entry point

@AGENTS.md is the authoritative instruction file for this project. Follow it
exactly. This file deliberately contains no rules of its own and must never
restate them, so the two records cannot drift.

Before changing behavior, read `HANDOFF.md` completely, then the relevant
source, tests, `docs/ROADMAP.md`, `docs/RESEARCH.md`, `docs/CHANGELOG.md`,
`docs/CODE_REVIEW.md`, and `docs/adr/`.

## Assistant coordination

- Branch as `claude/<type>/<slug>`, adding the target version as
  `claude/<type>/v<x.y.z>-<slug>` when the work is scheduled for a release.
  Codex uses `codex/` with the same shape. The merge commit preserves the
  branch name, so authorship stays visible in history without changing the
  one-line commit convention.
- Claim the next free `docs/adr/` number in the branch's first commit and name
  it in the pull request, so parallel branches cannot collide.
- Each assistant adversarially reviews the other's pull request before merge by
  default, recording findings in `docs/CODE_REVIEW.md` under the existing ID
  scheme. The maintainer may waive a review; a waived review becomes a recorded
  follow-up rather than a silent gap.
- Every subagent prompt must instruct the subagent to read `AGENTS.md` and
  `HANDOFF.md` fully before acting. Imported context is not inherited.
