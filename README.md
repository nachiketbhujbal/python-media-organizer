# python-media-organizer

`python-media-organizer` is a local-first, reversible toolkit for organizing
personal media collections. Its command is `pymo`.

The project defaults to previews, never deletes media, never overwrites an
existing file, and does not include telemetry, cloud services, hosted AI, or
automatic uploads. Every applied file operation is recorded in the collection
it belongs to.

The broader product goal is safe media preservation during collection moves
between local storage devices. Organization, deterministic naming, validation,
and duplicate isolation are steps toward proving that readable source content
remains represented after paths change and redundant copies are reviewed. The
current release does not copy drives or certify a migration; a directional,
read-only migration-verification command is promoted in the roadmap ahead of
optional metadata, similarity, and local-AI features.

pymo is not a failing-drive recovery utility. Do not postpone making a
recovery-grade copy of readable data while waiting for a future pymo release.
Use pymo on a healthy working copy; retain an unchanged baseline until the
planned verification workflow—or an independently trusted equivalent—accounts
for the source content.

Mutation planning and undo require complete filesystem enumeration plus
successful no-follow metadata inspection of every returned name. If a
directory or enumerated entry cannot be read completely, pymo stops before
creating action state or moving media; report-only scan and validation instead
preserve the problem as a visible health finding while continuing over readable
neighbors.

## Requirements and installation

- Python 3.11 or newer
- macOS, Debian-family or Red Hat-family Linux, or Linux running under WSL;
  the current append-only journal uses POSIX file locking
- uv 0.12 or newer for the reproducible development workflow
- Pillow, installed from `pyproject.toml`
- FFmpeg and ffprobe for exact video duplicate detection
- pytest only for development and testing

On macOS, FFmpeg can be installed with Homebrew:

```bash
brew install ffmpeg
brew install uv
```

Clone the repository, then create the locked development environment and run
the command:

```bash
uv sync --locked
uv run pymo --version
```

uv creates and maintains the project `.venv` automatically. To install a
snapshot of the command outside the development environment, run
`uv tool install .` from the repository. The package is not published to PyPI
yet. Standard tools remain compatible: `python -m pip install .` installs a
local checkout because the build metadata follows PyPA standards.

FFmpeg is intentionally an explicit system dependency. A Python wrapper would
still require a native binary while making its provenance and updates less
clear.

## Collection layout

The current convention uses four-character folder names:

```text
media-collection/
  pics/                 organized pictures
  vids/                 organized videos
  dups/
    pics/               exact picture copies isolated for review
    vids/               exact video copies isolated for review
  media-collection-actions-log.jsonl
                        portable append-only action history, after an apply
  .pymo.toml            optional collection-specific configuration
  .pymo.sqlite3         disposable shared derived-data cache, after persisted evidence
  .pymo.sqlite3.lock    persistent cache reader/writer coordination
  other files           non-media files at the collection root
```

The two duplicate finders have strict ownership. The image finder reads only
`pics` and writes only `dups/pics`; it does not require or touch the video
folders. The video finder reads only `vids` and writes only `dups/vids`; it does
not require or touch the picture folders.

## Configuration and ignored metadata

Every forward command uses the same local-only TOML configuration system.
Packaged defaults automatically ignore common operating-system and tool state,
including macOS `.DS_Store` and AppleDouble files, Windows thumbnail and
desktop metadata, recycle/index directories, Synology and archive metadata,
version-control directories, the optional pymo config, and pymo's disposable
SQLite cache, lock, and private staging artifacts. These paths are left exactly
where they are: they are not moved, renamed, fingerprinted, deleted, or written
to the action log.

The built-in rules are always active and require no file in a collection. To
extend them for one collection, add `.pymo.toml` at its root:

```toml
version = 1

[ignore]
files = ["*.tmp", "incoming/*.sidecar"]
directories = ["archive", "exports"]

[classification]
image_extensions = [".garden"]
video_extensions = [".city"]
video_application_mime_types = ["application/x-city"]
generic_mime_types = ["application/x-generic"]

[rename]
noise_tokens = ["planter"]

[image_duplicates]
extensions = [".flower"]

[video_duplicates]
decode_timeout_seconds = 3600

[performance]
scan_workers = 4
progress_interval_seconds = 15
cache_publication_batch_size = 32
```

