# ADR 0032: Keep full video validation sequential

- Status: Accepted
- Date: 2026-08-22

## Context

FFmpeg already uses internal threads, and concurrent full decodes can increase
external-drive contention, heat, and runtime. Standard probes and image checks
are much lighter independent work.

## Decision

Allow bounded workers for standard validation, using the existing validated
1..32 worker setting. If `--full` includes any non-empty video, use one overall
validation worker so FFmpeg decodes remain sequential until benchmarks support
a different default.

## Consequences

Full mixed-media validation prioritizes predictable resource use over maximum
parallelism. The report states the effective worker count rather than the
requested count.
