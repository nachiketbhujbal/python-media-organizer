# ADR 0118: Explicit queue recovery

- Status: Accepted
- Date: 2026-11-14
- Builds on: ADR 0116, ADR 0114, ADR 0097

## Intent

Reserve v0.7.4 for explicit recovery over the declared queue and existing
per-collection migration state. Keep `queue run` new-job-only. A separate
`queue resume MANIFEST` previews recovery without writes; `--apply` continues
only after complete control/state preflight. Completed workflows are validated
and not rerun. Unstarted jobs remain exclusive new-directory allocations.

## Safety boundary

Resume supplies no new checkpoint authority. Exact complete policies, receipts,
version, roots, options, strict lifecycle and typed outcomes remain required.
Bind existing private directories and locks for the invocation through the same
descriptor-relative I/O path used by new jobs. Never recreate missing controls,
adopt empty or incomplete state, change policy or infer missing child completion.
Unreferenced child artifacts or failed mutations require manual journal review
and are refused. A failed read/preview retry requires an explicit job ordinal;
reviewable validation findings retain existing exact policy acknowledgement.

A selected individual job may be resumed explicitly without claiming the whole
queue completed. No automatic failed-job skipping, arbitrary stage skipping,
cleanup, copying or concurrent execution is introduced. Historical completed
records are not a new preservation sign-off. Aggregate reporting remains v0.7.5.

## Acceptance

Exercise interruption between jobs/stages, completed-job immutability, explicit
read retry, partial-mutation/orphan refusal, exact bindings, busy locks,
whole-queue preflight, zero-write preview, real synthetic child execution and
installed artifacts. Require independent review and all release gates.

## Defined interface and compatibility

`queue resume MANIFEST [--job N] [--retry-job N ...] [--apply]` uses one-based
ordinals. Without `--apply` it acquires only existing advisory locks, inspects
private artifacts and required retained/authored evidence, and writes nothing.
Without `--job`, all jobs are selected in manifest order. With it, only that
job may advance; all declarations and existing state still pass preflight.
All selected failed read/preview retries must be acknowledged before any write.
A retry flag on an unselected, successful or absent job is refused.

Completed jobs are skipped only after strict terminal and outcome verification.
Arbitrary failed-stage skipping is unsupported. Individual selection is the
explicit way to work on another safe job, with no whole-queue success claim.
No state is auto-discovered; absent declared directories mean new jobs, while
occupied directories must contain a complete existing run. The same policy/run
binding used by `migrate --resume` supplies authority; no historical claim that
this exact manifest originally created the run is inferred. Version matching
remains exact; this release does not migrate prior-version state or policies.

All existing state locks are acquired nonblocking in manifest order before any
lifecycle is read and held until return. Newly allocated jobs also stay locked
through the recovery invocation. Exhaustive descriptor-pinned entry inspection
rejects all unknown, duplicate-reference, missing, unsafe or changing artifacts.
Child logs are synced, including their parent, before child launch. An orphan
log therefore blocks continuation even when the interrupted child produced no
outcome. Recovery never guesses whether an unrecorded child finished.

Existing managed destinations require a successful coordinator attempt, exact
approved preview and fresh committed journal/tree verification. Failed apply
attempts and unresolved journal operations are refused even with `--retry-job`.
Manual journal recovery remains a separate operation; do not erase private
artifacts or edit state to force queue adoption. A coherent later successful
single-collection recovery can be inspected again; ambiguous orphan artifacts
remain a refusal. No persistent schema is added or relaxed.

An unsigned terminal run under a manual policy is refused: its recorded final
verification cannot authorize current sign-off after an interruption. Obtain
fresh layered verification and explicit human review through the ordinary
single-collection workflow. Authored policies additionally rederive the bound
source and working namespaces; changed content is refused. Already signed-off
records remain historical and are never presented as new preservation evidence.
Retained trees and unresolved journals are rechecked at execution and final
boundaries, including for previously completed jobs.

## Candidate evidence

Independent Terra-medium review accepts corrected implementation `bf96be7` after
RECOVERY-R01 and R02, with 38 independently executed recovery tests. The complete
owner gate passes 900 tests and two existing distinct-filesystem skips at
88 percent subprocess-aware coverage; static checks, hooks, built artifact
inspection and installed synthetic interrupted recovery pass. Publication and
tagged artifact evidence are separate release steps.
