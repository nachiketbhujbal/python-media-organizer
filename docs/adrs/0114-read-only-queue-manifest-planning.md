# ADR 0114: Read-only queue manifest planning

- Status: Proposed
- Date: 2026-11-07
- Builds on: ADR 0108, ADR 0112

## Context

One collection can already consume an explicitly reviewed unattended policy.
Declaring several collections must not invent authority, share mutable state,
or let one entry's working tree overlap another entry's baseline.

## Decision

Reserve version 0.7.2 for strict local manifest validation and a complete
ordered execution plan without executing it. One owner implements this branch;
one independent reviewer assesses exact commits. Queue execution, recovery,
aggregate outcomes and scheduling remain separate roadmap units.

The manifest will bind each baseline, working root, private state destination,
accepted policy and intended duplicate disposition. Planning remains zero-write
and path-private, rejects conflicting declarations across the complete queue,
and does not establish fresh media preservation or future execution authority.

## Acceptance evidence

The final contract, synthetic safety tests, complete local gates and independent
review evidence will be recorded before this decision is accepted. No production
collection, cleanup operation, workbook or external publication is part of
manifest planning.
