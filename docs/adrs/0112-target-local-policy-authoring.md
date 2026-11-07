# ADR 0112: Author unattended authority from a target-local virtual plan

- Status: Accepted
- Date: 2026-11-07
- Builds on: ADR 0097, ADR 0108, ADR 0110

## Decision boundary

Version 0.7.1 composes a complete migration plan without changing collection
media or action history. Logical paths identify the planned namespace; stable
original descriptors supply content. Existing transformation and exact-media
policies remain authoritative. No scratch media copy or completed run at a
different root supplies authority.

A private candidate is distinct from an executable unattended policy. A separate
explicit acceptance binds its exact digest, target declaration, initial namespace
and bytes. Both acceptance and execution revalidate the initial binding. Later
execution still computes fresh checkpoint outcomes and mutation digests.

Planning refuses an unsupported transition or incomplete evidence rather than
publishing partial authority. Human output is aggregate and path-private;
explicit private artifacts contain the complete reviewable decisions.

## Acceptance evidence

Independent exact-SHA review and release gates remain required before release.
Production media, cleanup,
queue execution and PyPI publication are outside this unit.

## Concrete implementation

`policy plan` creates candidate schema 1 only with explicit `--output --apply`.
`policy review` projects every checkpoint and expectation without paths; the
private artifact carries full proposed moves. `policy accept --sha256` defaults
to preview and publishes schema-5 authority only with a separate `--apply`, after
fresh complete rederivation matches the exact reviewed candidate. Publication is
owner-private, single-link, exclusive and synced, outside both collection trees.

Schema 5 adds initial baseline/working and per-stage namespace digests. File
identity and bytes remain exact; future directory inodes and rename-dependent
ctimes are not guessed. Initial identity binds acceptance and the first apply;
subsequent stages bind the actual source objects at their planned paths. Every
child still owns fresh evidence, digest checks, and journaled mutation. Schema 4
remains compatible, with no coordinator/outcome/report schema change.

The implemented complete plan selects retained-in-place duplicates and no-cache
execution. A managed-quarantine manifest depends on future directory inodes and
change times. Independent design review confirmed that these cannot be authored
before mutation under the existing exact contract. Such planning is refused,
not converted to a portable hash or a partial policy. Existing working history,
unsafe/ambiguous scope and uninspectable content likewise require the separate
reviewed workflow. A partially applied child cannot resume unattended against
its prior namespace digest; journal recovery remains explicit.

See [the format and operator contract](../POLICY_AUTHORING.md). Temporary
synthetic differential tests compare the whole planned workflow with actual
execution, including metadata-varied images, corrected extensions, collision
names, retained ignored entries, and real FFmpeg remux duplicates. Production
collections are not required to prove these authoring boundaries.

Acceptance publishes and verifies the policy before publishing a separate
create-once receipt bound to its exact bytes, path, version and reviewed
candidate SHA-256. Schema 5 requires both files; extraction of the unaccepted
inner proposal supplies no authority. Scratch substitution or interruption
cannot turn mere file presence into accepted authority. Failed artifacts remain
for manual review; publication never overwrites or deletes them.
