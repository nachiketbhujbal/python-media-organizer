# ADR 0025: Omit changing files from scan reports

- Status: Accepted
- Date: 2026-08-22

## Context

A collection scan is a point-in-time report assembled over many filesystem
reads. Combining a size captured before a change with classification or hash
data read afterward produces internally misleading inventory and duplicate
statistics.

## Decision

Carry stable regular-file state through collection discovery, classification,
and optional checksumming. Omit files detected changing during those stages,
count them separately from unreadable entries, and include a path-private
warning in text and JSON reports.

## Consequences

Reports prefer an explicit incomplete count over mixed-state facts. The scan
remains read-only and best-effort; continuously changing collections may need a
later rerun after writers become idle.
