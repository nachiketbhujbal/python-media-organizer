# ADR 0001: Keep all media processing local

- Status: Accepted
- Date: 2026-08-21

## Context

Media names, paths, metadata, pixels, and decoded playback are private. Hosted
analysis, telemetry, and automatic uploads would violate the product boundary.

## Decision

pymo performs media analysis locally, has no telemetry or cloud service, and
does not add network-backed AI. A future AI feature must be explicit, optional,
and use a local model.

## Consequences

Native local tools and models may require separate installation. Privacy takes
priority over convenience supplied by hosted services.
