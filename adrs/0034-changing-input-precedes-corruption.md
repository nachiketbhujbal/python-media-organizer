# ADR 0034: Give changing input precedence over corruption findings

- Status: Accepted
- Date: 2026-08-22

## Context

A decoder may fail because another process replaced or rewrote a file during
validation. Reporting that transient state as corrupt would overstate what was
actually established and could leave unrelated preliminary findings attached
to a stale file identity.

## Decision

Recheck the captured regular-file state after every image or video decoder
failure. If it changed, discard all findings derived from the earlier state and
report only `changed_during_validation`. Report a decoder error only when the
same captured state is still present.

## Consequences

Validation is conservative under concurrent writers and never labels a moving
target corrupt. Users must rerun after writers become idle to obtain a complete
health conclusion for that file.
