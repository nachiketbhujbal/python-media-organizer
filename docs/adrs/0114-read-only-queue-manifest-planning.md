# ADR 0114: Read-only queue manifest planning

- Status: Accepted
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

The manifest binds each baseline, working root, private state destination,
accepted policy and intended duplicate disposition. Planning remains zero-write
and path-private, rejects conflicting declarations across the complete queue,
and does not establish fresh media preservation or future execution authority.

The exact schema and projection contract is in [QUEUE_PLANNING.md](../QUEUE_PLANNING.md).
All ordered jobs use accepted complete schema-4 or schema-5 policies, with
independent receipt checks for schema 5. Existing private run state is refused;
recovery is a separate release. Current directory identities and absent-leaf
parents are observed, normalized aliases are conservatively refused, and all
bindings are rechecked before emitting any plan. Control files stay outside all
collections. The existing policy parser is factored for pinned artifact reads;
ordinary unattended behavior is unchanged.

Independent review found that re-opening a private parent by its full pathname
could follow a transient intermediate link. Shared private artifact I/O now
retains a component-by-component no-follow descriptor chain through leaf access,
checks its permissions and identities, and compares queue reads with the
initially observed ancestry. Publication uses the same anchored boundary.
The original ancestry is also passed through nested receipt parsing and every
later acceptance recheck; observing a replacement parent cannot reset it.

Planning checks declaration consistency, not fresh media, free capacity or the
future namespace. A manifest grants no authority, creates no reservation and
cannot bypass later checkpoint evidence. Initial copying and manual cleanup
remain outside queue scope.

## Acceptance evidence

Independent Terra-medium review accepted corrected implementation `dee1f44`
after QUEUE-R01 and QUEUE-R02 were resolved. The owner and reviewer each passed
133 focused queue/policy tests. Static checks, all-file hooks, builds and an
isolated installed-package plan/refusal check passed. Complete coverage and
protected hosted gates are separate release prerequisites. No production
collection, cleanup operation, workbook or external publication is performed
by manifest planning.
