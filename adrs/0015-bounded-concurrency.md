# ADR 0015: Add concurrency only where bounded and measured

- Status: Accepted
- Date: 2026-08-22

## Context

Parallelism can improve classification but simultaneous FFmpeg decodes may
increase external-drive contention and FFmpeg already uses internal threads.

## Decision

Use bounded threads for scan classification. Keep exact video decoding
sequential until representative benchmarks justify a bounded process model.
Report observed rates rather than guessed universal performance.

## Consequences

Current long video scans favor predictable resource use. Future concurrency
requires measurements and safety tests.
