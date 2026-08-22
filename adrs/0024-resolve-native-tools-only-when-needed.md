# ADR 0024: Resolve native tools only when work requires them

- Status: Accepted
- Date: 2026-08-22

## Context

Exact video comparison requires FFmpeg and ffprobe, but an organized folder
with fewer than two videos has nothing to compare. Failing such a run because a
dependency is absent gives no safety or correctness benefit.

## Decision

Discover eligible videos first. Resolve and version-check FFmpeg and ffprobe
only when at least two videos require inspection for a possible comparison.

## Consequences

Empty and single-video collections receive a complete zero-duplicate report
without FFmpeg. Two or more eligible videos retain the explicit native-tool
requirement and the same conservative inspection behavior.
