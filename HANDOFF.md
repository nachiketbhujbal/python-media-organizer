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
`pymo` command, and has a `v0.3.3` report-only validation release. It is a
deliberately local-first tool for personal media collections. Git tags are the
authoritative version source; package code and `[project]` do not contain a
static version.

Version 0.3.3 pins validation classification and decoder reads to stable,
no-follow file descriptors beneath the collection root, preventing concurrent
pathname swaps from redirecting reads. Version 0.3.2 separates validation
discovery, video stream policy, execution,
and report options into typed stages without changing behavior. Version 0.3.1
hardens validation path privacy, reports unreadable traversal,
minimizes native-tool output, validates basic video stream fields, and ensures
changing inputs are never mislabeled corrupt. Version 0.3.0 adds standard and
full-decode collection health reports with
path-private JSON, explicit relative-path opt-in, stable file-state checks, and
no media or collection-state writes. Version 0.2.6 separates command analysis,
planning, apply, and verification stages, consolidates shared duplicate policy,
and measures coverage across real CLI
subprocesses. Version 0.2.5 omits files detected changing during scan
classification or checksumming and guarantees final runtime/status reporting
for interruption.
Version 0.2.4 binds exact image/video conclusions to stable file state,
revalidates duplicate groups through apply, handles malformed media
conservatively, rejects invalid derived-cache data before decoding, and only
requires FFmpeg when at least two videos need comparison. Version 0.2.3 made
schema 1 journal parsing strictly fail closed and introduced descriptor-relative
atomic no-replace moves.

Hard requirements:

1. Mutating commands default to dry run and require `--apply`.
2. Never delete media, overwrite existing files, or silently choose a different
   undo destination.
3. Every applied filesystem operation participates in a collection-local,
   append-only `{collection-name}-actions-log.jsonl`.
4. Undo appends history. It does not erase the log or prior run records.
5. Preflight and identity checks abort safely when later changes make an older
   action impossible to reverse exactly.
6. All content processing stays local. There is no telemetry, cloud service,
   hosted AI, or automatic download behavior.
7. Persistent logs require an explicit `--log-file` path.
8. Python dependencies belong in `pyproject.toml`; uv owns the lockfile and
   development `.venv`.
9. Collection folders follow the four-character `pics`, `vids`, and `dups`
   convention.
10. Repository text and tests use generic synthetic collections only.
11. Shared packaged policy provides ignore, classification, renaming,
    image-inspection, and video-timeout defaults. Custom arrays may extend but
    not disable packaged lists.
12. Ignored path names remain private by default and under `--verbose`. Only
    explicit `--show-ignored` may list deterministic collection-relative paths.
13. Supported behavior is not removed in a patch release. The compatibility
    interfaces deprecated throughout v0.1 were removed at the v0.2 boundary.
14. `scan` never writes media, action history, or cache state. Exact-video
    previews may persist disposable fingerprints by default so later preview
    or apply runs resume; `--no-cache` disables both cache reads and writes.
15. Every durable decision has one numbered ADR. Ruff, Black, mypy, pre-commit,
    the complete pytest suite, and a package build are release gates.
16. File moves are descriptor-relative and atomically refuse occupied targets.
    A media collection must not span filesystems when files need to move.
17. Exact duplicate conclusions are valid only while the analyzed regular-file
    state is unchanged; retained originals stay checked through commit.
18. Invalid derived cache data stops early and is never automatically deleted
    or replaced.
19. Scan facts must come from stable file state; changed files are omitted and
    counted without revealing paths.
20. Ctrl-C returns status 130 and human-readable commands report their observed
    runtime even when interrupted or stopped unexpectedly.
21. Command entry points coordinate explicit, independently testable stages;
    image and video content definitions remain separate despite shared layout
    and collision utilities.
22. Release coverage includes child-process CLI execution and complements,
    rather than replaces, real integration and adversarial behavior tests.
23. Validation is report-only and independent of organized layout. Repair or
    quarantine requires a future ADR and reversible mutation design.
24. Validation filenames are private unless `--show-files` is explicit; health
    errors return 1, warnings-only reports return 0, and setup errors return 2.

`{collection-name}-actions-log.jsonl` remains the authoritative portable
journal because it moves naturally with a media-collection on external storage.
SQLite is useful only as a derived, disposable collection-local cache or index.

## Current package layout

