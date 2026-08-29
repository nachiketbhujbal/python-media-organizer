# ADR 0036: Stage validation orchestration

- Status: Accepted
- Date: 2026-08-22

## Context

The first validation implementation concentrated traversal policy, file
classification, video stream interpretation, worker execution, and report
options in a few large functions. The behavior was tested, but independent
review showed that the branch density made safety changes harder to review.

## Decision

Separate directory filtering, single-file discovery, stream partitioning,
stream findings, duration checks, and native video inspection into typed helper
stages. Pass immutable `ValidationOptions` and `ReportOptions` objects between
the orchestration boundaries rather than long positional argument lists.

## Consequences

The command behavior and schema remain unchanged, while each policy stage can
be reviewed and tested independently. The option objects are internal
implementation types, not new configuration or public report contracts.
