# Cross-filesystem retained copying

This is the unreleased v0.7.0 contract. The installed v0.6.9 command supports
same-filesystem movement only. Copy mode is explicit and never an automatic
fallback from that movement.

```bash
pymo quarantine-dups "/path/to/collection" "/other-filesystem/retained-tree" --copy --copy-reserve-bytes 1073741824
pymo quarantine-dups "/path/to/collection" "/other-filesystem/retained-tree" --copy --copy-reserve-bytes 1073741824 --apply
```

The reserve is an explicit operator choice, in bytes. The example leaves one
GiB beyond the estimated staged allocation; it is not a universal recommendation
or a reservation against other writers. Preview writes nothing. The existing
destination parent must be safe, outside the collection, and on another
filesystem. The final target must be absent.

Pymo copies the complete `dups` tree through anchored no-follow descriptors,
verifies every file byte stream, publishes without replacement, rechecks the
source, and appends its result to the collection action journal. All originals
remain in `dups`. No physical space or working-collection bytes are released.
Embedded media metadata is part of the copied file bytes. Ownership, ACLs,
extended attributes, resource forks, and other filesystem metadata are not
claimed preserved. Preview and result output report aggregate observed extended
attributes and inspection unknowns without revealing their names or paths.

## Interruption

Repeat the same explicit paths, mode, and reserve with recovery:

```bash
pymo quarantine-dups "/path/to/collection" "/other-filesystem/retained-tree" --copy --copy-reserve-bytes 1073741824 --recover --apply
```

Recovery accepts only the exact journal-bound source, destination parent,
stage, and scratch identities. It freshly rehashes completed staged files before
reusing them. Incomplete scratch files remain in a separate private sibling
area. Each has a journal-bound UUID, file identity, destination-relative path
and expected bytes recorded before copying. Recovery accounts for every
recorded artifact at its exact scratch or staged/published location; missing,
unrecorded or substituted files require operator review. Retried copying uses
a new exclusive file. Scratch never enters the final
published tree. A fully published tree awaiting journal completion must be the
recorded staging directory itself, not merely an equal-looking replacement.

An interrupted directory creation before its identity was durably recorded can
leave an orphan. Pymo stops for operator review rather than adopting it by name.
Changed source data, occupied targets, unsafe entries, or malformed history also
stop recovery. Pymo never deletes, truncates, or overwrites to resolve these
conditions. A preflight failure before journal creation can be retried through
a fresh preview and apply. Recovery can also restart a child that failed before
recording any intent, but only after proving the journal is absent or strictly
valid, fully committed, and copy-free. All ordinary apply preflights still run.

There is no destructive copy undo. A committed copy protects the original
review tree from overlapping pymo mutations and dependent undo. Keep the source,
retained copy, and journal together as an evidence set. Operator retirement is
separate and invalidates future claims about unchanged copied correspondence.

## Guided migration

Select copy mode when creating the private run:

```bash
pymo migrate "/path/to/baseline" "/path/to/working" --log-dir "/path/to/private-state" --quarantine-destination "/other-filesystem/retained-tree" --quarantine-copy-reserve-bytes 1073741824 --start
```

At duplicate disposition, `--quarantine-dups` previews the saved operation and
`--quarantine-dups --apply` applies the exact reviewed plan. The result is
`copied-source-retained`; it never becomes an absent-`dups` confirmation.
If a child commits before the coordinator saves its result, repeat the same
apply to reconcile that exact journaled copy. Subsequent execution and sign-off
require fresh verification of both source
and retained copy. Final ordinary migration verification still includes `dups`.
The report is historical bookkeeping, not fresh evidence or cleanup authority.
A future manual retirement requires separate fresh preservation evidence under
the chosen byte or media-content contract.

Restart state is schema 6; private outcomes, unattended policies, and public
migration reports are schema 4. Earlier state/policy versions fail closed.
Policy generation remains planned for v0.7.1. No initial collection copying,
source-drive cleanup, metadata merger, or queue behavior is added here.