```text
python-media-organizer/
  pyproject.toml
  .pre-commit-config.yaml
  CODE_REVIEW.md
  README.md
  RESEARCH_IMPROVEMENTS.md
  AGENTS.md
  HANDOFF.md
  adrs/
  src/pymo/
    __init__.py
    __main__.py
    cli.py
    collection.py
    config.py
    default_config.toml
    logging_config.py
    progress.py
    file_safety.py
    action_log.py
    organize.py
    rename.py
    scan.py
    validate.py
    duplicates/
      common.py
      images.py
      videos.py
  tests/
```

The CLI subcommands are:

```text
pymo organize COLLECTION
pymo rename COLLECTION
pymo scan COLLECTION
pymo validate COLLECTION
pymo find-image-duplicates COLLECTION
pymo find-video-duplicates COLLECTION
```

The four mutating tools support dry-run/apply behavior and `--undo`, which is
also a preview unless combined with `--apply`. `scan` and `validate` are
read-only. Global
`--verbose`, `--quiet`,
`--log-file PATH`, `--timestamps`, `--config PATH`, and `--show-ignored`
options go before the subcommand. `--show-ignored` and command-specific options are also accepted by
the selected command after its collection argument.

## Shared configuration and collection layout

`src/pymo/default_config.toml` is packaged read-only data, loaded for every
forward command. It contains the default ignore patterns, classification
extensions and MIME policies, rename noise tokens, image-inspection
extensions, video decode timeout, scan worker count, and progress interval.
Collection
or explicit custom arrays
extend packaged arrays; they cannot remove safety defaults. A custom video
timeout overrides the packaged value, while `--decode-timeout` has final
command-line precedence.

`src/pymo/config.py` validates schema version 1 into frozen, typed policy
objects. A collection-root `.pymo.toml` extends packaged policy automatically.
`--config PATH` selects a different custom extension file for that command.
Ignore patterns match case-insensitive basenames or collection-relative paths,
and an ignored directory protects all descendants.

`src/pymo/collection.py` owns the invariant paths for `pics`, `vids`, `dups`,
the optional config, disposable video cache, and collection-named action log.
These names are intentionally not configurable because cross-tool ownership,
portable undo, and compatibility require one interpretation.

Ignored paths are excluded from moving, renaming, media classification,
fingerprinting, deletion, and action history. Symbolic links remain a separate
safety condition and are never made acceptable by an ignore rule. The
organizer may leave a source directory that still contains ignored metadata;
verification treats such a metadata-only tree as intentionally preserved.
Malformed, unknown, absolute, or parent-traversing configuration stops before
mutation. Undo remains action-driven and does not reinterpret historical
operations through current ignore settings.

All forward commands report the number of ignored entry points without naming
them. `--verbose` does not relax that privacy default. Explicit
`--show-ignored` adds a sorted collection-relative list without printing the
absolute collection root. If the user also requests `--log-file`, those listed
paths are deliberately included in that log.

The source contains only four assigned module constants: the config schema,
action-log schema, video fingerprint algorithm, and scan-report schema
versions. Each is an
on-disk compatibility boundary and has an adjacent justification. Dispatch,
logging, collection paths, tool identifiers, operation identifiers, timestamp
patterns, and policy collections no longer use scattered mutable globals.

## Shared action log

`src/pymo/action_log.py` stores one `{collection-name}-actions-log.jsonl` in
each media-collection.

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

Version 0.2.0 removed CSV organizer undo and `--manifest`, grouped image-output
migration and its options, the image finder's no-op `--recursive` option, and
fixed-name `media_actions.jsonl` detection. Users needing one of those v0.1
interfaces must use version 0.1.5 to finish the migration or undo before
upgrading. New work uses collection-named JSONL and creates none of the removed
CSV or grouped artifacts.

Do not treat current action-log schema version 1, persisted tool/action IDs, or
the human-readable “Group” report label as legacy. Current logs depend on those
identifiers, and report grouping does not create `group_*` directories.

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

Every inspected video carries a stable device/inode/size/time snapshot. The
finder checks it after hashing and probing, around fingerprint decoding, before
grouping, and during applied moves. The image finder uses the same contract for
displayed-pixel hashes and retained originals. A changed file is skipped or
stops an apply rather than reusing a stale exact-match conclusion.

FFmpeg input protocols are restricted to `file,pipe`, and tests assert that
decode commands contain no macOS, Windows, or X11 capture input. The tool does
not need Screen & System Audio Recording, Camera, or Microphone permission.

