# ADR 0091: Build the human migration synopsis from typed stage outcomes

- Status: Accepted
- Date: 2026-09-11
- Extends: ADR 0087

## Context

The guided migration coordinator already retains strict private restart state and
one human-readable log per child stage. Those records prove which stage ran,
which explicit operator action authorized it, and which exit status it returned,
but they do not own the inventory, health, transformation, duplicate, cache, or
preservation facts needed by the version 0.6.2 human synopsis.

Re-parsing human log wording would create an undocumented compatibility surface
and could mistake display text for evidence. Re-running expensive validation or
exact-video analysis solely to reconstruct a summary would waste time and could
produce facts about a later filesystem state rather than the completed stage.
The stable public machine-readable migration report is intentionally a separate
version 0.6.4 compatibility decision.

## Decision

Each coordinator-launched child stage may write one small, aggregate,
path-private outcome record into the explicitly requested private migration log
directory. The coordinator creates the destination with private permissions,
passes it through a hidden coordinator-only command option, and accepts it only
after strict schema, stage, command, result-kind, and value validation. The
coordinator records the validated outcome filename and the observed child
duration in schema-2 restart state.

The child command remains the owner of its facts. Scan contributes inventory;
validation contributes health, aggregate findings, and validation-cache use;
mutation commands contribute planned or applied transformations; duplicate
commands contribute exact duplicate groups, copies, bytes, skips, and cache
use; and migration verification contributes layered preservation and duplicate
review-tree accounting. A failed child may contribute a valid partial outcome,
but absence or invalidity of an outcome can never be converted into a success
claim.

The human synopsis is a deterministic projection of strict coordinator history
and these owned aggregate outcomes. It labels the workflow as not started,
pending, stopped, complete and eligible for sign-off, or complete and signed
off. It keeps observed and simulated preservation separate, distinguishes
potential duplicate storage from storage actually proven reclaimed, reports
only measured durations, and never prints a collection path or filename.

Outcome records and restart state are private, version-bound coordinator
bookkeeping. They are not preservation evidence, action history, a public API,
or the stable versioned report artifact planned for version 0.6.4. Existing
standalone command output remains unchanged when the hidden coordinator option
is absent.

## Consequences

- The final synopsis can be emitted without parsing prose or repeating costly
  collection analysis.
- Persistent outcome records remain opt-in because they exist only inside an
  explicit migration log directory.
- The append-only collection action log remains the authority for reversible
  mutations; an outcome only summarizes the command result that produced it.
- A missing, malformed, mismatched, or unsafe successful-stage outcome stops
  the coordinator before it advances restart state.
- Version 0.6.4 may stabilize an exported report from the same typed model
  without declaring these private per-stage files compatible.