Patterns are case-insensitive and match either a basename or a path relative
to the collection. An ignored directory protects its whole subtree. pymo
reports how many file or directory entry points it ignored without listing
private names by default.

To review exactly which paths were ignored, opt in explicitly:

```bash
pymo --show-ignored organize "/path/to/media-collection"
pymo find-image-duplicates "/path/to/media-collection" --show-ignored
```

The list is deterministic and relative to the media-collection root, so it
does not expose the root's absolute location. `--verbose` alone does not reveal
ignored names. Combining `--show-ignored` with `--log-file` intentionally
records those displayed relative paths in the requested log.

Custom arrays extend rather than replace packaged defaults. Classification
extensions are conservative filename fallbacks when content detection is
generic or unknown. Image-duplicate extensions select files for Pillow to
inspect; unreadable formats are still skipped. Rename noise tokens remove
additional unhelpful filename words. A command-line `--decode-timeout` takes
precedence over the configured video timeout. `scan_workers` controls bounded
parallel content classification for `pymo scan`; it must be between 1 and 32,
and `--workers` overrides it for one scan. `progress_interval_seconds` controls
periodic status and long-operation heartbeat cadence from 1 to 3600 seconds.
`cache_publication_batch_size` controls how many new file observations are
merged into each durable atomic cache publication; it must be between 1 and
1000.

An alternate extension file can be selected for one command:

```bash
pymo --config "/path/to/settings.toml" organize "/path/to/media-collection"
```

`--config` replaces the collection's optional `.pymo.toml` for that command;
both choices extend the packaged safety defaults rather than disabling them.
Invalid or unsafe configuration stops the command before mutation. Undo uses
the recorded action history and does not reinterpret older actions through the
current ignore rules.

The fixed `pics`, `vids`, and `dups` ownership structure, action-log naming,
config filename, and cache filename are deliberately not configurable. They
are centralized package invariants so every command and existing action log
agrees on the same collection layout.

## Commands

Every mutating command is a dry run unless `--apply` is present. Review the
preview before applying the same command. Every normal command ends with its
total elapsed time, and every physical line of that human-readable output has
an ISO timestamp by default. Long processing stages also report completed
files, bytes where meaningful, observed rates, and an ETA once enough work has
completed to calculate one honestly. ETA projection begins after three
completed observations. Completed-work rows use ten evenly spaced count
milestones, genuinely due time reports, and one final row instead of printing
after every item.

Ctrl-C reports the interruption, observed runtime, and conventional exit status
130 without claiming success. An unexpected error emits a stopped-runtime line
before its diagnostic propagates. Quiet output and machine-readable JSON remain
free of these human-facing records.

### Scan a collection

```bash
pymo scan "/path/to/media-collection"
pymo scan "/path/to/media-collection" --checksums
pymo scan "/path/to/media-collection" --checksums \
  --cache "/path/to/cache.sqlite3"
pymo scan "/path/to/media-collection" --json
pymo scan "/path/to/media-collection" --workers 1
```

`scan` is the recommended first command. It is read-only: it never moves or
renames media, creates an action log, or writes the fingerprint cache. The fast
profile reports aggregate inventory and storage by kind, extension, and
detected content type; layout and naming readiness; review-copy storage;
same-size duplicate candidates; estimated expensive work; existing local pymo
state; and recommended next steps.

Recommendations form an ordered plan rather than only naming the next command.
`scan` recommends report-only `validate` before any mutating command. When
layout and filenames both need work, it then recommends `organize` before
`rename`, followed by the applicable exact-duplicate finders.

