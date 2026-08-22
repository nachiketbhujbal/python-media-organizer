# ADR 0035: Report validation discovery failures as health findings

- Status: Accepted
- Date: 2026-08-22

## Context

Recursive traversal can encounter unreadable directories or entries. Silently
omitting them would make a validation report appear more complete and healthy
than the work actually performed.

## Decision

Record directory-walk failures and unreadable entries as error findings.
Changing entries and skipped symbolic links are warning findings. Aggregate
counts remain path-private; `--show-files` may expose only collection-relative
affected paths.

## Consequences

An incomplete traversal returns health status 1 and is visible in text and
JSON. Permission problems cannot silently pass as a healthy collection, while
the default report still avoids filenames and collection roots.
