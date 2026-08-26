# ADR 0067: Cache displayed-pixel fingerprints by content and runtime

- Status: Accepted
- Date: 2026-08-23

## Context

Exact-image scans repeatedly decode unchanged files through Pillow, apply EXIF
orientation, convert to RGBA, and hash dimensions plus displayed pixels. The
result is deterministic within pymo's normalization and Pillow runtime, but a
path or file timestamp alone cannot establish that cached pixels still belong
to current bytes.

An applied duplicate move has a stronger boundary than a preview: disposable
cache state must not independently authorize mutation even when its recorded
file state appears current.

## Decision

Persist the displayed-pixel digest as generic derived evidence keyed by the
complete-file SHA-256, `displayed-pixels-rgba-v1` algorithm, and exact Pillow
runtime. Decode only an exact JSON object containing one lowercase SHA-256
digest. Algorithm or runtime changes are cache misses; malformed compatible
evidence fails closed.

The image finder reads and writes the shared collection cache by default,
accepts an explicitly writable external cache, and provides `--no-cache` as a
complete hash and pixel-cache read/write opt-out. Newly computed observations
and pixel evidence publish in one bounded atomic batch. A newly added path may
reuse known pixels only after a fresh byte hash establishes matching content.

Before an applied result may create `dups`, append action history, or move an
image, re-read every file whose byte identity came from cache through the
stable collection-anchored descriptor and require the fresh SHA-256 to match.

## Consequences

Repeated scans avoid redundant Pillow decodes for unchanged content while
remaining incremental as collections grow. Dry-run output distinguishes loaded
evidence from actual reuse and computation without revealing filenames.

Cache status recognizes and validates displayed-pixel evidence without loading
media or invoking Pillow. The cache remains disposable acceleration, and the
fresh apply recheck preserves the authoritative content boundary.