Same-size candidates are only an upper bound, not duplicate proof.
`--checksums` additionally hashes those candidates to report exact-byte copies
without performing displayed-pixel or decoded-playback comparison. Use the two
dedicated duplicate finders for those stronger definitions. A checksum scan
may reuse whole-file hashes recorded for the exact current file state in the
collection cache or an explicit `--cache PATH`; it reports reused and computed
hash counts but never creates or updates a cache or lock. `--json` emits the
complete stable schema without the collection name, root path, or filenames;
ignored relative paths appear only with the explicit `--show-ignored` opt-in.
The default four classification workers can improve scans on mixed collections
without launching concurrent FFmpeg decodes.

Discovery, classification, and checksumming use stable regular-file snapshots.
If a file changes during the run, it is omitted instead of combining old and
new facts. Text and JSON reports include an aggregate `changed_entries` count
and path-private warning; rerun after other writers become idle for a complete
snapshot. Directory traversal failures are counted and warned about rather than
silently omitted; run `validate --show-files` when collection-relative finding
paths are needed.

### Inspect the derived cache

```bash
pymo cache status "/path/to/media-collection"
pymo cache status "/path/to/media-collection" --json
pymo cache status "/path/to/media-collection" --cache "/path/to/cache.sqlite3"
```

`cache status` is a strictly read-only snapshot. It does not create a cache,
lock, sidecar, directory, action record, or media state. A missing cache is an
ordinary status with exit 0. A healthy current or legacy cache also returns 0;
an unsafe, unreadable, corrupt, malformed, or incompatible cache returns 1,
and invalid command setup returns 2.

The report includes cache format and storage, evidence records by type and
namespace, current versus stale algorithms, file-observation freshness, and
evidence linkage to recorded observations. It validates known exact-video,
displayed-pixel, and normalized ffprobe payloads but deliberately does not
invoke media libraries or native tools to decide runtime reuse; the consuming
duplicate finder remains authoritative for actual reusable records.
Legacy video caches are reported with migration pending and remain unchanged.

The default is the collection-local `.pymo.sqlite3`. `--cache` can inspect a
derived database stored elsewhere without writing into either location; it
does not configure another command to write externally. Cache and observation
paths are opened through no-follow descriptors, and a concurrent cache
replacement invalidates the snapshot. Human and schema-1 JSON output omit the
collection root, cache path, filenames, scopes, hashes, algorithms, and runtime
strings.

### Warm exact-video cache evidence

```bash
pymo cache warm videos "/path/to/media-collection"
pymo cache warm videos "/path/to/media-collection" \
  --cache "/path/to/writable-cache.sqlite3"
pymo cache warm videos "/path/to/media-collection" --show-files
```

Cache warming hashes, structurally probes, and fingerprints every safely
discovered video directly inside `vids`; it does not perform duplicate
grouping. Whole-file observations and normalized probes are published together
in bounded atomic batches, while successful fingerprints remain incremental,
so interruption or later collection growth does not discard completed work. A
later video duplicate dry run or apply reuses probes matching the content hash,
probe algorithm, and exact ffprobe runtime, then reuses fingerprints matching
the exact-playback algorithm and FFmpeg runtime.

The command never moves media, creates `dups`, or appends action history. Its
default cache and lock are collection-local. `--cache` instead writes the
database and sibling lock in an existing external directory, allowing the
media collection itself to remain read-only. Normal output is aggregate and
path-private; `--show-files` explicitly lists collection-relative paths that
could not be represented. Exit 0 means every discovered video byte stream was
represented, exit 1 means coverage was incomplete or the cache was unsafe, and
exit 2 means setup was invalid. Run `scan` and `validate` separately because a
successful warm is not a collection-health or preservation verdict.

### Validate collection health

```bash
pymo validate "/path/to/media-collection"
pymo validate "/path/to/media-collection" --full
pymo validate "/path/to/media-collection" --json
pymo validate "/path/to/media-collection" --show-files
```

`validate` recursively checks media in any collection layout and never moves,
deletes, repairs, quarantines, renames, caches, or action-logs a file. The
standard profile uses Pillow integrity verification for supported images and
local ffprobe structure checks for videos. `--full` additionally loads every
image frame and completely decodes video/audio streams through local FFmpeg.

