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
current release includes a directional, read-only layered preservation verdict
over exact bytes, exact displayed images, and strict decoded video. It does not
copy drives or perform filesystem recovery; optional metadata, similarity, and
local-AI features remain later work.

pymo is not a failing-drive recovery utility. Do not postpone making a
recovery-grade copy of readable data while waiting for a future pymo release.
Use pymo on a healthy working copy; retain an unchanged baseline until the
complete verification workflow—or an independently trusted equivalent—accounts
for the source content. Version 0.5.3 is the earliest pymo release eligible for
post-transformation human sign-off when its final verdict is complete.

Mutation planning and undo require complete filesystem enumeration plus
successful no-follow metadata inspection of every returned name. If a
directory or enumerated entry cannot be read completely, pymo stops before
creating action state or moving media; non-mutating scan and validation instead
preserve the problem as a visible health finding while continuing over readable
neighbors. Validation may record disposable cache evidence unless `--no-cache`
is explicit, but it never changes media or authoritative action history.

## Requirements and installation

- Python 3.11 or newer
- macOS, Debian-family or Red Hat-family Linux, or Linux running under WSL;
  the current append-only journal uses POSIX file locking
- uv 0.12 or newer for the reproducible development workflow
- Pillow, installed from `pyproject.toml`
- FFmpeg and ffprobe for exact video duplicate detection and migration playback
  evidence
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

Container-family validation policy is packaged and immutable rather than a
collection preference. It covers every packaged video extension; custom video
extensions remain valid classification fallbacks but receive no container-name
accusation because pymo has no reviewed family policy for them.

Truthful-extension correction policy is also packaged and immutable. It maps a
verified Pillow format or confidence-gated ffprobe family to one canonical
extension plus accepted synonyms. Collection configuration cannot add
correction authority. Every packaged image extension and validation video
family must be mapped or explicitly protected. TIFF-derived images, camera raw
extensions, shared MOV/MP4/3GP and Matroska/WebM demuxers, audio-capable
ASF/Ogg/RealMedia families, and raw MPEG elementary streams are protected
because their evidence cannot select one truthful suffix.

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
`scan` recommends fresh `validate` before any mutating command, then
`correct-extensions` for a collection containing media. When layout and
filenames both need work, it then recommends `organize` before `rename`,
followed by the applicable exact-duplicate finders.

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

### Guide one collection migration

Version 0.5.11 coordinates the production runbook for one unchanged baseline
and one working collection without turning it into an unattended batch. With
no log directory it writes nothing and prints the complete plan:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-copy"
```

Select a dedicated private directory outside both collections to opt into
restart state and one log per attempted child stage:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-copy" \
  --log-dir "/path/to/private-logs" --start --no-cache
pymo migrate "/path/to/baseline" "/path/to/working-copy" \
  --log-dir "/path/to/private-logs" --run-next
```

Each invocation runs at most one stage and returns that child command's actual
status. A successful preview advances to a separate apply checkpoint, where
both `--run-next` and `--apply` are required. A status-1 validation result stops
until it is rerun or explicitly acknowledged with `--accept-status`; other
failures cannot be waived. At the duplicate-review boundary, pymo stops for the
operator to retain the complete `dups` tree outside the working collection.
`--confirm-quarantine` records the human checkpoint only when the working
`dups` path is absent, then fresh final validation and ordinary migration
verification remain pending.

Coordinator setup, unsafe-state, and invocation errors return status 2, keeping
them distinct from a child's status-1 findings. A `--run-next` attempt otherwise
returns the child command's actual status; status 1 from the external-quarantine
confirmation means the working `dups` path is still present.

The schema-1 restart file records canonical roots, the installed pymo version,
fixed common options, attempts, statuses, and private log names. Collection and
log-directory separation is checked by filesystem identity, so aliases on a
case-insensitive or normalizing filesystem cannot collapse the baseline and
working roots or place private logs inside either collection. It is workflow
bookkeeping, not action history or preservation evidence. It cannot create the
baseline or working copy, move quarantine, rescue-copy, delete, or authorize
discarding any data. See the [production runbook](docs/MIGRATION.md) for the
complete procedure and option examples.