Preview and applied runs use collection-root `.pymo.sqlite3`. It is a derived
cache keyed by content SHA-256, fingerprint algorithm version, and actual
FFmpeg version. Each successful cache miss is persisted immediately so an
interrupted preview retains completed work and a later `--apply` reuses it.
`--no-cache` disables all cache reads and writes.
SQLite uses a non-persistent journaling mode and connections close explicitly,
so `-wal`/`-shm` sidecars are not left behind.
Existing cache schemas and rows are validated read-only before decoding. An
invalid cache is preserved and reported; moving it aside or explicitly using
`--no-cache` is the recovery path. FFmpeg is resolved only when discovery finds
at least two eligible videos.

The finder mirrors image behavior for deterministic keeper choice, readable
`copy(n)` destinations, no overwrite/delete, action-log undo, post-operation
verification, and retained/duplicate/reclaimable storage reporting.

Full FFmpeg fingerprint decoding remains sequential. FFmpeg already performs
internal threading, and parallel decode processes can contend for disk and CPU,
especially on external media. Add bounded process-level decoding only after
representative benchmarks demonstrate a reliable benefit.

The finder reports uncached candidate count and bytes before decoding, an
observed aggregate rate and ETA after completed candidates, and a configurable
heartbeat while a single FFmpeg subprocess remains active. These reports do
not include filenames. The default interval is 15 seconds through
`performance.progress_interval_seconds`; accepted values are 1..3600.

## Collection scan

`src/pymo/scan.py` provides the read-only first-run `pymo scan COLLECTION`
report. Its fast profile inventories files, storage, extensions and detected
content types; reports layout and canonical-name readiness; summarizes review
storage and same-size duplicate potential; estimates checksum and exact-video
work; reports existing local pymo state; and recommends next commands.

`--checksums` hashes only same-size picture and video candidates and reports
exact-byte copies. It does not substitute for displayed-pixel image or decoded-
playback video matching. `--json` emits stable schema version 1 without the
collection name, root path, or filenames. Relative ignored paths remain opt-in
through `--show-ignored`.

The scan does not create an action log, cache, or other collection state.
Content classification uses a bounded thread pool, defaults to four workers,
is configurable through `performance.scan_workers`, and can be overridden with
`--workers 1..32`. Checksumming is deliberately opt-in; FFmpeg decoding is not
part of scan.

File state is captured at discovery and checked around classification and
checksumming. Detected changes are omitted from inventory and duplicate facts
and reported as an aggregate `changed_entries` count without revealing paths.

## Media validation

`src/pymo/validate.py` implements report-only `pymo validate COLLECTION` over
any collection layout. It never repairs, quarantines, moves, renames, deletes,
caches, or appends action history.

The standard profile uses Pillow integrity verification for supported images
and local ffprobe structure inspection for non-empty videos. `--full` also
loads every image frame and decodes selected video/audio streams completely
through local FFmpeg. Standard validation uses bounded workers; a full run
containing video reports and uses one worker so full FFmpeg decodes remain
sequential.

Text and schema-1 JSON aggregate severity/code findings without collection
names, root paths, or filenames. `--show-files` adds collection-relative
affected paths, while `--show-ignored` remains a separate opt-in. Status 0 means
no error-severity finding, 1 means health errors were reported, and 2 means the
command could not run safely. Animated or multi-page images are counted, not
classified as corrupt. Unsupported recognized formats remain warnings rather
than unverified claims of corruption. Unreadable subtrees are health errors,
native-tool diagnostics are discarded, and concurrent changes supersede
decoder conclusions. Pillow and native tools read inherited stable descriptors,
not a pathname that can be redirected after preflight.

## Logging

`src/pymo/logging_config.py` routes all command output through the standard
library logging package while preserving readable text expected by existing
behavioral tests.

- Default `INFO` messages go to stdout.
- Warnings/errors go to stderr.
- `--verbose` enables diagnostic `DEBUG` output.
- `--quiet` keeps only warnings and errors.
- `--log-file PATH` creates a timestamped local log only at the requested path.
- `--timestamps` prefixes every physical console line with an ISO timestamp.
- Explicit log files timestamp every physical line, including lines contained
  inside one multi-line message.
- `--show-ignored` explicitly adds relative ignored paths; `--verbose` alone
  never reveals them.
- No persistent log is created by default.

Do not put media bytes or unrelated metadata into exceptions or diagnostics.
Scan JSON is the first machine-readable result contract; human command output
continues to use logging. Every normal non-JSON CLI run ends with total elapsed
time. Long stages use `src/pymo/progress.py` for aggregate file/data rates and
observed ETA; no filenames or fabricated reference speeds enter those metrics.

## Dependencies and environment

Python 3.11 or newer is required. Runtime dependency: Pillow. Development
dependency: pytest. Both are declared in `pyproject.toml`, and exact development
resolutions are committed in `uv.lock`.

