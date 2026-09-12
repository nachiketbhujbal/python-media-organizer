# ADR 0103: Retain duplicate review trees in place

- Status: Accepted
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

## Decision

Add an explicit coordinator disposition that binds a reviewed successful
without-`dups` simulation to the choice to leave the complete `dups` tree
physically inside the working collection. The coordinator may advance without
manual filesystem movement only while reporting that the evidence is
counterfactual, the disposition is operator bookkeeping rather than fresh
inventory evidence, and pymo reclaimed no storage.

Rename the workflow checkpoint from `external-quarantine` to
`duplicate-disposition` and add the mutually exclusive `--retain-dups` action.
Preserve `--confirm-quarantine` as the compatibility action for a separately
managed external move. Retention requires a no-follow inspection of `dups` as
a real directory whenever the successful simulation found review files; a
missing, symbolic-link, or non-directory path stops without advancing. A
zero-file simulation records the disposition as not applicable.

Interactive operation chooses the applicable question from the reviewed
simulation and current path, then reloads strict state and collection identity
after the answer before recording it. Unattended policy schema 2 names either
`retain-dups` or `confirm-quarantine` at the same checkpoint and binds the
choice to exact simulated aggregate evidence. Private coordinator state schema
4 records the selected action.

Migration-report schema 2 adds `workflow.duplicate_disposition` and review
states for `retained-in-place` and `not-applicable`. The existing
`external_quarantine_confirmed` boolean remains true only for that separate
legacy-compatible choice. `physical_storage_reclaimed` remains false for every
state.

After either disposition, the existing final full validation and ordinary
fresh verification still inspect the physical working collection. Simulation
and restart bookkeeping grant no sign-off, movement, or deletion authority.

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
