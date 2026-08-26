# ADR 0075: Layer strict decoded-video coverage over missing bytes

- Status: Accepted
- Date: 2026-08-23

## Context

A container remux can preserve exact displayed frames, normalized timing, and
decoded audio while changing the complete file bytes. The byte layer must still
report the original stream absent, but migration evidence also needs to account
for exact playback under pymo's existing conservative video definition.

Migration comparison is a second consumer of probe normalization and decoded-
playback fingerprinting. Keeping those primitives in duplicate-move
coordination would invert the package dependency and let the two contracts
drift.

## Decision

Move descriptor-based ffprobe normalization, native-tool resolution and version
checks, streamed frame/audio decoding, and `exact-playback-v2` fingerprinting
into `src/pymo/video_content.py`. Duplicate and migration domains share those
primitives while retaining separate discovery, cache, reporting, grouping, and
mutation policy. FFmpeg and ffprobe remain explicit local native dependencies.

Version 0.5.2 considers configured video-extension source byte identities that
lack an exact destination byte representative. Freshly probe one representative
per eligible source and destination byte identity. Fully fingerprint every
supported source identity and only destination identities in a compatible
structural bucket; incompatible buckets cannot satisfy the strict fingerprint.
All reads remain descriptor-pinned and are checked against the byte-inventory
state after each native-tool pass.

Report strict playback coverage as a separate schema-3 layer. A remux match
does not prove source container, metadata, codec bitstream, or complete file
bytes survived. Recompression, different audio or timing, cropping,
watermarking, unsupported stream structures, HDR/high-bit-depth input, native
decode failure, and concurrent changes never receive an exact-playback claim.
Keep command exit status tied to the byte verdict until version 0.5.3 defines
the combined final-sign-off policy.

Resolve native tools only when an eligible source byte identity actually needs
content comparison. Use sequential fresh decoding and the configured per-file
timeout. Do not read or write the derived cache during migration verification.

## Consequences

Supported remuxes can be accounted for by strict decoded playback without
hiding absent source bytes. Missing playback is definite only with complete
relevant destination evidence; a failed destination probe or decode can hide a
representative and therefore makes the video layer unproven.

The command may perform substantial sequential decoding. It reports aggregate
progress and path-private heartbeats, while filenames remain opt-in. Cache reuse
and concurrency remain deferred until they can be proven not to weaken the
preservation boundary or overload external storage.