### Verify a migration by exact bytes and media content

```bash
pymo verify-migration "/path/to/baseline" "/path/to/working-copy"
pymo verify-migration "/path/to/baseline" "/path/to/working-copy" --json
pymo verify-migration "/path/to/baseline" "/path/to/working-copy" --show-files
pymo verify-migration "/path/to/baseline" "/path/to/working-copy" \
  --simulate-without-dups
```

`verify-migration` is directional: every in-scope unique byte stream readable
from `SOURCE` must have an exact SHA-256-and-length representative in
`DESTINATION`. Collection-root names, directory layouts, and filenames are not
identity, so organization and deterministic renaming do not create false
differences. Several byte-identical source copies may be represented by one
destination copy; reduced and added multiplicity are reported separately.
Destination-only content is also reported but does not invalidate source
coverage.

Both trees are enumerated without following symbolic links, then every
in-scope regular file is hashed from a fresh, stable, collection-anchored
descriptor. The command does not accept cached historical hashes as current
preservation proof and writes no cache, lock, configuration, media, duplicate
tree, or action history. Source and destination must be distinct, non-nested
directories.

The byte verdict is `complete` when all in-scope source identities have readable
destination representatives, `incomplete` when complete evidence proves some
are absent, and `unproven` when filesystem traversal, unreadable or changing
source data, unsupported entries, or destination uncertainty prevents that
claim. Ignored entry points and pymo state are counted and explicitly outside
the byte contract.

Version 0.5.1 adds a separate exact-image layer for source byte
identities that are absent from the destination. Eligible still images are
freshly decoded, EXIF-oriented, converted to RGBA, and compared by dimensions
plus every displayed pixel under `displayed-pixels-rgba-v1`. This can account
for a metadata-varied or losslessly re-encoded image without claiming its
original metadata, encoding, container, or file bytes survived. Animated,
multi-page, unsafe, unreadable, changing, unsupported, and merely similar
images never receive an exact-content match. Candidate eligibility uses the
configured exact-image extensions.

The image layer reports `complete`, `incomplete`, `unproven`, or `not-needed`
independently and never rewrites the byte verdict.

Version 0.5.2 adds schema-3 strict decoded-video evidence for byte-missing
source identities with configured video extensions. It freshly normalizes
supported stream structure with ffprobe, then streams complete displayed-frame,
normalized-timing, and decoded-audio fingerprints through local FFmpeg under
`exact-playback-v2`. Supported container remuxes may match; recompression,
different audio or timing, cropping, watermarks, ambiguous streams,
HDR/high-bit-depth inputs, unreadable media, native decode failures, and
concurrent changes do not. A match does not claim the source container,
metadata, codec bitstream, or original file bytes survived.

FFmpeg and ffprobe are resolved only when an eligible byte-missing video needs
comparison. `--ffmpeg PATH`, `--ffprobe PATH`, and `--decode-timeout SECONDS`
provide explicit local overrides. Video decoding remains sequential and fresh;
the verifier neither consumes nor creates cache evidence.

Version 0.5.3 adds schema-4 final preservation accounting. Each unique source
stream is represented once by exact bytes, exact displayed pixels, or strict
decoded playback. The command then freshly re-discovers both declared scopes
and revalidates every hashed file, in-scope directory namespace, unsafe entry
category, and collection-root identity while refreshing exclusion counts. The
final verdict is `complete` only when all
source streams are accounted for and no unreadable, unstable, unsupported, or
incomplete evidence remains. Unknown missing non-media content is
`incomplete`; recognized media without a supported exact evidence path is
`unproven`.

Version 0.5.10 advances JSON reporting to schema 5 and adds the explicit
`--simulate-without-dups` counterfactual. The verifier still freshly hashes the
complete physical destination, inventories the `dups` review tree separately,
then prevents its regular files from satisfying byte, displayed-image, or
decoded-video coverage. Simulated multiplicity and destination-only facts also
exclude those files. Unsafe, unreadable, unstable, ignored, and other excluded
review-tree evidence remains visible rather than being converted into a safe
absence claim, and final stability still revalidates the complete physical
destination namespace.

