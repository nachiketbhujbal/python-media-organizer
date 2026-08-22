# ADR 0031: Use validation exit status to report health

- Status: Accepted
- Date: 2026-08-22

## Context

A report-only command still needs to be useful in scripts and backup checks.
Completing the scan successfully is different from finding no invalid media.

## Decision

Return 0 when validation completes with no error-severity findings, 1 when one
or more media or unreadable-entry errors are reported, and 2 for usage,
configuration, collection, or required-tool failures. Warnings alone return 0.

## Consequences

Automation can gate on collection health without parsing prose. Exit 1 never
means pymo changed or quarantined a file; validation remains strictly
report-only.
