# ADR 0077: Coordinate multiple AI assistants through one authoritative file

- Status: Accepted
- Date: 2026-08-24

## Context

More than one AI coding assistant now contributes to this repository, and each
host tool discovers its instructions from a different filename. Restating the
project rules in every tool-specific file would let the copies drift, and a
contributor following a stale copy would break a rule another file still
states correctly.

Parallel assistant branches also introduce two practical collisions. Two
branches can claim the same `docs/adr/` number before either merges, and
attribution disappears once every commit is authored under the single
maintainer identity required by the Git policy.

A shared `.ai` directory with per-tool symlinks was considered and rejected for
now. Symlink behavior, host-tool discovery conventions, POSIX portability, and
conflicting generated settings are unresolved, and none of them need to be
resolved to make the assistants agree on one instruction source today.

## Decision

`AGENTS.md` is the single authoritative instruction file. A tool-specific entry
point may exist only to point at it, must contain no rules of its own, and must
not restate any rule, so the two records cannot disagree.

Name each assistant's branch with its own prefix, `claude/<type>/<slug>` or
`codex/<type>/<slug>`, adding the target version as `<type>/v<x.y.z>-<slug>`
when the work is scheduled for a release. The merge commit preserves the branch
name, so authorship stays visible in history without changing the one-line
commit convention or the maintainer authorship those commits carry.

Claim the next free `docs/adr/` number in a branch's first commit and name it in
the pull request, so parallel branches cannot collide on one number.

Each assistant adversarially reviews the other's pull request before merge by
default, recording findings in `docs/CODE_REVIEW.md` under the existing
identifier scheme. The maintainer may waive a review; a waived review is
recorded as follow-up debt rather than skipped silently.

Every subagent prompt must instruct the subagent to read `AGENTS.md` and
`HANDOFF.md` completely before acting, because imported context is not
inherited by a separately dispatched agent.

Private local context stays outside Git. A tool-specific handoff that names
acceptance collections, their paths, filenames, or statistics is local state and
must never be committed, regardless of which assistant maintains it.

## Consequences

Adding another assistant requires only a new delegating entry point and a branch
prefix; no rule is copied, so no rule can drift. The cost is that each tool
reads one extra hop before reaching the authoritative file.

Branch prefixes make assistant attribution permanent in merge history while
commits remain concise, one-line, and maintainer-authored. History written
before this decision keeps its existing names and is not rewritten.

Default cross-review slows a release by one review cycle and depends on both
assistants being available. The waiver exists for that case and converts an
unavailable review into recorded debt rather than an invisible gap.

Because branch protection is procedural under GitHub Free, as recorded in
ADR 0046, these coordination rules are also procedural. They are conventions the
assistants and maintainer follow, not constraints the host enforces.
