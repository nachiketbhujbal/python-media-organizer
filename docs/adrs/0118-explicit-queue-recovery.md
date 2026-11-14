# ADR 0118: Explicit queue recovery

- Status: Proposed
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
