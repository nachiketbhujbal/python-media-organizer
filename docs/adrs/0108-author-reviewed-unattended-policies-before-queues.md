# ADR 0108: Author reviewed unattended policies before queues

- Status: Accepted
- Date: 2026-09-14
- Builds on: ADR 0097, ADR 0105
- Supersedes: ADR 0105 (unreleased version 0.7.1 through 0.7.7 allocation only)

## Context

Version 0.6.5 can drive one migration in a single unattended invocation, but
only after the operator supplies an exact private policy containing every
checkpoint decision and the aggregate evidence and mutation-plan digests it may
accept. That boundary is intentionally safer than a general yes-to-all switch,
but version 0.6.9 provides no first-class way to author the policy. The current
contract is practical only when a person or another tool assembles schema 3
from a separately reviewed run.

Real collection trials proved that the unattended executor can reproduce an
independently reviewed result and stop on an unexpected boundary. They also
showed that hand-authoring the policy is the remaining obstacle to ordinary
one-command use. A completed run at a different root cannot safely supply
target-bound mutation and quarantine authority by aggregate analogy alone.
Queueing several collections before solving that obstacle would multiply
manual policy construction or make the queue responsible for inventing
authority.

ADR 0105 assigns cross-filesystem managed quarantine to version 0.7.0 and then
begins queue planning at version 0.7.1. None of the affected later versions is
released, so one policy-authoring unit can be inserted without changing a
shipped interface or artifact.

## Decision

Version 0.7.0 remains cross-filesystem managed quarantine. Version 0.7.1 adds a
first-class local workflow for authoring and reviewing an unattended-policy
candidate before any queue work begins.

The authoring workflow performs a complete zero-media-mutation plan against the
exact declared baseline and working roots that unattended execution will later
use. It must compose each deterministic namespace transition without applying
it, run the required fresh media analyses against the descriptor-pinned source
bytes represented by that planned namespace, and derive every validation,
transformation, duplicate, disposition, and final-verification expectation that
the policy would authorize. The resulting candidate must expose every
checkpoint decision, expected aggregate, mutation-plan digest, duplicate
disposition, and quarantine binding in both machine-readable and
human-reviewable form.

The complete plan is bound to the exact tool version, canonical roots, saved
options, root identities, initial namespace, file content, and selected
quarantine topology. It may use explicit owner-private planning state, logs,
and disposable cache under their existing safety rules, but it writes no media
or collection action history. Any unsupported virtual transition, incomplete
discovery, unstable file, unsafe tree, uninspectable content, occupied target,
or inability to derive later-stage evidence stops planning without a complete
candidate.

Generation is not approval. The candidate must remain non-authoritative until
one separate, explicit human acceptance step publishes an owner-private policy
in the currently supported unattended-policy schema. That acceptance binds the
exact candidate bytes and target declaration; changing either requires another
review. Review and acceptance do not start a migration.

The implementation must not translate a completed run from a different root,
invent mutation-dependent outcomes from aggregate counts, silently skip an
unsupported stage, or weaken the unattended executor's fresh evidence and
plan-digest checks. Unattended execution must still rederive and compare each
authorized stage against the accepted policy immediately before crossing its
checkpoint. A changed root identity, namespace, byte stream, version, option,
plan, or quarantine endpoint therefore invalidates the candidate or stops the
later run.

Exact command names, draft format, and whether acceptance creates a new policy
file or promotes a create-once candidate are implementation details for the
version 0.7.1 ADR. Any public file format requires its own explicit schema and
compatibility contract. The accepted policy remains private and local.

The existing queue and scheduler units retain their order and acceptance scope
but move one patch later:

| Former version | New version | Primary purpose |
| --- | --- | --- |
| 0.7.1 | 0.7.2 | Queue manifest and planning |
| 0.7.2 | 0.7.3 | Sequential queue execution |
| 0.7.3 | 0.7.4 | Queue recovery |
| 0.7.4 | 0.7.5 | Queue synopsis |
| 0.7.5 | 0.7.6 | Storage-aware scheduler measurements |
| 0.7.6 | 0.7.7 | Bounded intra-collection scheduling |
| 0.7.7 | 0.7.8 | Bounded cross-collection scheduling |

Accepted ADR 0105 remains unchanged as the historical record of the version
0.6/0.7 boundary. This ADR supersedes only its allocation of unreleased version
0.7.1 through 0.7.7 work.

## Consequences

- A user can plan and review the exact target without mutating its media, then
  invoke the existing unattended executor once without manually transcribing
  its policy.
- Queue manifests can consume deliberately authored policies instead of
  becoming an implicit authority generator.
- Version 0.7 now runs through 0.7.8, while version 0.7.0 and every existing
  queue and scheduling acceptance boundary retain their prior scope.
- Version 0.7.1 requires its own implementation ADR, synthetic tests,
  adversarial exact-SHA review, protected pull request, and appropriate
  real-collection acceptance before release.
- This roadmap decision changes no runtime, package, command, report, cache,
  journal, migration, media, installed version, or release tag.
- Automatic deletion remains outside the promoted plan.
