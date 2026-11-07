# ADR 0109: Separate migration readiness from engineering milestones

- Status: Accepted
- Date: 2026-11-06
- Clarifies: ADR 0087, ADR 0105, ADR 0108

## Context

The immediate product purpose is to consolidate collections from a larger
source into a smaller destination, preserving the agreed evidence contract
while avoiding redundant copies. Repeated operational pilots do not by
themselves resolve capacity, metadata, interruption, or final cleanup decisions.
Existing retained baselines are sufficient for targeted development acceptance;
production source storage need not be accessed during ordinary engineering.

## Decision

Retain the promoted implementation order through version 0.7.5: explicit
cross-filesystem quarantine, reviewed policy authoring, queue planning,
sequential execution, recovery, and aggregate reporting. Reassess production
readiness after that sequence; neither its version nor a passing queue report
is migration sign-off. Concurrency in 0.7.6 through 0.7.8 is not a prerequisite.

Use the following readiness requirements:

1. Declare each source, preserved baseline, working collection, retained review
   tree, protected unrelated content, and ignore/exclusion scope explicitly.
   Complete a read-only retirement audit before recommending cleanup of old
   working trees. Preserve action journals, policies, and restart records.
2. Budget peak destination storage for the current batch: existing content,
   working copies, retained duplicates, copy staging, and a reviewed reserve.
   Unique-byte estimates are not measured physical savings. Same-filesystem
   holding moves reclaim no storage; shared clone extents make apparent bytes
   unsuitable as promised reclaimed capacity. The planner is an external
   tracking aid, never preservation evidence or mutation authority.
3. Distinguish exact-byte redundancy from exact displayed-image or decoded-video
   equivalence. Keep every byte-distinct variant until its metadata/container
   implications have been reviewed. A media-content match alone cannot justify
   a zero-byte-loss claim or disposal. No keeper-policy change is authorized.
4. Cross-filesystem quarantine must copy to exclusive staging, check capacity,
   verify fresh source and destination bytes, publish without replacement, and
   recover only a strictly bound interrupted operation. Preserve source media
   throughout; copying is not source cleanup or storage reclamation. Its
   implementation ADR must specify the source-retention state and how the
   coordinator represents it without claiming that the working tree is absent.
5. Initial collection copying and filesystem rescue remain separate from the
   queue over existing baseline/working pairs. Do not imply that version 0.7.5
   performs these operations. Before production, select a reviewed copying
   procedure and independently verify each copied batch.
6. Require fresh validation, complete directional preservation accounting, and
   explicit human acceptance of the named preservation contract before any
   source retirement. Account for ignored, unsupported, unreadable, changing,
   or unproven content separately; a report never proves whole-device recovery.
   The operator performs any eventual Trash, deletion, or formatting outside
   pymo. No source or duplicate deletion is added to this sequence.

Do not require repeated full real-collection pilots merely because a release
number changes. Required synthetic, adversarial, interruption, real-FFmpeg,
platform, packaging, and independent-review gates remain mandatory. A targeted
real-collection test needs a specific unresolved acceptance question and uses
an isolated disposable working copy of a preserved baseline. Never mutate the
baseline to run such a test. Cross-filesystem behavior still requires evidence
across distinct filesystems; copies on one filesystem alone cannot prove it.

Old trial trees may be retained in a holding area for later operator cleanup.
Preserve whole trees with their journals. Saved restart state and quarantine
undo bind exact locations, so moving a tree retires its ordinary resumability
unless its exact required locations and identities are restored and verified.
Keep active runs, baselines, and their retained quarantine locations stable.

## Consequences

The existing release sequence remains cohesive and can proceed without more
routine pilots. Production readiness gains explicit capacity and preservation
criteria. Metadata inspection/export and resumable rescue copying remain later
work; if manual review or copying cannot satisfy a production requirement,
promote that missing capability through a separate decision before migration.
This decision changes no installed behavior, report schema, release tag,
collection data, workbook, or cleanup authority.
