# ADR 0070: Persist fresh validation evidence without implicit reuse

- Status: Accepted
- Date: 2026-08-23

## Context

Full validation is expensive, particularly for video, and previously left no
durable derived record of what profile ran, which bytes were inspected, which
local runtimes were used, or what result was observed. The shared cache can
store this evidence, but an old healthy result cannot prove that current bytes
remain readable. Complete findings also cannot be keyed by content SHA-256
alone: extension and detected-kind context may differ for byte-identical files.

Source preservation may require reading a collection while writing derived
state elsewhere. Users also need an explicit way to retain the former
zero-cache-read/write validation behavior.

## Decision

Normal `pymo validate` and `pymo validate --full` continue to inspect current
content through stable descriptors. When caching is enabled, that same
descriptor is freshly hashed and the completed result is published afterward.
No cached validation result is loaded to satisfy a normal validation request.

Validation evidence uses the existing generic schema. Its key combines content
SHA-256, a profile-specific algorithm, and a canonical namespace containing
media kind, extension, extension classification, detected kind, and the exact
applicable Pillow, ffprobe, and FFmpeg runtimes. Its strictly validated payload
contains profile, kind, outcome, findings, animated/multi-page state, and a UTC
completion time. An exact file-observation row supplies collection scope,
relative path, filesystem identity, state, and the same content hash.

Observations and results publish together in bounded atomic updates. `--cache`
selects an external database and sibling lock; `--no-cache` performs fresh
validation without cache reads, hashes for evidence, or writes. Validation JSON
schema 2 reports whether fresh validation ran, where evidence was directed,
how many file records were written, and whether publication became incomplete.

## Consequences

- Default validation writes only disposable cache state; it never modifies
  media, duplicate trees, configuration, or authoritative action history.
- An explicit external cache permits evidence collection from a read-only
  media collection.
- Completed earlier batches remain useful if a later cache publication fails,
  while the command returns nonzero and reports the incomplete publication.
- Cache status recognizes and strictly validates media-validation evidence but
  does not claim runtime reuse.
- Explicit reuse of unchanged compatible results remains a separate v0.4.12
  command mode and cannot weaken the fresh default.
