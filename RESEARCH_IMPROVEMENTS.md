# Research and future improvements

This document is the durable research notebook and feature backlog for the
Media Organization project. It records product research, source-audit results,
design conclusions, privacy standards, licensing cautions, and ideas that may
be useful in future versions.

Research snapshot: **2026-08-21**

## Current decision

Continue building the project as a custom, local-first Python package named
**python-media-organizer**, versioned from signed-off Git tags. Its command-line
name is **`pymo`**.

Existing behavior has several unusual safety properties that none of the
researched products combines:

- dry-run-first operation with an explicit `--apply` boundary;
- no automatic media deletion and no overwriting;
- duplicate isolation into review folders instead of deletion;
- collision-safe moves and renames;
- post-operation verification;
- an append-only, per-collection action history;
- dependency-aware undo across separate tools;
- deterministic duplicate definitions instead of opaque similarity decisions;
- simple, auditable dependencies and no cloud services or telemetry.

The implemented configuration foundation uses immutable packaged TOML defaults
plus an optional collection-root `.pymo.toml` or explicit `--config` extension.
It is deliberately constrained data, not executable rules. Shared ignore
patterns apply to organization, renaming, and both duplicate finders so common
operating-system metadata and tool state remain untouched.

Local AI remains acceptable in principle, including models downloaded to the
machine, but it is a future, explicitly optional feature. Its likely first use
would be descriptive file-naming assistance. It is not a current priority and
must never require hosted inference or upload media.

## Research method and limits

The audit used official project pages, source repositories, package metadata,
and a disposable Python virtual environment. No third-party tool was run
against any real collection.

For Home Media Organizer, release `0.3.7` was downloaded and extracted, its
source repository was cloned, destructive operations and network-related code
were searched, and a dependency-resolution dry run was completed. The full
dependency set was not installed because the resolution itself demonstrated a
very large and unnecessary runtime surface.

For PyPipeline, the advertised website, pricing and FAQ text, HTML resources,
PyPI endpoint, and GitHub endpoint were inspected. Its CLI could not be
installed or source-audited because the advertised package and repository did
not exist publicly at the time of research.

Static source review can find explicit uploads, telemetry SDKs, network
clients, and automatic download paths, but it cannot prove that every binary
dependency is harmless. Strong privacy therefore requires both source design
and enforceable runtime constraints.

## Product audit: Home Media Organizer

Sources:

- <https://pypi.org/project/home-media-organizer/>
- <https://github.com/BoPeng/home-media-organizer>
- <https://home-media-organizer.readthedocs.io/>

Audited release: `0.3.7`, published 2025-03-02. PyPI labels it pre-alpha and
the package is MIT licensed.

### Useful capabilities

- Organizes photos and videos using EXIF-derived dates.
- Supports configurable date-based directory and filename patterns.
- Reads, writes, shifts, and searches EXIF information through ExifTool.
- Detects exact byte-content duplicates independently of filenames.
- Compares two collections by content, which can reveal missing, changed,
  renamed, or reorganized copies.
- Maintains a SQLite metadata/tag manifest.
- Validates some media formats.
- Provides tag queries and local AI classification for faces, age, gender,
  emotion, and NSFW categories.

### Safety problems

The tool is not compatible with this project's non-destructive standard.

- Duplicate handling calls `os.remove()` and permanently deletes copies.
- Batch duplicate handling keeps the longest/deepest pathname, which is not a
  reliable proxy for originality or quality.
- Interactive duplicate selection also permanently removes unselected files.
- Rename and organization code can delete the source when it finds an exact
  copy at the canonical destination.
- Cleanup directly unlinks configured files.
- Validation can remove corrupt or changed files.
- There is no append-only action journal or general undo system.
- The SQLite manifest stores file metadata and tags; it is not a reversible
  transaction log.
- Prompt handling defaults to `y`, while this project requires explicit apply.
- Dry run is an option rather than the central operational contract.

Its duplicate definition is whole-file content identity. It does not match
images by displayed pixels while ignoring metadata, and it does not provide
decoded-content video matching.