Every byte, image, video, and final verdict is labeled simulated. A simulated
complete result is only eligible for human quarantine review: it does not move
or delete anything, does not prove the post-quarantine collection, and does not
replace ordinary fresh verification after an external quarantine move.

A complete verdict is eligible for human sign-off, not an instruction to
delete a baseline. It covers stable namespace-visible content inside the two
declared roots and cannot prove orphaned filesystem allocations or whole-drive
recovery.

Normal text and JSON omit both roots and all filenames. `--show-files` exposes
only relative missing, destination-only, and problem paths;
`--show-ignored` separately exposes relative policy exclusions. Exit status 0
means complete layered preservation, 1 means incomplete or unproven, and 2
means invalid setup. Under `--simulate-without-dups`, status 0 means simulated
completion eligible only for human quarantine review; only an observed result
with `eligible-for-human-signoff` can enter final migration sign-off.

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

### Warm derived cache evidence

```bash
pymo cache warm images "/path/to/media-collection"
pymo cache warm videos "/path/to/media-collection"
pymo cache warm all "/path/to/media-collection"
pymo cache warm all "/path/to/media-collection" \
  --cache "/path/to/writable-cache.sqlite3"
pymo cache warm all "/path/to/media-collection" --show-files
```

Image warming hashes and computes displayed-pixel evidence for every safely
discovered file directly inside `pics`. Video warming hashes, structurally
probes, and fingerprints every safely discovered file directly inside `vids`.
`all` performs both. Warming inspects and publishes evidence but never groups
duplicates. Whole-file observations and derived records are published in
bounded atomic batches, so interruption or later collection growth does not
discard completed work. Later duplicate dry runs or applies reuse only evidence
matching its content, algorithm, and exact library or native-tool runtime.

Every selected layout is checked and all selected media is discovered before
cache writes begin. A combined warm also resolves required video tools before
publishing image evidence, preventing an invalid FFmpeg setup from leaving a
partially initialized combined run. `images` does not require `vids` or native
video tools; `videos` does not require `pics`. `all` requires both organized
media folders. An empty selection returns successfully without creating a
cache or lock.

The command never moves media, creates `dups`, or appends action history. Its
default cache and lock are collection-local. `--cache` instead writes the
database and sibling lock in an existing external directory, allowing the
media collection itself to remain read-only. Normal output is aggregate and
path-private; `--show-files` explicitly lists collection-relative paths that
could not be represented. Exit 0 means every selected media byte stream was
represented, exit 1 means coverage was incomplete or the cache was unsafe, and
exit 2 means setup was invalid. Run `scan` and `validate` separately because a
successful warm is not a collection-health or preservation verdict.

### Refresh selected cache evidence

```bash
pymo cache refresh images "/path/to/media-collection"
pymo cache refresh videos "/path/to/media-collection"
pymo cache refresh validation-standard "/path/to/media-collection"
pymo cache refresh validation-full "/path/to/media-collection"
pymo cache refresh images "/path/to/media-collection" \
  --cache "/path/to/writable-cache.sqlite3"
```

`cache refresh` deliberately bypasses reusable evidence for the selected
target. Image refresh recomputes whole-file hashes and displayed-pixel
fingerprints; video refresh recomputes hashes, probes, and decoded-playback
fingerprints. Validation targets perform a fresh current standard or full
validation and publish the resulting evidence. Existing records for the same
keys are atomically replaced while unrelated algorithms, runtimes, profiles,
media types, and collection scopes remain intact.

