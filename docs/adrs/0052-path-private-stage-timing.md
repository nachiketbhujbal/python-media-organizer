# ADR 0052: Report path-private pipeline stage timing

- Status: Accepted
- Date: 2026-08-22

## Context

The unified CLI reports a monotonic total runtime for every human-readable
command. An exact-video duplicate run can spend materially different amounts
of time discovering candidates, hashing and probing files, deriving decoded
fingerprints, planning moves, applying them, or verifying the result. A total
alone cannot identify which stage dominates a run or help compare cached and
uncached behavior.

Wall-clock timestamps are useful for log correlation but are not suitable for
elapsed measurements because the system clock can change during a run.
Filename or collection-path output is also unnecessary for performance
diagnosis and would weaken the default privacy boundary.

## Decision

Add a shared monotonic stage timer that emits a fixed stage label and formatted
elapsed duration. Instrument the explicit exact-video pipeline boundaries for
discovery, probing, fingerprinting, planning, apply, and verification.

Report a stage only when it executes. Normal dry runs therefore report the
read-only stages but not apply or verification. Applied runs report mutation
stages only when there is a non-empty move plan. Keep the existing final
whole-command runtime as the inclusive end-to-end measurement.

Stage messages use the existing logging path, so quiet mode suppresses them,
explicit log files retain them, and future default console timestamps can
prefix them without changing elapsed-time calculation.

## Consequences

Users can distinguish slow storage traversal and probing from expensive decode
fingerprinting, cache publication, planning, mutation, and verification. The
records disclose neither filenames nor collection paths and remain meaningful
if the system wall clock changes.

The first release instruments exact-video matching because it has the longest
and most distinct native-media pipeline. The shared timer can be applied to
other commands when their stage boundaries warrant separate performance
reporting; adding labels indiscriminately would create noise rather than useful
measurements.