### Privacy and dependency findings

No obvious first-party telemetry, analytics SDK, or intentional media-upload
path was found in the `0.3.7` package source. This is a limited positive result,
not a complete guarantee about all dependencies.

AI models may download additional files. The mandatory dependency graph also
contains network-capable libraries such as Requests and gdown. A simulated
installation resolved **75 packages**, including:

- DeepFace;
- TensorFlow, with a roughly 239.5 MiB platform wheel in the audit;
- Keras and tf-keras;
- NudeNet;
- ONNX Runtime;
- OpenCV and OpenCV-headless;
- Flask, Flask-CORS, and Gunicorn;
- Requests and gdown;
- NumPy, pandas, Pillow, and several model-support packages.

These AI dependencies are mandatory rather than separated into optional
extras. That greatly increases installation size, audit surface, binary supply
chain, and the chance of unexpected network behavior for users who only want
file organization.

The current source also initializes its cache and manifest under
`~/.ai-marketplace-monitor` instead of the documented Home Media Organizer
directory. This appears to be a copy-and-paste path bug, not proof of
telemetry, but it is a meaningful quality-control warning.

The cloned source had only 14 discovered test functions at the audit snapshot.

### Conclusion

Do not use Home Media Organizer on the real collections. Reuse concepts such
as metadata inspection, date-resolution policy, validation, and
collection-to-collection comparison under this project's stronger safety
model. MIT-licensed source can be consulted or reused only with appropriate
license and attribution handling.

## Product audit: PyPipeline

Sources advertised by the product:

- <https://pypipeline.com/#pricing>
- <https://pypi.org/project/pypipeline-cli/>
- <https://github.com/PyPipeline/pypipeline>

### Advertised capabilities

- A free MIT command-line tool.
- Fast SQLite media indexing.
- Exact duplicate detection by content hash.
- Organization preview and safe file operations.
- Local semantic search through Ollama.
- A terminal user interface.
- A paid desktop application.
- Cloud index synchronization, hosted AI, visual duplicate detection, and a
  web dashboard in future paid offerings.

### Verifiability and privacy findings

As of the research date, both the advertised PyPI package and GitHub repository
returned HTTP 404. `pip` reported no available `pypipeline-cli` distribution.
The paid offerings were still presented through a waitlist. Consequently, no
CLI package, dependency graph, source code, tests, telemetry behavior, or file
mutation implementation could be verified.

The marketing site says the free tool is local and private, but also says that
Pro synchronizes filenames and metadata and that paid features include hosted
AI. Even without uploading the media bytes, transmitting filenames and
metadata violates the strict requirement that collection information remain
local. Cloud and hosted AI are therefore disqualified.

The downloaded landing-page HTML contained no obvious analytics package. It
loads a GitHub star badge, and submitting the waitlist form sends the supplied
email address to a Cloudflare Worker. This says nothing about the unavailable
CLI.

### Conclusion

Do not adopt PyPipeline unless a real public release and source repository
appear and can be audited independently. Its local SQLite index and search UX
are useful concepts, but its current claims are not verifiable.

## Other local and open-source alternatives

### Czkawka

Source: <https://github.com/qarmin/czkawka>

Czkawka is the strongest general-purpose reference found. It is implemented in
Rust, has GUI and CLI frontends, exposes a reusable core, and states that it has
no Internet access and collects no user information or statistics.

Useful ideas:

- BLAKE3/full-content duplicate detection with size and pre-hash filtering.
- Persistent hash and thumbnail caches for fast rescans.
- Similar-image hashing with selectable algorithms and geometric invariance.
- Similar-video scanning using FFmpeg.
- JSON output for automation.
- Reference/protected directories.
- Bad-extension, corrupt-file, empty-folder, and unwanted-name scanners.
- EXIF removal and video optimization as separate tools.

Limitations for this project:

- It can delete, trash, or hard-link files.
- It does not participate in a shared cross-tool undo history.
- Its similar-media thresholds are not the same as this project's exact
  duplicate definitions.

