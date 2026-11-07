# ADR 0112: Author unattended authority from a target-local virtual plan

- Status: Proposed
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

Implementation details, format contracts, independent review and release gates
will be recorded before this proposal is accepted. Production media, cleanup,
queue execution and PyPI publication are outside this unit.
