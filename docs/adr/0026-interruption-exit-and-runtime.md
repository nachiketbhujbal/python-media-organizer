# ADR 0026: Report runtime and use exit 130 on interruption

- Status: Accepted
- Date: 2026-08-22

## Context

Long media commands need a useful final duration even when they are interrupted
or fail unexpectedly. An uncaught `KeyboardInterrupt` previously bypassed the
normal completion line and produced no stable command exit contract.

## Decision

The unified CLI catches `KeyboardInterrupt`, reports the interruption, emits
the observed elapsed runtime, and returns exit status 130. A different
unexpected exception still propagates for diagnosis, but a `finally` boundary
first emits a stopped-runtime line. Structured scan JSON remains free of extra
console records.

## Consequences

Interactive and scripted callers can distinguish user interruption from normal
command failures, and long runs retain useful timing evidence. Quiet mode and
machine-readable JSON preserve their existing output guarantees.