uv 0.12 or newer manages Python selection, the project `.venv`, dependency
locking, command execution, and builds. Hatchling is the PEP 517 build backend;
hatch-vcs derives PEP 440 package versions from Git tags. The runtime version
comes from installed distribution metadata through `importlib.metadata`.
Neither uv nor Hatch is required to run an already installed wheel.

FFmpeg/ffprobe remain external runtime dependencies to keep native binary
origin, licensing, and updates explicit. The current development machine has a
Homebrew FFmpeg installation available; tests skip real integration cases when
the executables are absent.

Setup and verification:

```bash
uv sync --locked
uv run pymo --version
uv run --locked ruff check src tests
uv run --locked black --check src tests
uv run --locked mypy
uv run --locked pre-commit run --all-files
uv run --locked pytest
uv build
```

## Test coverage state

The suite is entirely synthetic and temporary. Current coverage includes:

- organizer dry run, apply, verification, collisions, nested layouts, content
  classification, symbolic-link safety, empty-directory restoration, reruns,
  removed CSV option refusal, `dups` protection, default OS-metadata ignores,
  custom-directory protection, custom classification extensions, and
  ignored-only source trees;
- renamer parsing and cleanup across varied filename structures, deterministic
  names, configurable additive noise tokens, collisions, apply/undo, and
  `dups` protection;
- action journal ordering, strict lifecycle grammar, no-follow opening,
  descriptor-relative atomic moves, late target collision refusal, interrupted
  run recovery, stable identity calculation, conflict refusal, cross-tool
  dependencies, and ordered undo;
- image exact-pixel equivalence across metadata/format differences, strict
  folder ownership, storage accounting, collisions, removed compatibility-
  option refusal, configurable inspection extensions, dry run/apply/undo, and
  review-tree restoration;
- real FFmpeg byte-copy/remux matches, different-audio and different-timing
  non-matches, corrupt and multi-audio skips, strict ownership, collisions,
  incremental preview cache, interruption recovery, cache opt-out, sidecar
  behavior, cross-tool undo dependencies, missing runtime errors, and local-
  file-only/no-capture command construction;
- unified CLI version, default no-log behavior, explicit logging, verbose mode,
  quiet mode, global option forwarding, default ignored-name privacy, and
  explicit relative ignored-path output;
- command runtime summaries, optional ISO console timestamps, timestamped
  multi-line file logs, deterministic duration/rate/ETA formatting, and
  long-FFmpeg heartbeat behavior;
- typed configuration parsing, immutable/additive defaults, validated media
  extensions, MIME types, noise tokens and timeout, alternate-config
  selection, invalid-schema refusal, and config self-protection;
- centralized collection-path derivation and duplicate-tree recognition;
- fixed-name action-log non-detection and removed v0.1 interface refusal;
- path-private fast and checksum scan reports, stable JSON, bounded worker
  validation, readiness recommendations, and no-write guarantees;
- dynamic package metadata, packaged TOML data, runtime/distribution version
  agreement, and the selected Hatchling plus hatch-vcs configuration.

Run the committed quality gates and complete suite after every change. Release
review also runs subprocess-aware coverage. Do not
replace real FFmpeg integration coverage with mocks alone. `CODE_REVIEW.md`
records the pre-validation findings, their severity, target release, and durable
resolution state; keep it synchronized as each release closes a group.

## Research and roadmap

`RESEARCH_IMPROVEMENTS.md` is the durable research notebook. It records the
assessment of Home Media Organizer, PyPipeline, Czkawka, Video Duplicate Finder,
digiKam, organize, Phockup, dupeGuru, and related design ideas. It also defines
privacy constraints, licensing cautions, validation, metadata, comparison,
local indexing, keeper scoring, similarity levels, and local-AI rules.

Near-term roadmap:

1. Adversarially review validation and resolve findings in approved 0.3.x tags.
2. Add metadata inspection/export and confidence-based date provenance.
3. Add read-only collection/backup comparison.
4. Expand the disposable SQLite index for local statistics and fingerprints.
5. Add perceptual similarity as report-only functionality.
6. Revisit optional local AI suggestions after deterministic tooling matures.

`scan` is implemented; do not rename it to `inspect`.

## Git policy

This project uses concise one-line commits authored as `nachiketbhujbal` with
the account-specific GitHub no-reply address. `origin` is the approved personal
repository at `git@github.com:nachiketbhujbal/python-media-organizer.git`, using
a repository-specific deploy key. Push commits or release tags only when the
user explicitly approves that release. Confirm private collection data and
generated state are absent before every commit.
