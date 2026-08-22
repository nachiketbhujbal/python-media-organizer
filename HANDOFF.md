# python-media-organizer handoff

## Project scope

This repository is the complete durable source for the Python package. Future
work should rely on this handoff, the project instructions, source modules, and
tests; no earlier task or machine-specific path is required.

Private media-collections are never project fixtures and must never be moved
into this repository or named or described in source, tests, documentation,
logs, or Git history.

## Product decisions

The package is named `python-media-organizer`, imports as `pymo`, exposes the
`pymo` command, and starts at version `0.1.0`. It is a deliberately local-first
tool for personal media collections.

Hard requirements:

1. Mutating commands default to dry run and require `--apply`.
2. Never delete media, overwrite existing files, or silently choose a different
   undo destination.
3. Every applied filesystem operation participates in a collection-local,
   append-only `media_actions.jsonl`.
4. Undo appends history. It does not erase the log or prior run records.
5. Preflight and identity checks abort safely when later changes make an older
   action impossible to reverse exactly.
6. All content processing stays local. There is no telemetry, cloud service,
   hosted AI, or automatic download behavior.
7. Persistent logs require an explicit `--log-file` path.
8. Python dependencies belong in `pyproject.toml` and development uses `.venv`.
9. Collection folders follow the four-character `pics`, `vids`, and `dups`
   convention.
10. Repository text and tests use generic synthetic collections only.

`media_actions.jsonl` remains the authoritative portable journal because it
moves naturally with a media-collection on external storage. SQLite is useful
only as a derived, disposable collection-local cache or index.

## Current package layout

```text
python-media-organizer/
  pyproject.toml
  README.md
  RESEARCH_IMPROVEMENTS.md
  AGENTS.md
  HANDOFF.md
  src/pymo/
    __init__.py
    __main__.py
    cli.py
    logging_config.py
    action_log.py
    organize.py
    rename.py
    duplicates/
      images.py
      videos.py
  tests/
```

The CLI subcommands are:

```text
pymo organize COLLECTION
pymo rename COLLECTION
pymo find-image-duplicates COLLECTION
pymo find-video-duplicates COLLECTION
```

Each supports dry-run/apply behavior; all four support `--undo`, which is also
a preview unless combined with `--apply`. Global `--verbose`, `--quiet`, and
`--log-file PATH` options go before the subcommand.

## Shared action log

`src/pymo/action_log.py` stores one `media_actions.jsonl` in each
media-collection.

- Paths are relative to the collection, preserving portability.
- Runs and actions have UUIDs.
- File actions record size, SHA-256, device, and inode identity.
- Every mutation is preceded by a flushed and synced `ACTION_PLANNED`, then an
  `ACTION_COMPLETED`; successful runs end with `RUN_COMMITTED`.
- The journal is locked during mutation recording.
- Undo plans are fully checked before changes begin.
- Later active runs sharing file identities or paths block earlier undo.
- Interrupted applies can be discovered and reversed from logged plus observed
  state.
- Successful undo writes new events and retains the complete audit trail.

This ordering is intentional. For example, if organization is followed by
renaming, organization cannot be undone until renaming is undone. The same rule
applies when a duplicate finder later moves a renamed file.

Older CSV support remains intentionally narrow:

- `organize` can undo an old `organization_manifest*.csv`, including an
  explicitly selected `--manifest`.
- `find-image-duplicates --reorganize-existing` can read old
  `move_manifest*.csv` files and flatten legacy `group_*` output.
- New applied work uses JSONL and does not need new CSV manifests.

## Organizer

`src/pymo/organize.py` recursively flattens a supplied collection into:

```text
media-collection/
  pics/       pictures directly inside
  vids/       videos directly inside
  other files directly at the root
```

It uses the operating-system `file` utility for content-aware MIME detection
where useful, with extension fallback for generic/unknown results. It fixes
media already in the wrong destination, uses collision names such as
`name (1).ext`, skips symbolic links, removes only directories that became
empty, and performs post-apply verification.

The whole `dups` tree is protected so isolated copies are never pulled back
into normal media folders. If an applied run created `pics`, `vids`, or removed
empty source directories, logged undo restores the exact recorded structure.

## Renamer

`src/pymo/rename.py` creates deterministic names without pretending to see the
content. The format combines a normalized collection name, `image` or `video`,
a stable sequence, a trustworthy timestamp/date or `undated`, and cleaned
descriptive tokens where the original name contains useful words.

It recognizes selected EXIF and filename date patterns, distinguishes date-only
evidence from complete timestamps, removes opaque hashes/platform noise and
repeated collection text, leaves non-media and canonical names unchanged, and
protects `dups`. Applied renames are verified and logged as `RENAME` actions.

Local visual-language naming is accepted only as an optional future feature:
models must be explicitly installed, verified, licensed, local-only, and unable
to fall back to a network service. Suggested names must be reviewable rather
than applied automatically.

## Exact image duplicates

`src/pymo/duplicates/images.py` owns only `pics` and `dups/pics`. It does not
require, inspect, create, validate, or modify `vids` or `dups/vids`.

It uses Pillow to apply EXIF orientation, convert to RGBA, and SHA-256 hash
dimensions plus decoded displayed pixels. Filenames and metadata do not affect
equivalence. Animated, multi-page, unreadable, and unsafe inputs are skipped.

Within an exact group it keeps the largest file, then oldest on a size tie,
then stable filename order. Extra copies move to flat readable names such as
`retained_copy(1).jpg`. The report distinguishes scanned bytes, retained
original bytes, duplicate bytes, and potentially reclaimable storage. Nothing
is deleted.

