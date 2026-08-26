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
branches can claim the same `docs/adrs/` number before either merges, and
attribution disappears once every commit is authored under the single
maintainer identity required by the Git policy.

Two assistants reviewing each other also need a way to finish disagreeing.
Without one, a review can restate a position indefinitely, and the cost of that
falls on the maintainer rather than on either assistant.

A shared `.ai` directory with per-tool symlinks was considered and rejected for
now. Symlink behavior, host-tool discovery conventions, POSIX portability, and
conflicting generated settings are unresolved, and none of them need to be
resolved to make the assistants agree on one instruction source today.

## Decision

### One authoritative instruction file

`AGENTS.md` is the single authoritative instruction file. A tool-specific entry
point exists to navigate to it: it may identify `AGENTS.md` as authoritative,
state the reading order, and link to the relevant records. It must not
introduce, alter, or duplicate a normative project requirement.

The boundary is **normative versus navigational**, not empty versus non-empty.
An entry point forbidden from saying anything useful is one no tool benefits
from reading, while a rule stated in two places is one that can drift.

### Branch naming and attribution

Name each assistant's branch with its own prefix, `claude/<type>/<slug>` or
`codex/<type>/<slug>`, adding the target version as `<type>/v<x.y.z>-<slug>`
when the work is scheduled for a release. The merge commit preserves the branch
name, so authorship stays visible in history without changing the one-line
commit convention or the maintainer authorship those commits carry.

### ADR numbers

Reserve the next free `docs/adrs/` number in shared local coordination state when
a branch starts, claim it in that branch's first commit, and name it in the pull
request. **Re-check the number against the target branch immediately before
merge, and renumber on conflict.**

Claiming alone does not prevent the collision it appears to solve: two branches
can independently select the same next free number, and each will believe it
holds the claim. The pre-merge re-check is the step that actually resolves it.

### Release ownership and review

Each release has **one owner and one reviewer, never two co-owners.**

The owner writes implementation, tests, documentation, and review-ledger
resolutions on the release branch. The reviewer does not commit to that branch:
it reports findings through its own channel, and the owner either applies them
or disputes them with evidence. Review-ledger changes are therefore written on
the branch under review, by its owner, not on the reviewer's own branch.

Each assistant adversarially reviews the other's release by default. The
maintainer may waive a review; a waived review is recorded as follow-up debt
rather than skipped silently.

Assign ownership by where the risk sits rather than by rotation. Work whose
failure mode is preservation-critical belongs to the assistant that will be
accountable for release integration, with the other performing the independent
challenge.

One assistant coordinates the final pull request, CI, merge-commit
verification, tag, and installed-version proof — and only after the maintainer
authorizes each external boundary.

### Resolving disagreement

**Evidence and tests decide technical disputes.** A measured or traced result
outranks an inferred or assumed one, so a contested claim should carry which of
those it is; that single word usually ends the dispute without either side
having to be persuasive.

**The maintainer is the final product and policy tiebreaker.** Record
unresolved dissent rather than averaging two positions into a compromise
neither assistant believes.

One round of engagement is expected. Restating a position a third time is an
escalation to the maintainer, not a further review.

### Subagents and private context

Every subagent prompt must instruct the subagent to read `AGENTS.md` and
`HANDOFF.md` completely before acting, because imported context is not
inherited by a separately dispatched agent.

Private local context stays outside Git. A tool-specific handoff that names
acceptance collections, their paths, filenames, or statistics is local state and
must never be committed, regardless of which assistant maintains it.

## Consequences

Adding another assistant requires only a new delegating entry point and a branch
prefix; no normative rule is copied, so no normative rule can drift. The cost is
that each tool reads one extra hop before reaching the authoritative file, and
that the navigational/normative line needs judgement rather than a mechanical
test.

Branch prefixes make assistant attribution permanent in merge history while
commits remain concise, one-line, and maintainer-authored. History written
before this decision keeps its existing names and is not rewritten.

Default cross-review slows a release by one review cycle and depends on both
assistants being available. The waiver exists for that case and converts an
unavailable review into recorded debt rather than an invisible gap.

Single ownership per release removes the ambiguity of two assistants editing one
branch, at the cost that the reviewer cannot fix what it finds and must describe
it precisely enough for the owner to act. That cost is deliberate: it keeps the
review adversarial rather than collaborative, and it keeps one party accountable
for the branch.

Requiring evidence class on contested claims makes disagreements resolvable
without appeal to authority, but it only works if both assistants apply it to
their own claims first. An assertion that looks confident and one that was
measured are indistinguishable until someone says which is which.

Because branch protection is procedural under GitHub Free, as recorded in
ADR 0046, these coordination rules are also procedural. They are conventions the
assistants and maintainer follow, not constraints the host enforces.
