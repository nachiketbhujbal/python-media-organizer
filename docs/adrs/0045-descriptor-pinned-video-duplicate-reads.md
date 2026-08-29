# ADR 0045: Pin exact-video duplicate reads to descriptors

- Status: Accepted
- Date: 2026-08-22

## Context

Stable state checks before and after video analysis reject changed results, but
they do not prevent a pathname or parent directory from becoming a symbolic
link between a check and a classifier or native decoder open. A transient read
could therefore reach unrelated local content even though the result was later
discarded.

## Decision

Open each exact-video candidate relative to no-follow directory descriptors
anchored at the resolved collection root. Require the open regular-file state
to equal the expected snapshot. Perform classification, whole-file SHA-256,
ffprobe inspection, frame hashing, and audio decoding through that descriptor.
Pass only inherited `/dev/fd` inputs to ffprobe and FFmpeg, then recheck both
the descriptor and pathname before closing.

Use one pinned descriptor for both frame and audio fingerprint passes. Keep the
existing local `file,pipe` protocol whitelist and no-capture-input assertions.

## Consequences

A concurrent link or directory swap cannot redirect exact-video content reads.
Changed candidates are skipped and never cached or moved. This design relies on
the accepted POSIX platform boundary and preserves exact-playback-v2 output for
unchanged files, so existing valid fingerprints remain compatible.
