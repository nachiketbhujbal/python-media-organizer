# ADR 0051: Separate active heartbeats from ETA projections

- Status: Accepted
- Date: 2026-08-22

## Context

A heartbeat exists to reassure a user that one long native-media operation is
still active. The shared progress meter built that heartbeat by reusing its
completed-work status, then appending the active item. During a long decode,
the completed byte count stayed fixed while elapsed time increased. Repeated
heartbeat rows therefore displayed an increasingly volatile rate and ETA even
though no new observation supported either estimate.

The same ETA policy allowed a projection after the first completed item. Media
files can vary substantially in size and decode cost, so a single observation
is not a useful confidence boundary.

## Decision

Give heartbeats a distinct, path-private message containing only the active
item number, completed-item count, and elapsed time. A heartbeat does not show
throughput or ETA because those values describe completed work rather than the
currently active item.

Continue to calculate rates from completed work, but withhold ETA until at
least three items have completed. Use byte-weighted ETA when a bounded byte
total exists and count-weighted ETA otherwise. Keep the stable milestone,
time-interval, and final-row cadence established by ADR 0050.

## Consequences

Long operations continue to provide periodic reassurance without repeating
stale estimates or implying that an active item has completed. Early progress
rows can show a directly observed rate but omit ETA until the minimum evidence
threshold is met. Collections with fewer than four eligible items finish
without an intermediate ETA, which is preferable to presenting a projection
with too little evidence.

The threshold is deliberately a product invariant rather than user
configuration: it prevents low-confidence output and does not affect work,
matching, mutation, cache behavior, or privacy.