If used independently, use reporting only or mount the source library
read-only. Czkawka's MIT components are the most practical source-reference
candidate when licensing and attribution are preserved.

### Video Duplicate Finder

Sources:

- <https://github.com/0x90d/videoduplicatefinder>
- <https://github.com/0x90d/videoduplicatefinder/wiki/How-Duplicate-Detection-Works/09c2e2a3fdbeda3ebfe5d8fe4a1ead5054aab9ad>

This is the strongest specialized video-matching reference.

Useful ideas:

- Sample frames across a video's duration.
- Use perceptual hashes to find re-encodes, resized versions, watermarks, and
  mirrored copies.
- Cache scan fingerprints for very fast rescans.
- Find shorter clips inside longer videos using Chromaprint-style audio
  fingerprints and sliding-window comparison.
- Confirm an audio partial-match using decoded video frames to reduce false
  positives from shared soundtracks.
- Rank likely keepers using resolution, bitrate, duration, and quality.
- Provide both exact/conservative and fuzzy/aggressive scan profiles.
- Offer CLI, GUI, and local web interfaces backed by one engine.
- Recommend dry run and provide trash as a safer alternative to deletion.

Its optional AI pass uses DINOv2 visual embeddings through ONNX Runtime. The
project says inference is local and nothing is uploaded. Enabling it downloads
about 100 MiB of runtime/model components once and verifies the model hash.

Limitations:

- Its main purpose is similarity, not strict decoded equivalence.
- It supports permanent deletion.
- It has no shared append-only action history.
- It is AGPLv3. Concepts and published algorithms can be studied, but source
  must not be copied into a differently licensed package without a deliberate
  licensing decision.

The audio-offset plus visual-confirmation design is especially valuable for a
future report-only partial-clip finder.

### digiKam

Sources:

- <https://www.digikam.org/about/>
- <https://docs.digikam.org/en/maintenance_tools/maintenance_duplicates.html>
- <https://docs.digikam.org/en/maintenance_tools/maintenance_quality.html>
- <https://docs.digikam.org/en/setup_application/metadata_settings.html>

digiKam is the strongest complete graphical library manager in the research.
It states that photos, metadata, settings, and AI processing remain local.

Useful ideas:

- A local searchable catalog without forcing physical reorganization.
- EXIF, IPTC, and XMP reading and writing.
- Sidecar metadata and configurable metadata synchronization.
- Duplicate and similarity fingerprints.
- Face recognition, auto-tags, natural-language search, and local models.
- Image-quality scoring using either local deep learning or deterministic
  factors: blur, noise, exposure, and compression.
- Explicit user labels for accepted, pending, and rejected items.
- Rebuildable fingerprints, thumbnails, and database maintenance stages.

Limitations:

- It is a large GUI application and database ecosystem rather than a focused
  reversible CLI.
- It can write embedded metadata and provides cloud export integrations.
- Its database/actions do not integrate with this project's action log.

digiKam may be useful as an optional companion application configured not to
write original media, but it is not a replacement for `pymo`.

### organize

Source: <https://github.com/tfeldmann/organize>

Useful ideas:

- Reusable YAML rules and named profiles.
- EXIF filters and filename/path templates.
- Conflict-resolution policies.
- A dedicated simulation command.
- Machine-readable JSONL output.
- Config validation and debugging.

Limitations:

- Rules may invoke arbitrary Python and shell commands.
- Deletion is a normal action.
- There is no shared reversible transaction history.

The configuration and explainable simulation UX are worth adapting later, but
`pymo` should expose a constrained schema rather than arbitrary code execution.

### Phockup

Source: <https://github.com/ivandokov/phockup>

Useful ideas:

- Copy-first ingestion by default.
- EXIF date-field priority configuration.
- Filename-regex and filesystem-time fallbacks.
- An `unknown` destination for media with no trustworthy date.
- Checksum comparison before resolving target collisions.
- Date-range filters and traversal-depth controls.
- Device/user suffixes for merging multiple sources.

Limitations:

- Its year/month/day layout is different from this project's collection model.
- It has no durable undo or cross-tool dependency tracking.

### dupeGuru

Sources:

- <https://github.com/arsenetar/dupeguru>
- <https://github.com/arsenetar/dupeguru/blob/master/help/en/scan.rst>

Useful ideas:

- Protected reference folders.
- Fuzzy filename and music-tag comparison.
- A picture mode that divides decoded images into blocks and compares average
  colors.
- EXIF-timestamp comparison as an optional signal.
- Cached picture analysis and multi-core comparisons.

Limitations:

- EXIF timestamp equality alone has serious false-positive risk.
- The image comparison can become quadratic.
- It is GPLv3 and should be treated as a conceptual reference unless the
  project's license is deliberately made compatible.
- It lacks `pymo`'s action-log and review-folder model.

## Durable privacy and security standard

The core package should make privacy an architectural guarantee rather than a
marketing setting.

### Core rules

- No telemetry, analytics, crash reporting, accounts, or cloud synchronization.
- No HTTP client or hosted-AI dependency in the normal dependency graph.
- No automatic downloads during ordinary commands.
- No filenames, hashes, metadata, thumbnails, embeddings, or statistics leave
  the machine.
- All file and cache paths stay within explicitly documented local locations.
- Never follow symbolic links into unapproved locations.
- Never accept a URL where a local media path is expected.
- Restrict FFmpeg inputs to local files and disable unnecessary network
  protocols where practical.
- Keep dependencies minimal, pinned within sensible compatibility ranges, and
  separated into optional extras.
- Record an SBOM/dependency inventory for releases and run dependency audits.
- Test the core with outbound socket creation blocked.

### Future local AI rules

- AI is an optional extra, never a core dependency.
- No hosted fallback exists.
- Model origin, license, size, checksum, and version are documented.
- Model installation is an explicit command or manual step.
- Downloads require an explicit user action and SHA-256 verification.
- Inference runs locally with networking denied.
- Results are suggestions stored in a local index or sidecar until explicitly
  applied.
- AI-generated names or tags expose confidence and never overwrite originals.
- Person identification and sensitive demographic classification require a
  separate ethical/privacy decision and are not part of the naming roadmap.

## Feature roadmap and integration ideas

### 1. Collection scan and statistics

Version 0.2.0 implements the completely read-only command:

```text
pymo scan COLLECTION
```

It answers whether a collection is worth organizing before any action is
applied. The fast profile reports aggregate inventory, layout and naming
readiness, review storage, same-size duplicate potential, estimated expensive
work, existing pymo state, warnings, and recommended next steps. Stable JSON
schema version 1 omits collection names, root paths, and filenames by default.
`--checksums` hashes only same-size picture and video candidates to report
exact-byte copies.

Suggested inventory:

- total files, directories, and bytes;
- counts and bytes by picture, video, audio, other, unsupported, and unknown;
- counts and bytes by extension and detected content type;
- image dimensions, formats, animation/multi-page status, and EXIF presence;
- video duration, resolution, codecs, frame rates, audio presence, and bitrates;
- dated versus undated media and the date source/confidence;
- already organized versus proposed organizer moves;
- already canonical versus proposed renames;
- exact image duplicate groups, extra copies, and reclaimable bytes;
- exact video duplicate groups, extra copies, and reclaimable bytes;
- corrupt, truncated, suspicious, or extension-mismatched files;
- symbolic links and layout problems;
- largest files and directories;
- estimated time/cost for expensive scans;
- a recommendation such as organize first, validate first, or review
  duplicates first.

Friendly terminal text and stable JSON are implemented. CSV may be added for
flat summaries. Scanning does not create an action log, write the disposable
cache, or modify media. It only reports whether local state exists.

Content classification uses a bounded thread pool, with four workers by
default and a validated 1..32 configuration/CLI range. This parallelizes
independent content-type probes without introducing concurrent FFmpeg decodes.
The remaining richer metadata, validation, and historical statistics below are
future extensions.

Possible later statistics:

