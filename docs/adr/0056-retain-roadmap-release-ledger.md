# ADR 0056: Retain a compact release-status ledger in the roadmap

- Status: Accepted
- Date: 2026-08-22

## Context

The roadmap introduction said released entries would be removed after their
behavior reached the changelog and handoff. In practice, the version 0.3 table
deliberately retained each shipped patch with its primary purpose, acceptance
boundary, and status. That compact sequence is useful for comparing the plan
with the tag history, while the changelog remains the detailed source of truth
for shipped behavior.

The completion audit also found README next-work guidance that still named an
adversarial validation review completed before the retained stabilization
ledger. Current-state documentation must distinguish a useful historical
status record from stale future-tense guidance.

## Decision

Keep released rows in the roadmap as a compact status and sequencing ledger.
Keep detailed shipped behavior in the changelog and current engineering state
in the handoff rather than duplicating those inventories in the roadmap.

Future-work summaries in the README must follow the promoted unreleased section
of the roadmap. Completion audits must check roadmap statuses and future-tense
documentation against the current tag and changelog history.

## Consequences

The roadmap shows both where a promoted release sequence went and where it is
going, making drift visible without requiring readers to reconstruct planning
from tags. The changelog remains authoritative for release contents, and the
handoff remains authoritative for current implementation details.

Released rows can be archived later if the ledger becomes unwieldy, but that
would be an explicit documentation-structure decision rather than an implied
cleanup rule.
