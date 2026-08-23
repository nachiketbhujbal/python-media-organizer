# ADR 0063: Warm exact-video evidence without duplicate planning

- Status: Accepted
- Date: 2026-08-22

## Context

Exact-video fingerprinting is deliberately expensive. The duplicate finder
persists completed candidate fingerprints incrementally, but operators cannot
prepare the cache independently of duplicate grouping and a collection with no
same-structure candidates does not receive reusable fingerprints. Preservation
work also needs to analyze a read-only collection while writing disposable
derived state somewhere explicitly writable.

A warming command is stateful by definition, so it must remain clearly
separate from the zero-write `cache status` contract. Partial media failure
must not discard successfully completed evidence or be mistaken for complete
coverage.

## Decision

Add `pymo cache warm videos COLLECTION [--cache PATH]`. The extensible
`cache warm MEDIA` grammar reserves future `images` and `all` selectors without
introducing a temporary video-only command name.

Warm every safely discovered flat video in `vids`, not only records that happen
to share a duplicate-candidate bucket. Hash and probe each stable file through
the existing descriptor-pinned exact-video path, fingerprint one representative
per unique byte stream, and persist every successful new fingerprint
immediately. Reuse only evidence matching the exact-playback algorithm and the
actual FFmpeg runtime. Do not perform duplicate grouping, create `dups`, move
media, or append action history.

The default database remains collection-local. An explicit cache path selects
both the database and its sibling lock in an already existing non-symbolic-link
directory. Cache locking, descriptor-pinned reads, private staging, validation,
and atomic publication are anchored to that cache directory, not the analyzed
media root. The exact-video finder accepts the same `--cache PATH`, so a later
dry run can consume warmed external evidence while a read-only source remains
free of cache and lock state. `--cache` and `--no-cache` are mutually exclusive.

Normal output is aggregate and path-private. `--show-files` explicitly reveals
collection-relative paths that could not be represented; `--show-ignored`
retains its separate configuration-policy meaning. Complete discovered-video
coverage returns 0, incomplete media coverage or an unsafe cache returns 1,
and invalid setup returns 2. A collection containing no discovered videos
returns 0 without resolving FFmpeg or creating cache state.

## Consequences

An expensive cache can be prepared once and reused by a later dry run or apply.
Interruption retains prior successfully published records, collection growth
requires work only for new byte streams, and an external writable cache avoids
placing state on a preservation source.

The command proves coverage only for videos that classification safely
discovers under the organized `vids` boundary. It does not replace `scan` or
`validate`, and “complete discovered-video coverage” is not a collection-health
or migration-preservation verdict.
