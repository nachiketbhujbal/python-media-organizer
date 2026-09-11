# ADR 0086: Keep release documentation aligned with verified release state

- Status: Accepted
- Date: 2026-09-10

## Context

Version 0.5.12 completed independent exact-SHA review, protected merge,
exact-main continuous integration, annotated tagging, release checks, and
installed-wheel verification. Several current documents nevertheless retained
candidate, pending-review, or pending-release language from the final
pre-release commit. That contradiction made the documented availability and
next-work guidance less trustworthy than the release evidence.

The next useful product phase is to exercise the released workflow on existing
real collections and let observed operational friction inform later priorities.
Those collections contain private paths, filenames, media, statistics, and
identifying metadata that do not belong in public project records.

## Decision

Version 0.5.13 is a documentation-only release that reconciles every current
availability, review, roadmap, changelog, and handoff claim with the verified
v0.5.12 release. It records both v0.5.12 and v0.5.13 as released in the tagged
state and uses one concise public product description:

> Organize and transform a media collection without silently losing,
> overwriting, misclassifying, or falsely claiming preservation of content.

After v0.5.13, controlled workflow trials on existing real collections become
the immediate evidence-gathering phase. Only generic, aggregate observations
needed to assess the workflow or motivate a later decision may enter project
records. Collection names, paths, media, statistics, and identifying metadata
remain private. An observation does not by itself promote a feature or
authorize a product change.

This release changes no runtime, package, configuration, command, report,
cache, journal, migration, or media behavior.

## Consequences

- Current documentation names the actual released state instead of preserving
  a stale candidate checkpoint as present truth.
- Historical review failures and intermediate candidates remain recorded,
  while their final disposition is explicit.
- Real-collection use can guide prioritization without importing private
  collection evidence into the public repository.
- Any feature arising from those trials still requires its own promoted scope,
  safety analysis, and release evidence.