Refresh never deletes the cache, media, duplicate trees, or action history.
Image and video targets retain their organized-layout requirements;
validation targets work over any collection layout. Normal output remains
path-private unless `--show-files` or `--show-ignored` is explicit. An external
`--cache` keeps derived writes off a read-only collection. Refresh is not a
repair operation: invalid cache structure still fails closed, and validation
findings remain health evidence rather than ignored content.
Historical validation records remain structurally valid but stale after a
validation-algorithm upgrade. They are never reused under newer semantics;
standard or full validation refresh publishes current records while preserving
the historical and unrelated rows.

### Validate collection health

```bash
pymo validate "/path/to/media-collection"
pymo validate "/path/to/media-collection" --full
pymo validate "/path/to/media-collection" --json
pymo validate "/path/to/media-collection" --show-files
pymo validate "/path/to/media-collection" --reuse-validation
pymo validate "/path/to/media-collection" --no-cache
pymo validate "/path/to/media-collection" \
  --cache "/path/to/writable-cache.sqlite3"
```

`validate` recursively checks media in any collection layout and never moves,
deletes, repairs, quarantines, renames, or action-logs a file. The
standard profile uses Pillow integrity verification for supported images and
local ffprobe structure checks for videos. `--full` additionally loads every
image frame and completely decodes video/audio streams through local FFmpeg.

After each fresh check, validation records path-private, disposable evidence in
the shared cache by default. A record binds the complete-file SHA-256 and exact
file observation to the validation profile, semantic extension/content
context, applicable Pillow or native-tool versions, result, findings, and UTC
completion time. Observations and results publish together in bounded atomic
batches. Cache evidence never lets ordinary or full validation skip a current
probe or decode: an old healthy result cannot establish current health.

`--reuse-validation` is an explicit performance mode that may satisfy an
unchanged file from strictly compatible validation evidence. Reuse requires an
exact file observation, complete-file SHA-256, validation profile, semantic
classification context, validation algorithm, and applicable local runtime.
Pymo reopens every proposed hit through its stable descriptor boundary before
accepting it; changed or incompatible files are validated freshly and refresh
their evidence. Omit this option when current proof is required, including a
final migration sign-off.

`--no-cache` restores a run with no cache reads, evidence hashing, cache writes,
or lock creation. `--cache PATH` writes the evidence database and sibling lock
in an existing external directory instead, keeping a read-only media collection
free of derived state. Invalid known validation evidence stops early and is
left untouched. Neither cache mode changes media, creates `dups`, or writes
action history.

Reports cover empty and invalid media, unreadable or changing entries,
extension/content mismatches, unsupported recognized image formats, video
stream layouts, missing codec names or dimensions, extra streams, and
missing/invalid duration. A file whose extension claims media but whose content
is positively something else is reported as a warning-severity naming mismatch
and is never probed or decoded, so it does not make an otherwise healthy
collection fail. Unreadable subtrees make the report unhealthy rather
than being silently omitted. A damaged file becomes a finding without aborting
validation of its healthy neighbors. Unsupported media remains explicitly
unverified and visible as a warning; pymo never converts a health finding into
an ignore rule. Animated and multi-page images are counted as valid
characteristics rather than corruption.

A real video whose confidently probed container family disagrees with its
extension receives the separate warning `container_extension_mismatch`. The
check reuses the standard extensionless ffprobe result, requires an integer
content-probe score from 50 through 100, and compares families so MOV/MP4,
Matroska/WebM, and related shared demuxers do not false-positive. Weak, missing,
malformed, or unmapped evidence produces no accusation. The warning remains
visible alongside a later full-decode error and does not itself make validation
fail.

Classification and decoding use stable, no-follow file descriptors anchored
beneath the resolved collection root. If a file or parent path is replaced
during validation, the decoder remains pinned to the original file and the
result is reported as changed so the user can rerun safely.

Collection roots and filenames are hidden by default. `--show-files` adds
collection-relative affected paths; `--show-ignored` controls ignored paths
separately. JSON schema version 2 omits collection names and roots and reports
the validation mode, fresh and reused file counts, whether fresh validation
ran, whether caching was enabled, the path-private cache location class,
records written, and any publication issue. Native video
diagnostics are not copied into reports. Exit status is 0 when no errors are
found, 1 when validation reports errors or cache publication is incomplete,
and 2 when the command cannot run safely. Warnings alone return 0. Standard
validation uses bounded workers; full validation containing video uses one
worker to avoid unmeasured competing FFmpeg decodes.

