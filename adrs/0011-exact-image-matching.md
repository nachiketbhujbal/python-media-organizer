# ADR 0011: Define image duplicates by displayed pixels

- Status: Accepted
- Date: 2026-08-21

## Context

Byte hashes miss images with identical pixels but different metadata or
encodings, while perceptual matching can produce unsafe false positives.

## Decision

Apply EXIF orientation, decode a single image to RGBA, and compare dimensions
and exact displayed pixels. Skip animated, multi-page, unreadable, and unsafe
inputs. Move extra copies only to `dups/pics`.

## Consequences

Metadata differences do not prevent a match. Similar-looking but non-identical
images never enter the exact move path.