Reports cover empty and invalid media, unreadable or changing entries,
extension/content mismatches, unsupported recognized image formats, video
stream layouts, missing codec names or dimensions, extra streams, and
missing/invalid duration. Unreadable subtrees make the report unhealthy rather
than being silently omitted. A damaged file becomes a finding without aborting
validation of its healthy neighbors. Unsupported media remains explicitly
unverified and visible as a warning; pymo never converts a health finding into
an ignore rule. Animated and multi-page images are counted as valid
characteristics rather than corruption.

Classification and decoding use stable, no-follow file descriptors anchored
beneath the resolved collection root. If a file or parent path is replaced
during validation, the decoder remains pinned to the original file and the
result is reported as changed so the user can rerun safely.

Collection roots and filenames are hidden by default. `--show-files` adds
collection-relative affected paths; `--show-ignored` controls ignored paths
separately. JSON uses stable schema version 1 without collection names or
roots. Native video diagnostics are not copied into reports. Exit status is 0
when no errors are found, 1 when validation reports errors, and 2 when the
command cannot run safely. Warnings alone return 0. Standard validation uses
bounded workers; full validation containing video uses one worker to avoid
unmeasured competing FFmpeg decodes.

### Organize a collection

```bash
pymo organize "/path/to/media-collection"
pymo organize "/path/to/media-collection" --apply
pymo organize "/path/to/media-collection" --undo
pymo organize "/path/to/media-collection" --undo --apply
```

`organize` recursively flattens pictures into `pics`, videos into `vids`, and
other files into the collection root. It detects supported content signatures,
fixes media already in the wrong destination, resolves name collisions, removes
only source directories that became empty, protects the entire `dups` review
tree, and verifies the resulting layout.

### Rename media predictably

```bash
pymo rename "/path/to/media-collection"
pymo rename "/path/to/media-collection" --apply
pymo rename "/path/to/media-collection" --undo
pymo rename "/path/to/media-collection" --undo --apply
```

`rename` creates deterministic names from the collection name, media kind, a
stable sequence, a trustworthy embedded or filename timestamp when available,
and useful filename words. It uses `undated` rather than inventing dates,
leaves non-media and already canonical names alone, and excludes `dups`.

It does not claim to understand the visual content. Local AI-assisted naming is
a possible future, opt-in feature.

### Find exact image duplicates

```bash
pymo find-image-duplicates "/path/to/media-collection"
pymo find-image-duplicates "/path/to/media-collection" --summary
pymo find-image-duplicates "/path/to/media-collection" \
  --cache "/path/to/writable-cache.sqlite3"
pymo find-image-duplicates "/path/to/media-collection" --no-cache
pymo find-image-duplicates "/path/to/media-collection" --apply
pymo find-image-duplicates "/path/to/media-collection" --undo
pymo find-image-duplicates "/path/to/media-collection" --undo --apply
```

The image finder applies EXIF orientation, decodes to RGBA, and matches exact
displayed pixels while ignoring filenames and metadata. It keeps one original
using deterministic rules and moves extra copies into flat `dups/pics` names
such as `original_copy(1).jpg`. Animated, multi-page, unreadable, and unsafe
inputs are skipped conservatively. Pillow reads each candidate through a stable
no-follow descriptor anchored beneath the collection root, so a concurrent
pathname or parent-directory swap cannot redirect pixel decoding to unrelated
local content. Changed paths are reported and skipped.

By default, the finder stores whole-file observations and displayed-pixel
fingerprints in the shared collection cache. Reuse requires the same content
SHA-256, pixel-normalization algorithm, and exact Pillow runtime. A newly added
path can reuse known pixels only after its bytes hash to known content. Hash
observations and new pixel evidence publish together in bounded atomic batches;
output reports actual reused, computed, and persisted counts without exposing
paths. `--cache PATH` selects an external writable cache and `--no-cache`
disables both reads and writes. Before an applied move can depend on a cached
hash, pymo re-reads and recomputes that file through its stable descriptor.

### Find exact video duplicates