### Correct truthful media extensions

```bash
pymo correct-extensions "/path/to/media-collection"
pymo correct-extensions "/path/to/media-collection" --apply
pymo correct-extensions "/path/to/media-collection" --undo
pymo correct-extensions "/path/to/media-collection" --undo --apply
```

`correct-extensions` changes only a filename's final suffix, or adds the
canonical suffix when a verified media file has none, and never changes media
bytes. It reclassifies each in-scope file from a stable, collection-anchored
descriptor, verifies and fully decodes every supported image frame through
Pillow, and probes videos through an extensionless ffprobe descriptor. It
consumes no validation cache evidence. Video correction requires at least one
video stream, an integer content-probe score from 50 through 100, a well-formed
family, and a packaged canonical mapping.

Valid synonyms such as `.jpeg` remain unchanged. TIFF-derived image containers
and camera raw extensions are protected because Pillow's TIFF identity cannot
select a truthful suffix. Shared MOV/MP4/3GP and Matroska/WebM families,
audio-capable ASF/Ogg/RealMedia families, raw MPEG elementary streams, weak
probes, unsupported or corrupt media, meaningful non-media content such as
source text named `.ts`, and custom classification extensions remain
untouched. A confidently identified MPEG transport stream under a false suffix
can become `.ts`; a fully decoded PNG named `.jpg` can become `.png`; and an
extensionless fully decoded JPEG can receive `.jpg`.

The command protects `dups`, packaged ignored paths, symbolic links, and
pymo-owned state. Incomplete discovery or changing evidence stops before an
action log is created. Preview is the default; `--apply` uses collision-safe
numbering plus the descriptor-relative atomic no-replace journal boundary.
Applied targets are rehashed from stable descriptors, and `--undo` participates
in the same later-operation dependency checks as every other mutation.

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
the same external-cache contract used by `cache warm`. `--cache` and
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

For a production baseline/working pair, use the guided coordinator above. It
preserves every preview, apply, verification, and quarantine stop in the
following manual sequence:

```bash
pymo scan "/path/to/media-collection"
pymo validate "/path/to/media-collection"
pymo correct-extensions "/path/to/media-collection" --apply
pymo organize "/path/to/media-collection" --apply
pymo rename "/path/to/media-collection" --apply
pymo find-image-duplicates "/path/to/media-collection" --apply
pymo find-video-duplicates "/path/to/media-collection" --apply
pymo verify-migration "/path/to/unchanged-baseline" "/path/to/working-copy" \
  --simulate-without-dups
pymo verify-migration "/path/to/unchanged-baseline" "/path/to/working-copy"
```

Resolve or consciously account for validation errors before applying changes;
use `validate --full` when complete local decoding is warranted. Image and
video duplicate scans are independent and may run in either order. Undo
dependent changes in reverse order. The action log refuses an earlier undo when
a later active operation touched the same files or paths.

