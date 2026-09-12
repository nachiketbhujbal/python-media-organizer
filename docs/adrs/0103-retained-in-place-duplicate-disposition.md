# ADR 0103: Retain duplicate review trees in place

- Status: Proposed
- Date: 2026-09-12
- Applies: ADR 0083, ADR 0084, ADR 0087

## Context

The existing migration workflow proves a simulated destination-without-`dups`
state, then requires the operator to move the complete review tree outside the
working collection before the coordinator will continue. That ceremony is
unnecessary when the operator deliberately chooses to retain duplicate review
copies in place and accepts that the working collection will reclaim no
physical storage.

Version 0.6.8 owns only an honest retained-in-place disposition. It must not
collapse retained content, external quarantine, or permanent deletion into one
authority contract.

## Proposed decision

Add an explicit coordinator disposition that binds a reviewed successful
without-`dups` simulation to the choice to leave the complete `dups` tree
physically inside the working collection. The coordinator may advance without
manual filesystem movement only while reporting that the evidence is
counterfactual, the review bytes remain allocated in the working collection,
and no storage has been reclaimed.

The final design must preserve strict restart-state, interactive, unattended,
resume, synopsis, report, visibility, and privacy boundaries. It must grant no
move, copy, delete, cleanup, or ordinary post-quarantine sign-off authority.

## Consequences

- Retained-in-place disposition can remove needless shell choreography without
  changing media bytes or collection layout.
- Simulation remains distinct from ordinary observed verification.
- Same-filesystem quarantine remains version 0.6.9; cross-filesystem
  quarantine remains version 0.6.10; permanent deletion remains outside
  version 0.6.