```bash
pymo find-video-duplicates "/path/to/media-collection"
pymo find-video-duplicates "/path/to/media-collection" --summary
pymo find-video-duplicates "/path/to/media-collection" \
  --cache "/path/to/writable-cache.sqlite3"
pymo find-video-duplicates "/path/to/media-collection" --apply
pymo find-video-duplicates "/path/to/media-collection" --undo
pymo find-video-duplicates "/path/to/media-collection" --undo --apply
```

The video finder first hashes complete files, then uses ffprobe and streamed
FFmpeg decoding for plausible candidates. A strict duplicate must have the same
displayed frames, normalized frame timing, orientation, decoded audio, audio
timing, and supported stream structure. A remux can match; different audio,
different playback timing, recompression, cropping, shortening, and watermarks
do not.

Ambiguous or insufficiently tested inputs are reported and left untouched,
including corrupt files, multiple video or audio streams, attachments,
subtitles/data streams, and HDR or high-bit-depth video. Decode commands are
restricted to local file inputs and streamed output; they do not request a
camera, screen, microphone, or network source.

Classification, whole-file hashing, ffprobe, and both FFmpeg decode passes read
one stable no-follow file descriptor anchored beneath the collection root.
Native tools receive only an inherited `/dev/fd` input, so a concurrent
pathname or parent-directory swap cannot redirect analysis to unrelated local
content. A changed pathname is still reported and skipped.

Exact image and video results are bound to the regular file's device, inode,
size, modification time, and change time. A file that changes during analysis
is skipped. Applied runs revalidate every duplicate group and continue checking
retained originals through the action-log commit, stopping safely on stale
state. Pillow decompression-bomb inputs and malformed ffprobe values are also
conservative skips.

Preview and applied runs use `.pymo.sqlite3`, a disposable collection-local
shared cache. Schema version 1 stores generic evidence by content SHA-256,
evidence type, algorithm version, and runtime version, plus stable file
observations with optional whole-file hashes. An observation is reusable only
when its collection identity, relative path, device, inode, size, modification
time, and change time all match. Exact-video fingerprints and normalized
ffprobe structure are supported evidence types. Each newly decoded fingerprint
is saved immediately; new hash observations and probes are published together
in bounded atomic batches, so an interrupted preview can resume and the later
`--apply` usually reuses the reviewed work. The command reports
candidate-relevant reusable records, hashes and fingerprints still required,
actual probe reuse and computation, and the number of new records durably
persisted. Any reused hash that contributes to an applied result is recomputed
before pymo creates duplicate directories, action history, or moves.
Add `--no-cache` for a run that neither reads nor writes the cache; that mode
emits no lookup or update claim. Cache writes are derived local state only:
they never move media or write action history.

Use `--cache PATH` to read and update an explicitly selected external cache and
its sibling lock instead of placing derived state in the collection. This is
the same external-cache contract used by `cache warm videos`. `--cache` and
`--no-cache` cannot be combined.

An existing cache is opened read-only through a stable no-follow descriptor
anchored beneath the collection root, then its exact schema, integrity, and
every row are validated before expensive decoding. A concurrent pathname swap
cannot redirect SQLite to unrelated local data and instead stops the run. If
the cache is corrupt or incompatible, pymo leaves it untouched and stops with
instructions to move it aside or rerun with `--no-cache`.

Valid caches from the earlier video-only schema remain byte-for-byte unchanged
during lookup. The next successful fingerprint write migrates their completed
records only inside the private staged replacement, so a failed migration
leaves the public legacy cache intact.

Readers share `.pymo.sqlite3.lock`; writers take it exclusively and merge the
latest completed records. Concurrent first-time writers safely create or open
one direct-child lock before serializing. A write is first built in memory,
serialized to a
private collection-anchored staging descriptor, synced, reopened read-only, and
validated. Only then does pymo publish it with an atomic no-replace rename or a
verified atomic exchange and sync the collection directory. The public cache
is never modified in place. An interruption therefore leaves either the prior
cache or the complete replacement public; an unpublished `.pymo.sqlite3.new.*`
artifact may remain for inspection and is ignored by every forward command.
These cache-state operations never delete media or write action history.

FFmpeg and ffprobe are resolved only when at least two eligible videos exist;
smaller collections do not need a decoder to report that no comparison is
possible.

