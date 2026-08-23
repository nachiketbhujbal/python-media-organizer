# Research notebook

This document records product research, source-audit results, design evidence,
privacy standards, licensing cautions, and open questions. Work with an
accepted delivery target is promoted into [ROADMAP.md](ROADMAP.md); shipped
behavior is recorded in [CHANGELOG.md](CHANGELOG.md).

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

### Duplicate finalization and collection history

Duplicate detection and isolation must remain non-deleting. A later
finalization command may deliberately dispose of reviewed content, but it needs
a stronger contract than an `--apply` option on either duplicate finder:

- require a complete dry-run inventory and reject untracked additions or an
  action-journal state that cannot explain the review tree;
- prefer moving the review tree to an explicit quarantine outside the working
  collection, leaving permanent deletion as a later and separately confirmed
  boundary;
- require fresh directional preservation evidence for the simulated
  post-finalization collection, and define how that evidence is bound to the
  exact baseline, working namespace, and time of finalization;
- state prominently that disposal makes the corresponding duplicate move and
  any dependent earlier runs impossible to undo unless the bytes are restored;
- append a durable irreversible event to the portable journal even though it
  has no inverse, recording what pymo established and did without implying that
  journal replay can recover deleted bytes; and
- support a path-private collection-history synopsis, similar in purpose to a
  concise version-control log, which distinguishes committed reversible runs,
  undo runs, quarantines, and irreversible finalization events.

The journal schema, confirmation ceremony, quarantine portability across
macOS/Linux/WSL, and preservation-evidence binding require an ADR before this
work receives a release number.

### Persistent diagnostic logging

Collection-local diagnostic logs are useful acceptance and operational
evidence, but making them automatic would reverse the current privacy decision
that persistent path-bearing output is opt-in. It would also create state for
commands whose contract is report-only, complicate read-only collections and
two-root migration verification, and require the log itself to be excluded
consistently from scan, validation, mutation, and preservation scope.

Research should compare the current explicit `--log-file PATH` behavior with a
possible `{collection-name}-pymo.log` default plus `--no-log`. Any default must
define append/rotation and locking behavior, failure policy, filename privacy,
which root owns a two-collection command's log, and whether read-only commands
may create it at all. A safer alternative may be an explicit configured log
directory outside media collections while the append-only action journal and a
future history command provide the durable collection audit record.

Logging-level controls should also be normalized without proliferating
ambiguous flags. Evaluate a conventional `--log-level
{DEBUG,INFO,WARNING,ERROR,CRITICAL}` interface, a convenient `--debug` alias,
separate console/file thresholds, and compatibility treatment for the current
`--verbose` and `--quiet` options. The current default remains console INFO and
explicit-file INFO, with DEBUG enabled only deliberately.

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
- Which hardware and workload signals can choose conservative worker counts
  across macOS, Debian-family Linux, Red Hat-family Linux, and WSL, and what
  oversubscription threshold should trigger a warning for a manual override?
- Does profiling on representative collections expose a Python CPU hotspot
  that justifies Cython, Rust, or another native accelerator after accounting
  for binary portability, build complexity, maintenance cost, and the time
  already spent inside Pillow, hashing libraries, SQLite, and FFmpeg?
- What is the safest metadata-undo representation for formats where ExifTool
  may rewrite container structures even when logical tags are restored?
- Which local visual-language model is appropriately licensed, compact, and
  accurate enough for optional filename suggestions?
