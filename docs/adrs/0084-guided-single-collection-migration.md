# ADR 0084: Guided single-collection migration

- Status: Accepted
- Date: 2026-08-29

## Context

The production migration runbook deliberately separates one unchanged baseline
from one mutable working collection. Its commands are individually safe, but a
complete run repeats roots, privacy options, native-tool options, log paths, and
more than twenty ordered evidence and mutation checkpoints. A loose shell
script can reduce typing, but it cannot durably distinguish a reviewed preview
from an applied mutation, preserve child exit status, or stop at the external
quarantine boundary without adding private collection-specific policy.

The coordinator must reduce operational fatigue without weakening the existing
commands. Prior stage state is workflow bookkeeping, not current preservation
evidence. Rescue copying, automatic quarantine, deletion, and multi-collection
queues remain separate product boundaries.

## Decision

Version 0.5.11 adds `pymo migrate BASELINE WORKING` as a coordinator over the
documented single-collection sequence. With no explicit private log directory,
it is zero-write and prints the complete plan. `--log-dir` selects one private
directory outside both collection roots; `--start` initializes schema-1
restart state there, and later invocations bind that state to the same canonical
baseline and working roots. Root separation uses device-and-inode ancestry
rather than lexical path spelling, including for a not-yet-created log-directory
leaf, so filesystem case or Unicode aliases cannot turn one collection into
both roles or place coordinator state inside collection evidence. Genuinely
distinct directories on a case-sensitive filesystem remain distinct.

`--run-next` executes exactly one current child command. It never batches later
steps, and it returns the child's real status. A nonzero status stops progress
and remains recorded. Only a validation finding status may be advanced through
a separate explicit acknowledgement; configuration, evidence, discovery,
verification, or mutation failures cannot be waived.
Coordinator setup, state, and invocation failures return status 2; an executed
child retains its own status, and status 1 therefore remains reviewable child
findings rather than an ambiguous coordinator error.

Every mutating operation remains two distinct stages: the ordinary preview
must succeed first, then the apply stage additionally requires the coordinator's
`--apply`. Extension correction runs before organization and deterministic
renaming. Image and video duplicate isolation remain separate. Fresh ordinary
migration verification follows every applied transformation. The later
simulation without `dups` remains zero-write and can advance only to an external
quarantine checkpoint. Pymo does not move that tree; the operator moves or
retains it outside the working root, then uses an explicit confirmation while
the canonical review path is absent. Final full validation and ordinary fresh
verification run only after that checkpoint.

Common privacy, configuration, native-tool, timeout, cache, and worker options
are carried to the child commands that own them. An explicit log directory
creates one stage-specific persistent log per attempt. The private state and
lock are not action history, preservation evidence, or authorization to remove
the baseline, source, quarantine, or working data. State publication is locked,
private-permissioned, validated, and atomic; mismatched, malformed, unknown, or
out-of-order state fails closed.

## Consequences

- One invocation performs at most one evidence or mutation step, so every
  preview, apply, finding acknowledgement, and quarantine transition remains a
  visible human checkpoint.
- Restarting avoids re-entering roots and options, but does not reuse a prior
  scan, validation result, migration verdict, media hash, or decoder result as
  current evidence.
- The baseline is passed only to read-only scan, validation, and verification
  commands. Mutating child commands receive only the working collection.
- Persistent paths and filenames enter logs and coordinator state only after
  the operator explicitly selects the private directory.
- A completed coordinator sequence means the documented child stages ran and
  the final observed verification succeeded. It remains eligible for human
  sign-off only and proves neither whole-device recovery nor safe deletion.
