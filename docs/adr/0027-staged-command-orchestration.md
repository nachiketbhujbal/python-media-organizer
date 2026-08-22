# ADR 0027: Separate command orchestration into explicit stages

- Status: Accepted
- Date: 2026-08-22

## Context

Command entry points had accumulated discovery, analysis, reporting, cache,
planning, mutation, and verification logic in one function. That made safety
boundaries harder to review and forced tests through entire command processes.
The two duplicate finders also repeated ownership, layout, collision, undo
display, and byte-formatting policy.

## Decision

Keep entry points as coordinators and expose typed stage functions for
analysis, candidate fingerprinting, grouping, planning, apply, and
verification. Share duplicate-folder validation, review destinations,
collision naming, and undo display in `pymo.duplicates.common`, and use the
single progress byte formatter across reports.

## Consequences

Safety-critical stages can be reviewed and tested independently while command
text and filesystem behavior stay compatible. Some parsers and policy
validators remain branch-heavy by nature; complexity metrics guide focused
review but are not enabled as an indiscriminate commit blocker.