The matching, keeper policy, readable names, conservative skips, action-log
integration, and undo behavior are approved. Do not change these core choices
without an explicit user request.

## Exact video duplicates

`src/pymo/duplicates/videos.py` is implemented and owns only `vids` and
`dups/vids`. It does not require, inspect, create, validate, or modify `pics` or
`dups/pics`.

FFmpeg and ffprobe are explicit native executables. The implementation:

1. Discovers flat videos with the same conservative classifier used by the
   collection tools.
2. Computes whole-file SHA-256 as a cheap exact-byte identity and cache key.
3. Uses ffprobe JSON for structure, dimensions, timing, orientation, audio, and
   candidate bucketing.
4. Streams FFmpeg `framehash` output with microsecond-normalized frame timing
   and autorotated displayed frames.
5. Streams normalized decoded PCM into SHA-256 and includes audio start timing.
6. Combines structure, frame/timing, orientation, and audio facts into the
   `exact-playback-v2` fingerprint.

The explicit `-enc_time_base:v filter` setting is important. A generated timing
regression test caught a previous normalization error; algorithm version `v2`
prevents reuse of stale fingerprints from that behavior.

A strict match can span byte-different remuxed containers but requires exact
supported decoded playback. Different audio or playback timing does not match.
Recompression, cropping, shortening, watermarking, and merely perceptual
similarity do not enter the automatic move path.

Unsupported or ambiguous cases are reported and retained: corrupt inputs,
multiple video/audio tracks, attachments, subtitle/data streams, and HDR or
high-bit-depth video. Decoding is bounded and streamed; decoded temporary media
is never created.

FFmpeg input protocols are restricted to `file,pipe`, and tests assert that
decode commands contain no macOS, Windows, or X11 capture input. The tool does
not need Screen & System Audio Recording, Camera, or Microphone permission.

Applied scans can update collection-root `.pymo.sqlite3`. It is a derived cache
keyed by content SHA-256, fingerprint algorithm version, and actual FFmpeg
version. Dry runs may read an existing cache but do not create or mutate it.
SQLite uses a non-persistent journaling mode and connections close explicitly,
so `-wal`/`-shm` sidecars are not left behind.

The finder mirrors image behavior for deterministic keeper choice, readable
`copy(n)` destinations, no overwrite/delete, action-log undo, post-operation
verification, and retained/duplicate/reclaimable storage reporting.

## Logging

`src/pymo/logging_config.py` routes all command output through the standard
library logging package while preserving readable text expected by existing
behavioral tests.

- Default `INFO` messages go to stdout.
- Warnings/errors go to stderr.
- `--verbose` enables diagnostic `DEBUG` output.
- `--quiet` keeps only warnings and errors.
- `--log-file PATH` creates a timestamped local log only at the requested path.
- No persistent log is created by default.

Do not put media bytes or unrelated metadata into exceptions or diagnostics.
Machine-readable result output is separate future work.

## Dependencies and environment

Python 3.11 or newer is required. Runtime dependency: Pillow. Development
dependency: pytest. Both are declared in `pyproject.toml`.

FFmpeg/ffprobe remain external runtime dependencies to keep native binary
origin, licensing, and updates explicit. The current development machine has a
Homebrew FFmpeg installation available; tests skip real integration cases when
the executables are absent.

Setup and verification:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/pymo --version
```

## Test coverage state

The suite is entirely synthetic and temporary. Current coverage includes:

- organizer dry run, apply, verification, collisions, nested layouts, content
  classification, symbolic-link safety, empty-directory restoration, reruns,
  legacy CSV undo, and `dups` protection;
- renamer parsing and cleanup across varied filename structures, deterministic
  names, collisions, apply/undo, and `dups` protection;
- action journal ordering, locking model, interrupted run recovery, identity
  changes, conflict refusal, cross-tool dependencies, and ordered undo;
- image exact-pixel equivalence across metadata/format differences, strict
  folder ownership, storage accounting, collisions, legacy output migration,
  dry run/apply/undo, and review-tree restoration;
- real FFmpeg byte-copy/remux matches, different-audio and different-timing
  non-matches, corrupt and multi-audio skips, strict ownership, collisions,
  cache/sidecar behavior, cross-tool undo dependencies, missing runtime errors,
  and local-file-only/no-capture command construction;
- unified CLI version, default no-log behavior, explicit logging, verbose mode,
  and quiet mode.

Run the complete suite after every change. Do not replace real FFmpeg
integration coverage with mocks alone.

## Research and roadmap

`RESEARCH_IMPROVEMENTS.md` is the durable research notebook. It records the
assessment of Home Media Organizer, PyPipeline, Czkawka, Video Duplicate Finder,
digiKam, organize, Phockup, dupeGuru, and related design ideas. It also defines
privacy constraints, licensing cautions, validation, metadata, comparison,
local indexing, keeper scoring, similarity levels, and local-AI rules.

Near-term roadmap:

1. Add read-only `pymo scan COLLECTION` with counts, types, storage, layout
   readiness, validation warnings, duplicate potential, and estimated cost.
2. Add report-only media validation.
3. Add metadata inspection/export and confidence-based date provenance.
4. Add read-only collection/backup comparison.
5. Expand the disposable SQLite index for local statistics and fingerprints.
6. Add perceptual similarity as report-only functionality.
7. Revisit optional local AI suggestions after deterministic tooling matures.

`scan` is the selected name; do not call this future feature `inspect`.

## Git policy

This project uses a local Git repository with concise one-line commits. No
remote is configured and nothing should be pushed until the user supplies and
explicitly approves a personal remote. Confirm private collection data and
generated state are absent before every commit.