Before candidate fingerprinting begins, the finder reports the number and total
size of fingerprints it must calculate. It reports observed progress and data
rate at stable count milestones or when the configured interval is due,
estimates remaining time from completed work, and emits a periodic heartbeat
while one FFmpeg decode is still running. Heartbeats report only the active
item, completed count, and elapsed time; they do not repeat a stale rate or
ETA. ETA begins only after three candidates complete. These figures describe
the current machine and storage device; pymo does not invent a universal
decode speed.

The command also reports independent path-private durations for discovery,
probing, fingerprinting, and planning. An applied run reports apply and
verification timing only when duplicate moves execute. These stage records
complement the final whole-command runtime and make it easier to identify the
expensive part of a run without exposing filenames.

Both duplicate finders report retained storage, extra-copy storage, and the
space potentially reclaimable if the isolated copies are later deleted
manually. `pymo` itself never deletes them.

Add command-specific `--summary` to either duplicate finder for an aggregate,
path-private report. It keeps progress, counts, storage, cache and timing facts,
final results, dry-run guidance, and verification status while suppressing
collection paths, filenames, run IDs, group/action listings, per-video start
rows, and per-file skip details. It works for forward scans, explicit applies,
and undo previews, but cannot be combined with `--show-ignored`. Summary mode
changes reporting only; every analysis, collision, action-log, and verification
check still runs.

## Recommended workflow

For a mixed collection, preview and then apply:

```bash
pymo scan "/path/to/media-collection"
pymo validate "/path/to/media-collection"
pymo organize "/path/to/media-collection" --apply
pymo rename "/path/to/media-collection" --apply
pymo find-image-duplicates "/path/to/media-collection" --apply
pymo find-video-duplicates "/path/to/media-collection" --apply
```

Resolve or consciously account for validation errors before applying changes;
use `validate --full` when complete local decoding is warranted. Image and
video duplicate scans are independent and may run in either order. Undo
dependent changes in reverse order. The action log refuses an earlier undo when
a later active operation touched the same files or paths.

## Action history and undo

Each media-collection owns one append-only
`{collection-name}-actions-log.jsonl`. Records use paths relative to the
media-collection so it and its history can move together.
Applied operations record planned and completed actions, file identities, run
boundaries, and successful undos. Undo appends new history; it never erases the
audit trail.

Before changing anything, undo verifies all expected paths and identities. A
missing, changed, renamed, or occupied path stops the operation safely. This is
why a rename must be undone before undoing an earlier organizer run that moved
the same files.

Journal records are parsed as a strict lifecycle: malformed, unknown,
duplicated, out-of-order, or inconsistent events stop all mutation and undo.
File moves use platform-native atomic no-replace operations through no-follow
directory handles, then verify the recorded content identity. pymo refuses a
cross-filesystem move because copy-and-unlink cannot provide the same atomic
collision and crash guarantees; keep one collection on one filesystem.

## Version 0.2 compatibility boundary

Version 0.2 removes the interfaces deprecated in v0.1.5: CSV organization
manifest undo, grouped image-output migration, the image finder's no-op
`--recursive` option, and automatic detection of fixed-name
`media_actions.jsonl`. A collection that still depends on one of those old
artifacts should use version 0.1.5 to complete the relevant undo or migration
before upgrading. Current collection-named action logs, their schema, and
persisted tool/action identifiers remain supported. Duplicate reports may
still label matching sets as “Group”; that is only a report label.

## Logging

Normal output uses Python's logging system while remaining friendly in a
terminal:

```bash
pymo --verbose organize "/path/to/media-collection"
pymo --quiet organize "/path/to/media-collection"
pymo --no-timestamps organize "/path/to/media-collection"
pymo --timestamps find-video-duplicates "/path/to/media-collection"
pymo --log-file "/path/to/pymo.log" organize "/path/to/media-collection"
pymo --show-ignored organize "/path/to/media-collection"
```