- capture-date distribution and calendar heatmaps;
- camera/device and codec distribution;
- portrait/landscape/square and resolution distributions;
- duration buckets for videos;
- growth between scans;
- duplicate storage by media type and duplicate group;
- health trends and newly introduced invalid files;
- estimates of the space used by originals, review copies, and miscellaneous
  files.

Statistics remain local. Reports may contain sensitive filenames and metadata,
so they should also be treated as private collection data.

### 2. Media validation and collection health

Add `pymo validate COLLECTION` as a report-only command first.

This boundary is accepted in ADR 0019. Implementation begins only after the
pre-validation findings in `CODE_REVIEW.md` are resolved or explicitly accepted.

Image validation should distinguish header recognition from full pixel decode
and detect truncated, multi-page, and animated inputs. Video validation should
combine ffprobe structure inspection with a bounded full decode when requested.

Report:

- unreadable or partially decodable media;
- zero-length or implausibly small media;
- extension/content mismatches;
- unsupported codecs or pixel formats;
- malformed metadata and invalid UTF-8 metadata;
- missing expected video/audio streams;
- ambiguous multiple-stream layouts;
- duration, frame-count, or timestamp inconsistencies;
- checksum changes relative to a previous inventory.

Validation never deletes files. A future quarantine action may move questionable
files to a review location through the action log.

### 3. EXIF and metadata management

ExifTool is the preferred optional external engine because it supports broad
image and video metadata formats:

- <https://exiftool.org/>
- <https://exiftool.org/exiftool_pod2.html>

Potential commands:

```text
pymo metadata show FILE
pymo metadata export COLLECTION --format json
pymo metadata audit COLLECTION
pymo metadata repair COLLECTION
pymo metadata privacy COLLECTION
```

Date resolution should preserve provenance and confidence:

1. `DateTimeOriginal` or equivalent capture timestamp;
2. trusted creation metadata such as QuickTime creation time;
3. a recognized filename timestamp;
4. a recognized filename date without inventing a time;
5. filesystem modification time, clearly marked low confidence;
6. `undated` when no trustworthy value exists.

Metadata writes must be dry-run-first. Before writing, record the complete
relevant metadata snapshot and file identity. After writing, verify media
decodability, expected tags, and retained unrelated metadata. Restoration must
be possible through the action history or an immutable sidecar snapshot.

Prefer XMP/JSON sidecars for tags, ratings, captions, and AI suggestions until
the user explicitly chooses to embed them. Add GPS and privacy audits that can
report sensitive metadata or create redacted copies without modifying
originals.

### 4. Collection and backup comparison

Add a content-based comparison command independent of path and filename:

```text
pymo compare COLLECTION_A COLLECTION_B
```

Report:

- identical content in both collections;
- present only in A or only in B;
- same filename with different content;
- same content with different filenames or paths;
- files that appear renamed or reorganized;
- total missing/extra bytes;
- optional displayed-pixel image equivalence;
- optional exact decoded-video equivalence;
- a machine-readable mapping suitable for backup verification.

Comparison is read-only and should be useful for migrations, camera-card
imports, restored backups, and validating an organized collection against its
source.

### 5. Derived local index and cache

Maintain a clear separation:

- `{collection-name}-actions-log.jsonl` is authoritative, append-only mutation
  history. Version 0.2 no longer detects the fixed v0.1
  `media_actions.jsonl` filename; users needing that migration must use 0.1.5
  first.
- A SQLite index/cache is derived, disposable, and rebuildable.

This is the selected `0.1.0` design. SQLite is excellent for fingerprints,
inventory, statistics, and local queries, but replacing the already tested
JSONL journal would add migration and recovery risk without improving current
undo behavior. Existing collection history must remain usable. A later SQLite
projection may index JSONL events for reporting while leaving JSONL as the
source of truth.

The database belongs to the managed collection or an explicitly documented
local application-data directory, not inside the installed Python package.
Package installations may be read-only, shared by multiple collections, or
replaced during upgrades.

The derived database may store:

- paths and stable file identities;
- byte hashes and quick pre-hashes;
- displayed-pixel image hashes;
- decoded-video fingerprints;
- dimensions, durations, codecs, bitrates, and stream layouts;
- selected EXIF/metadata fields;
- optional perceptual hashes, thumbnails, tags, or embeddings.

Cache keys must cover content identity, size, modification state, algorithm
version, and external-tool version. Renames should reuse content-derived
records. Content changes, fingerprint algorithm changes, and FFmpeg upgrades
must invalidate the affected values.

Exact-analysis records now carry a device/inode/size/modification/change-time
snapshot and are discarded when that state changes. Existing video caches are
queried read-only and validated before decoding; invalid cache data stops early
and is preserved for explicit recovery rather than silently discarded or
automatically overwritten.

Applied file moves follow ADR 0021: descriptor-relative atomic no-replace
renames are preferred over a cross-filesystem copy fallback. This keeps the
action journal's completed boundary aligned with one atomic filesystem event.

Dry-run semantics require care and must be command-specific. `pymo scan` never
creates or updates a database. Exact-video analysis persists each successfully
decoded fingerprint during preview as documented derived state, because the
work is expensive and a later apply must be able to reuse it; `--no-cache`
provides a zero-read/write cache mode. Cache writes never imply media mutation
or action-history creation.

### Performance engineering policy

Improve measured bottlenecks in stages while preserving exactness and local-
only behavior:

1. Cache deterministic expensive results with explicit algorithm and runtime
   version keys. Incremental exact-video fingerprints are the first example.
2. Reduce work before adding concurrency: filter candidates by cheap facts,
   stream data, avoid decoded temporary media, and hash only candidates when a
   report does not require every file's digest.
3. Use bounded threads for independent subprocess or filesystem-latency work.
   `scan` classification currently follows this approach.
4. Use processes only for measured CPU-heavy work. A future exact-video worker
   count should default to one until benchmarks across internal SSDs and
   external drives prove a safe gain.
5. Prefer deterministic worker limits and stable output ordering. Never let
   concurrency alter keeper selection, action order, collision handling, or
   failure semantics.

Async I/O is not a natural fit for the current hot paths: local filesystem
reads, hashing, Pillow decoding, and FFmpeg subprocesses are blocking work, and
the subprocess output is already streamed. Threads can help latency-bound
classification; CPU-bound Python work needs processes, while FFmpeg already
uses native threads internally.

Useful future benchmarks and low-risk optimizations:

- record per-stage time for discovery, classification, hashing, ffprobe,
  fingerprint decoding, planning, and verification without recording private
  filenames;
- cache validated ffprobe structure and content hashes using carefully defined
  file identity, while retaining a full-content check before any exact move;
- compare sequential and small bounded pools for hashing and ffprobe on both
  SSD and external-media workloads;
- benchmark one versus a small number of FFmpeg processes, including thermal,
  memory, and disk-throughput effects;
- reuse cached work after logged moves and renames through content identity;
- keep compression-heavy fuzzy decode and similarity analysis outside the
  exact automatic-move path.

Every performance option needs synthetic correctness tests, deterministic
results across worker counts, interruption tests where state is persisted, and
representative benchmarks before its default changes.

The current unreleased timing patch implements the first measurement layer:
all normal commands report total elapsed time; long stages report aggregate
observed file/data rates and ETA; exact-video decoding emits a heartbeat during
one long candidate; and `performance.progress_interval_seconds` controls the
cadence. `--timestamps` is an opt-in console presentation choice, while
explicit log files timestamp every physical line. Scan JSON remains clean.

No universal throughput default is stored because classification, hashing,
image decoding, and FFmpeg decoding have different cost models, and storage,
codec, resolution, and hardware dominate performance. A future derived local
index may retain privacy-safe per-stage historical aggregates to improve
collection-specific estimates, but it must document expiry/invalidation and
must never turn a read-only `scan` into an implicit write.

### 6. Duplicate-detection levels

Keep definitions separate and visible to users:

1. **Exact bytes** — same complete file bytes.
2. **Exact displayed image** — same oriented decoded pixels, metadata ignored.
3. **Exact decoded video** — same displayed frames, timing, orientation, audio,
   and supported stream structure.
4. **Similar image** — perceptual hash or other visual similarity.
5. **Similar video** — sampled-frame visual similarity.
6. **Partial clip** — audio fingerprint plus visual confirmation and offset.
7. **AI similarity** — optional local visual embeddings for substantial edits.

Only deterministic exact levels should automatically move files into `dups`.
Similarity results should begin as report-only because thresholds can produce
false positives.

### 7. Keeper quality scoring

Current exact duplicate selection prefers larger, then older, then stable
filename order. A future explainable score may consider:

- successful full validation;
- resolution and bit depth;
- duration completeness;
- audio/video bitrate and codec quality;
- metadata richness and trustworthy capture date;
- presence in a protected/reference folder;
- known original-camera naming patterns;
- embedded thumbnail or provenance information;
- source-path confidence.

The score should be displayed factor by factor. It may recommend a keeper but
must not delete alternatives. For exact displayed images, a larger file is not
always better; it may merely contain more metadata or inefficient compression.

### 8. Rule profiles and machine-readable plans

Borrow the good parts of rule-based organizers without arbitrary code
execution:

Version 0.1.2 established schema-versioned ignore configuration. Version 0.1.3
extends that safe base with typed classification, renaming, image-inspection,
and video-timeout policy. Custom arrays are additive, values are strictly
validated, and configuration remains constrained data rather than executable
rules. Fixed collection paths and journal/cache protocol identifiers remain
code invariants because making them adjustable would weaken compatibility.

- named TOML profiles;
- validated fields and constrained actions;
- preview/explain commands;
- stable JSON plan output;
- include/exclude patterns;
- protected/reference folders;
- date-range and traversal-depth filters;
- explicit collision strategies;
- saved but human-readable configuration.

Plans should be serializable and reviewable, but applies must revalidate the
current filesystem rather than blindly trusting a stale plan.

### 9. Future local semantic naming and search

Potential future capabilities:

- local object/scene tags;
- suggested descriptive filename tokens;
- local natural-language search over images and sampled video frames;
- grouping visually related media;
- OCR for screenshots and documents contained in collections.

AI output should not immediately rename files. Suggested descriptors should be
reviewable, editable, confidence-scored, and stored in a local sidecar or index.
The deterministic collection name, media kind, sequence, and trusted timestamp
remain the stable filename core.

## Implemented video duplicate principles

The `pymo find-video-duplicates` implementation is deliberately conservative:

- scan only flat `vids`;
- write only to `dups/vids`;
- do not inspect or create `pics` or `dups/pics`;
- hash whole-file bytes as a fast path;
- use ffprobe for structure and candidate selection;
- derive an exact normalized playback fingerprint from decoded frames, timing,
  orientation, and audio;
- require video and audio agreement;
- skip corrupt, unsupported, HDR/high-bit-depth, multi-video, multi-audio,
  subtitle, data, or attachment cases until tested;
- stream decoded data instead of creating decoded temporary videos;
- never auto-move recompressed pixels, cropped clips, watermarked copies, or
  merely similar media;
- report retained and duplicate storage plus potentially reclaimable bytes;
- move copies into flat `dups/vids` using readable names;
- participate in the shared action log with its own tool identity;
- persist each completed fingerprint incrementally during preview or apply and
  report cache hits/misses, with `--no-cache` as a complete opt-out;
- support dry-run/apply/undo and post-apply verification.

FFmpeg and ffprobe are external runtime requirements, not hidden Python wrapper
dependencies. Real integration tests are required in addition to controlled
subprocess tests.

## Packaging direction

The durable package is named `python-media-organizer`; the import and CLI name
is `pymo`.

The implemented initial layout is:

```text
python-media-organizer/
  pyproject.toml
  README.md
  RESEARCH_IMPROVEMENTS.md
  AGENTS.md
  HANDOFF.md
  src/
    pymo/
  tests/
```

