# ADR 0083: Simulate preservation without the duplicate review tree

- Status: Accepted
- Date: 2026-08-29

## Context

The exact duplicate finders move review copies into the destination collection's
`dups` tree without deleting them. Ordinary migration verification correctly
includes that physical tree: silently ignoring it could let the only retained
representative of source content satisfy a preservation claim.

Before an operator moves the reviewed tree to retained external quarantine,
they need a zero-write answer to a different question: would the declared
source still be accounted for if the current destination `dups` tree were no
longer part of the destination evidence? Physically moving the tree merely to
test that question adds risk, changes the action-journal dependency boundary,
and makes the preview itself harder to audit.

## Decision

Version 0.5.10 adds the explicit
`pymo verify-migration SOURCE DESTINATION --simulate-without-dups` mode. The
command freshly discovers and hashes the complete physical destination,
including `dups`, then partitions regular files beneath that fixed review root
out of the destination comparison inventory. Those files cannot satisfy exact
byte, exact displayed-image, or strict decoded-video coverage and do not enter
the simulated destination multiplicity or destination-only accounting.

The report inventories the excluded review tree separately, including stable
file and byte totals, unique streams, duplicate copies, directory and excluded
entry counts, and any explicitly requested relative file, ignored, or problem
paths. Missing, unreadable, unsafe, unstable, or traversal evidence remains
visible and fail-closed; simulation does not turn an incompletely inspected
physical namespace into a complete result.

Final stability revalidates the complete physical source and destination
namespaces, not only the filtered comparison view. Every byte, image, video,
and final preservation verdict is explicitly labeled simulated. A simulated
complete result is eligible only for human quarantine review. It is not an
observed post-quarantine verification, a deletion instruction, or final
migration sign-off. After external quarantine, ordinary fresh verification
must prove the physical working collection again.

The machine-readable report advances to schema 5 and states whether the result
is observed or simulated. Simulation changes no files and creates no cache,
lock, configuration, duplicate tree, action-log record, or other state.

## Consequences

Content represented only beneath `dups` makes the simulation non-complete even
when ordinary verification is complete. A representative retained elsewhere
in the destination can still satisfy the appropriate evidence layer. Review
tree bytes remain freshly inventoried and path-private by default.

Hashing the physical tree before partitioning adds no second content-read pass
and preserves the existing descriptor-pinned evidence boundary. The report is
counterfactual by design; operators must retain quarantine and run the ordinary
command after the physical move before signing off.
