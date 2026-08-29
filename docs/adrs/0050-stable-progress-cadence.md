# ADR 0050: Use stable completed-work progress milestones

- Status: Accepted
- Date: 2026-08-22

## Context

The shared progress meter normally emitted a row when its configured time
interval elapsed and at completion. Exact-video fingerprinting bypassed that
policy by forcing a row after every candidate. A large collection therefore
produced hundreds of completion rows, including a new row immediately after a
heartbeat even when almost no time had passed.

Purely time-driven completed-work output also varies substantially between fast
and slow machines. A fast run may show only its final count while a slower run
shows many arbitrary intermediate counts, making logs harder to compare.

## Decision

Remove the force option from `ProgressMeter.advance` and from exact-video
fingerprinting. For every non-empty bounded stage, compute at most ten evenly
spaced completed-item milestones from the known total. Emit one row when a
milestone is crossed, when the configured time interval is genuinely due, or
when the final item completes. A single advance call satisfying multiple
conditions emits only one row and consumes every milestone it crossed.

Heartbeat calls remain time-driven and continue to describe an active item
without incrementing completed work. Their wording and ETA confidence policy
are intentionally deferred to the next focused release.

## Consequences

Fast and slow runs share a stable set of count checkpoints, while slow stages
can still provide time-based reassurance between them. Exact-video completion
output is bounded rather than proportional to candidate count, and a recent
heartbeat suppresses a quick non-milestone completion row.

Small stages can report each item because collapsing ten percentage thresholds
onto fewer than ten items naturally deduplicates the milestones. JSON and quiet
output behavior remain unchanged because their callers already suppress
human-facing progress messages.
