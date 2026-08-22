# ADR 0012: Define video duplicates by strict decoded playback

- Status: Accepted
- Date: 2026-08-21

## Context

Containers and codecs can differ while playback is identical, but perceptual
video matching is too ambiguous for automatic moves.

## Decision

Use whole-file SHA-256 as an identity fast path, ffprobe structural checks, and
local FFmpeg streaming to compare exact frames, normalized timing and
orientation, decoded audio, and supported stream structure. Skip ambiguity.

## Consequences

Remuxes may match; recompression, different audio or timing, cropping, and
watermarks do not. FFmpeg and ffprobe are explicit native dependencies.
