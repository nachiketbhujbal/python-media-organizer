# ADR 0029: Provide standard and full validation profiles

- Status: Accepted
- Date: 2026-08-22

## Context

Header and structure checks are useful and relatively fast, while fully
decoding every image frame and video/audio stream can be substantially more
expensive. Treating those costs as one implicit behavior makes first-run health
checks unpredictable.

## Decision

`pymo validate` uses a standard profile by default: Pillow integrity
verification for supported images and local ffprobe structure inspection for
videos. `--full` additionally loads every image frame and decodes selected
video/audio streams completely through local FFmpeg. Both profiles bind results
to stable file state and remain report-only.

## Consequences

Users can run a meaningful routine check before opting into complete decoding.
Unsupported but recognized image formats are warnings rather than false
corruption claims. Full validation takes longer and requires FFmpeg only when a
non-empty video actually needs it.
