# ADR 0069: Unified image and video cache warming

- Status: Accepted
- Date: 2026-08-23

## Context

Exact-video warming established a safe way to populate disposable evidence
without duplicate planning or media mutation. Displayed-pixel evidence later
gave exact images the same reusable cache foundation, but the image analysis
entry point still combined inspection with grouping. Users also needed one
deliberate command that could prepare every supported evidence family.

A combined operation introduces an ordering risk: publishing image evidence
before discovering an invalid video layout or unavailable FFmpeg installation
would leave cache state from a request that was invalid at setup time.

## Decision

Support `pymo cache warm {images,videos,all} COLLECTION`. Image inspection and
cache publication are separated from displayed-pixel duplicate grouping; the
image duplicate finder composes both operations, while warming calls only the
inspection layer.

Within one image inspection run, a freshly computed pixel fingerprint is
immediately reusable for later files with the same complete byte hash, even
before the bounded publication batch is flushed. Byte-identical copies are
therefore decoded once without weakening the persisted evidence key.

Before the first cache write, warming validates every selected media layout and
completes selected discovery. When selected video files exist, it also resolves
and versions FFmpeg and ffprobe before any image evidence is published.
Image-only warming rejects video-only options. Empty selections do not create a
cache or lock. Each selector retains the existing aggregate, path-private,
external-cache, incremental-publication, and no-media-mutation contracts.

## Consequences

- `images` depends only on an organized `pics` folder and Pillow.
- `videos` depends only on an organized `vids` folder and native video tools
  when videos are present.
- `all` requires both organized folders and prepares both evidence families.
- Setup-invalid combined requests remain zero-write. Per-file inspection
  failures may retain completed disposable evidence and return incomplete
  coverage so a later run can resume.
- Cache warming remains preparation, not validation, duplicate planning, or a
  preservation verdict.