The `pymo` command should provide focused subcommands while internal modules
remain reusable and independently tested. Action-log tool identities and schema
must remain compatible with existing collections during the transition.

The selected packaging toolchain separates standardized responsibilities:

- uv 0.12 or newer manages Python, `.venv`, dependencies, `uv.lock`, command
  execution, and build orchestration;
- Hatchling is the PEP 517 build backend;
- hatch-vcs derives PEP 440 package versions from Git release tags;
- standard PEP 621 `[project]` metadata preserves compatibility with pip and
  other build frontends.

This avoids a manager-specific package format. The committed uv lockfile makes
development and tests reproducible, but downstream installers continue to
resolve the package's declared runtime requirements normally.

### Logging design

Use Python's standard `logging` package throughout the packaged application.

- Human-friendly `INFO` output is the normal console experience.
- Warnings and errors remain visibly distinct.
- `--verbose` enables diagnostic `DEBUG` output.
- `--quiet` limits output to warnings and errors.
- Machine-readable command results remain a separate future output format,
  rather than trying to parse free-form logs.
- Persistent log files are opt-in through an explicit path. They are not
  created automatically because collection paths and filenames are private.
- Exceptions from external tools include useful context without dumping media
  bytes or unrelated metadata.
- Tests capture and assert log records or rendered command output as
  appropriate.

### Native video runtime

Python dependencies such as Pillow and pytest live in the uv-managed project
virtual environment. FFmpeg and ffprobe are native executables and should
remain an explicit external runtime dependency. A pip-installed Python wrapper
does not remove that requirement, while packages that silently bundle FFmpeg
add binary provenance, platform, licensing, and update concerns. Prefer a known
system installation and record its version in derived fingerprint-cache keys.

## Licensing guidance

- Home Media Organizer, Czkawka core/CLI, organize, and Phockup provide
  MIT-licensed source or components. Preserve copyright and license notices
  when code—not merely an idea—is reused.
- dupeGuru is GPLv3.
- Video Duplicate Finder is AGPLv3.
- GPL/AGPL source should not be copied into this package without a deliberate
  compatible licensing decision. Learn from algorithms, documentation, tests,
  and user experience, then implement independently from suitable primary
  references.
- Model licenses and datasets must be reviewed separately from inference
  runtime licenses before any AI feature ships.

## Open research questions

- Which exact decoded-video normalization is most stable across FFmpeg versions
  and harmless container remuxing without collapsing meaningful timing or audio
  differences?
- Which local cache identity works reliably across filesystems while still
  reusing fingerprints after a logged move or rename?
- Should derived caches live in each collection, an application cache
  directory, or both with an explicit portability/export command?
- Which image similarity hash gives the best explainable results across crop,
  resize, recompression, rotation, and watermark cases?
- How should quality recommendations balance resolution, compression quality,
  metadata, provenance, and successful validation?
- Which report schema can power both terminal summaries and a future local GUI
  without coupling the core to one interface?
- How can `pymo scan` improve its current byte/work estimates into reliable
  elapsed-time ranges without decoding the entire collection first?
- Do representative internal-drive and external-drive benchmarks justify a
  bounded process pool for full FFmpeg fingerprints, despite FFmpeg's own
  threading and likely disk contention?
- What is the safest metadata-undo representation for formats where ExifTool
  may rewrite container structures even when logical tags are restored?
- Which local visual-language model is appropriately licensed, compact, and
  accurate enough for optional filename suggestions?

## Near-term implementation order

Strict duplicate-finder ownership, deterministic exact video duplicate
detection, the uv/Hatchling package structure, resumable video fingerprints,
and the version 0.2 collection scan are implemented and covered by tests. The
remaining order is:

1. Add report-only media validation.
2. Add metadata inspection/export and confidence-based date resolution.
3. Add collection/backup comparison.
4. Mature the derived SQLite index/cache.
5. Add perceptual matching only as an explicitly non-deterministic,
   report-first feature.
6. Revisit optional local AI naming after the deterministic toolkit is mature.
