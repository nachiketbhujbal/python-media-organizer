# ADR 0057: Make migration preservation proof directional and layered

- Status: Accepted
- Date: 2026-08-22

## Context

Media organization is part of a larger preservation workflow: content may be
copied or rescued from one local storage location, renamed and reorganized at
another location, and reduced by removing reviewed duplicates. Comparing names,
paths, file counts, or total bytes cannot prove that source content survived.

A literal byte-for-byte inventory and an exact-media-content inventory also
answer different questions. Removing an exact byte copy changes multiplicity
without losing a unique byte stream. Removing an image variant with different
metadata or a remuxed video can retain displayed or playback content while no
longer retaining every source byte stream.

The source may be degraded or intentionally mounted read-only. Repeated reads
and any source-side cache or lock writes are unacceptable preservation
boundaries.

## Decision

Promote a directional `pymo verify-migration SOURCE DESTINATION` subsystem
after the shared derived-cache foundation and before optional enrichment
features.

The command is report-only and path-independent. It never mutates media,
appends action history, or writes cache, lock, or configuration state to the
source. Any reusable evidence is written only to an explicitly writable cache
location and remains derived and disposable.

Reports distinguish:

1. exact byte-stream preservation;
2. exact displayed-image or decoded-video content preservation under pymo's
   existing conservative definitions; and
3. missing, unreadable, changing, unsupported, or otherwise unproven input.

A complete-success verdict names its preservation contract and is available
only when every source entry relevant to that contract was read from stable
state and accounted for. Duplicate multiplicity reduction and storage savings
are reported separately from content coverage.

## Consequences

Collections can be verified after root-folder renaming, internal organization,
and deterministic media renaming. A post-deduplication destination can be
content-complete without being a strict byte-for-byte mirror, and the report
must say so plainly.

Version 0.4 cache interfaces must separate the analyzed media root from the
writable cache location. Migration verification reuses stable hashes and exact
media fingerprints without turning cache state into proof by itself.

This command verifies a copy or rescue performed elsewhere. A future
`pymo migrate` command requires its own decision because cross-device copying,
recovery from failing storage, resumability, and destination writes create a
separate safety boundary.

The preferred operational test keeps an unchanged baseline and a separate
working copy on healthy storage, mutates only the working copy, and verifies
the result against the baseline. Two trees on one physical device reduce reads
from degraded media but do not constitute independent backup copies; capacity
and device-failure risk remain explicit prerequisites.