Persistent logs are opt-in because paths and filenames can be private. No log
file is created by default. Global logging options go before the subcommand.
Normal human-readable command logging prefixes every physical console line
with an ISO timestamp. Use `--no-timestamps` for plain console output;
`--timestamps` remains accepted for compatibility and for callers that want to
state the default explicitly. Structured `scan --json`, `validate --json`, and
`cache status --json` results remain clean JSON regardless of either flag.
Help, version, and argument-parser output also remain unprefixed. Explicit log
files always
include ISO timestamps, levels, and logger names on every line regardless of
the console choice.
`--show-ignored` is a separate privacy opt-in and may appear globally or after
the subcommand's collection argument.

## Tests

```bash
uv run --locked pytest
uv run --locked pytest --cov=pymo --cov-report=term-missing
uv run --locked ruff check src tests
uv run --locked black --check src tests
uv run --locked mypy
uv run --locked pre-commit run --all-files
uv build
```

Install the local commit gate once per clone with
`uv run --locked pre-commit install`. It blocks commits on basic file hygiene,
Ruff linting, Black formatting, and mypy typing. The complete pytest suite and
build remain release gates so normal commits do not repeatedly run FFmpeg
integration tests. Development-tool versions are resolved in `uv.lock`.
Coverage is configured to include the real child-process CLI tests; the normal
test command stays fast, while the coverage form is a release review gate.
GitHub Actions runs the same locked quality, coverage, native-FFmpeg, and build
gate automatically for pull requests targeting `main` and pushes to `main`.
Ordinary branch pushes and release tags do not repeat the matrix while the
repository is private; manual dispatch remains available when an additional
remote run is warranted. See
[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for the branch and release
workflow. GitHub Free does not offer server-side protection for private
repositories, so the planned no-force-push, no-deletion, PR, status-check, and
conversation-resolution rules remain procedural until the account gains Pro or
the repository becomes public; ADR 0046 records the activation design.

The suite uses temporary synthetic collections and tiny locally generated video
fixtures. It covers dry runs, apply, undo, collision refusal, action ordering,
content changes, strict folder ownership, exact image and video matching,
different audio and timing, corrupt/ambiguous media, derived cache behavior,
incremental cache recovery, cache opt-out, zero-write cache status, cache
health/coverage JSON, exact-state whole-file hash reuse, cached-hash mutation
rechecks, concurrent first-lock creation, scan reports and JSON stability,
bounded scan workers, removed v0.1 interfaces,
elapsed-time summaries, default and opt-out console timestamps, timestamped
multi-line logs, observed throughput and ETA reporting, FFmpeg heartbeats,
shared built-in and custom policy, malformed-config refusal, centralized
collection paths, default ignored-name privacy, explicit relative ignored-path
output, logging privacy, report-only standard/full validation, validation JSON
privacy and health exit codes, and the guarantee that video decoding never
invokes capture devices. Private collections and their names are not fixtures
or repository content.

## Versions and releases

Git tags are the authoritative release version. Hatchling builds the package,
and hatch-vcs derives the Python package version from tags such as `v0.2.0`;
there is no second version string to update by hand. Untagged development
commits receive a PEP 440 development version containing their Git revision.
uv manages the environment and `uv.lock`, while ordinary standards-compatible
installers can still build and install the package.

## Roadmap and research

`pymo scan COLLECTION` provides the fast local overview and recommends
`pymo validate COLLECTION` before mutation. Version 0.4 begins with
corruption-tolerant discovery and then builds the shared cache foundation,
followed by directional migration verification. Corrupt, unreadable, changing,
unsupported, and mismatched media remain visible findings rather than automatic
ignore rules. Richer metadata and similarity tooling remain later roadmap or
research work. Full video decoding remains sequential until representative
benchmarks show that bounded process concurrency improves real external-drive
workloads without increasing contention or reducing safety.

See the [documentation index](docs/README.md) for the release
[roadmap](docs/ROADMAP.md), [research notebook](docs/RESEARCH.md),
[changelog](docs/CHANGELOG.md), [package architecture](docs/ARCHITECTURE.md),
[architecture decisions](docs/adr/README.md), and
[adversarial review ledger](docs/CODE_REVIEW.md). `HANDOFF.md` records the
current engineering state and compatibility details.
