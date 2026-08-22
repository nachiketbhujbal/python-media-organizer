# ADR 0040: Report complete ordered scan recommendations

- Status: Accepted
- Date: 2026-08-22

## Context

Scan already measures proposed organizer moves and non-canonical media names.
It previously recommended rename only when no organization was needed, while
still recommending later duplicate-finder commands. The output therefore mixed
an immediate-next-step model with a complete-plan model and could hide a major
supported workflow.

## Decision

Report every applicable action in safe workflow order: organize, rename, exact
image duplicates, then exact video duplicates. Keep each recommendation
independent so an earlier applicable action does not suppress a later one.

## Consequences

Scan remains read-only and its schema is unchanged. Text and JSON users receive
a complete ordered plan and can preview each recommended command before apply.