Run `verify-migration` against the retained baseline after destination-side
changes and before discarding that baseline. Version 0.5.0 proves exact
in-scope bytes after byte-identical duplicate removal, version 0.5.1 separately
accounts for exact displayed images after metadata-varied image deduplication,
and version 0.5.2 separately accounts for supported strict-playback video
remuxes. Version 0.5.3 combines them into the final preservation verdict.
Version 0.5.10 can preview whether the same contract would remain satisfied
without destination `dups`; after retained external quarantine, rerun the
ordinary command against the physical collection. Do not discard a baseline
unless that observed verdict is complete for the actual collection and all
recovery evidence has been reviewed.

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
the same files. An extension correction is a distinct tool run using ordinary
rename actions, so history can distinguish truth correction from deterministic
naming and require the same reverse dependency order.

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
GitHub Actions always classifies pull requests and `main` pushes and publishes
one stable `quality-gate`. Documentation-only changes run a lightweight
documentation/privacy gate; executable, packaging, toolchain, and workflow
changes run the same locked quality, coverage, native-FFmpeg, and build gate on
Ubuntu, the pinned Fedora container, and macOS. Manual dispatch also runs that
full platform set. Every annotated `v*` tag runs a narrower Linux release
workflow that verifies mainline ancestry, builds both distributions, and
requires an isolated wheel installation to report exactly the tagged version.
Ordinary branch pushes remain quiet, and no workflow runs while repository
Actions is disabled. ADR 0081 records the separation. See
[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for the branch and release
workflow. The public repository has API-verified no-bypass rules for `main` and
immutable `v*` tags; `main` requires an up-to-date pull request, resolved
conversations, and the configured hosted status checks.

Version 0.5.8 adopts Apache-2.0, adds structured issue
forms and security guidance, and implements the contained workflow recorded in
ADR 0081. Pull requests and exact `main` commits receive their applicable
aggregate gate; tags prove ancestry, package versions, distributions, and an
isolated installation without repeating an already required platform suite.
Public visibility, Actions, approval for every external contributor, and the
no-bypass branch/tag rulesets were activated and verified before this release.
Structured issues and private vulnerability reporting are enabled only after
the corresponding 0.5.8 files reach `main`.

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
output, logging privacy, non-mutating standard/full validation, fresh
validation evidence, validation JSON
privacy and health exit codes, and the guarantee that video decoding never
invokes capture devices. Directional migration tests cover fresh exact-byte
inventory, duplicate multiplicity, missing/unproven evidence, zero writes,
schema privacy, exact displayed-image matches across metadata or format
changes, and strict decoded-video matches across supported remuxes without
relabeling absent source bytes. Private collections and their names are not
fixtures or repository content.

## Versions and releases

Git tags are the authoritative release version. Hatchling builds the package,
and hatch-vcs derives the Python package version from tags such as `v0.2.0`;
there is no second version string to update by hand. Untagged development
commits receive a PEP 440 development version containing their Git revision.
uv manages the environment and `uv.lock`, while ordinary standards-compatible
installers can still build and install the package.

## License

`python-media-organizer` is licensed under the
[Apache License, Version 2.0](LICENSE).

## Roadmap and research

`pymo scan COLLECTION` provides the fast local overview and recommends
`pymo validate COLLECTION` before mutation. Version 0.4 established
corruption-tolerant discovery and the shared cache foundation; version 0.5.0
adds fresh directional exact-byte coverage, version 0.5.1 adds exact
displayed-image evidence, version 0.5.2 adds strict decoded-video evidence, and
version 0.5.3 adds the fresh layered final verdict. Corrupt, unreadable,
changing, unsupported, and mismatched media remain visible findings rather than
automatic ignore rules. The promoted continuation completed public governance
in 0.5.8; version 0.5.9 adds reversible
`correct-extensions` before organization,
adds zero-write preservation simulation without `dups` in 0.5.10, and version
0.5.11 coordinates the complete guided single-collection runbook. Rescue copying, irreversible
duplicate finalization, damaged-media remediation, richer metadata, and
similarity tooling remain later roadmap or research work. Full video decoding
remains sequential until representative benchmarks show that bounded process
concurrency improves real external-drive workloads without increasing
contention or reducing safety.

See the [documentation index](docs/README.md) for the release
[roadmap](docs/ROADMAP.md), [research notebook](docs/RESEARCH.md),
[changelog](docs/CHANGELOG.md), [production migration runbook](docs/MIGRATION.md),
[package architecture](docs/ARCHITECTURE.md),
[architecture decisions](docs/adrs/README.md), and
[adversarial review ledger](docs/CODE_REVIEW.md). `HANDOFF.md` records the
current engineering state and compatibility details. `AGENTS.md` is the
authoritative instruction file for coding agents; a tool-specific entry point
navigates to it without introducing a requirement of its own, and ADR 0077
records the multi-assistant coordination model, including single release
ownership and how disagreements are settled.
