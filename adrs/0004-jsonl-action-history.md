# ADR 0004: Store reversible actions in append-only JSONL

- Status: Accepted
- Date: 2026-08-21

## Context

Separate CSV manifests could not safely coordinate organize, rename, and
duplicate moves. SQLite would make the authoritative history less portable and
human-inspectable.

## Decision

Each collection owns `{collection-name}-actions-log.jsonl`. It records relative
paths, file identity, lifecycle events, and undo runs. Undo appends; history is
never erased or rewritten.

## Consequences

Collections and their history can move together. Commands must fail closed on
corrupt history and undo dependent actions in reverse order.
