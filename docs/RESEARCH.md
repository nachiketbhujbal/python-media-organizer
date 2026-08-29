# Research notebook

This document records product research, source-audit results, design evidence,
privacy standards, licensing cautions, and open questions. Work with an
accepted delivery target is promoted into [ROADMAP.md](ROADMAP.md); shipped
behavior is recorded in [CHANGELOG.md](CHANGELOG.md).

Research snapshot: **2026-08-29**

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

**Decision promoted:** version 0.5.8 adopts Apache-2.0 and completes the
controlled public transition. ADR 0081 owns the license, workflow, branch/tag
protection, issue, and security-reporting decision. The audited repository was
made public early to restore standard-runner verification; server-enforced
branch/tag protections and conservative Actions controls were installed before
workflow execution, while versioned license, issue, and security files land in
0.5.8.

Apache-2.0 is permissive while making the copyright grant, patent grant and
termination, notice retention, and lack of a trademark grant explicit. It does
not grant a fork authority over this repository, its `main` branch, releases,
or project identity. Accepted contributions will use the same license; no
history rewrite or contributor license agreement is planned for the current
sole-maintainer boundary.

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

## Media truthfulness, damage, and remediation

**Status: research only, with two shipped exceptions and one implemented release candidate.** The
classification-severity correction described below shipped in 0.5.5,
confidence-gated container and extension detection shipped in 0.5.6, and the
separate reversible correction command is implemented on the unreleased 0.5.9
candidate under ADR 0082. Validation
remediation guidance, damaged-media isolation folders, byte-changing repair,
container conversion, and damaged-media quarantine are all recorded here for
later evaluation and must not be implemented on the strength of this record
alone. Several questions below are deliberately unresolved.

### What prompted it

Two observations from local acceptance work, stated generically.

First, validation detects a still image whose decoded format disagrees with its filename extension
and reports `extension_content_mismatch`, but the equivalent video check is only category-level:
classification asks whether the detected content and the extension are both video, so an MPEG
transport stream named `.mp4`, a Matroska named `.mp4`, or a QuickTime file named `.webm` are all
accepted in silence. A real file of the first kind decoded without a single error and played
correctly in any player supporting its true container. Nothing about it was damaged. The report was
simply silent about the one thing that was untrue: its name.

Second, two still images failed full decode with the same finding code and the same exit status
despite being nothing alike. Both were truncated. One lost only its end-of-image terminator, so
every row of pixel data decodes and the picture is visually complete. The other lost the terminator
*and* a substantial share of its trailing scan data, so it renders a large flat region where image
content used to be. The same two-byte repair would make either file conform to the format; only in
the first case does that produce a file with nothing missing.

### Two independent axes

Damage resisted a single classification because two separate questions are being asked:

| | Content complete | Content provably incomplete |
| --- | --- | --- |
| **Structurally valid** | healthy | valid but permanently lossy |
| **Structurally invalid** | repairable to fully healthy | repairable only to valid-but-lossy |

Structural validity is about conformance to the format specification, and is often repairable.
Content completeness is about whether data is provably gone, and is never repairable. A file can be
in any of the four states, and remediation only ever moves a file leftward along the structural
axis; it can never move it upward.

Any future taxonomy, folder, report, or command must keep these axes separate. Conflating them is
what makes "corrupt" an unhelpful word.

### Terminology

- **Conversion** is the umbrella term for producing a new file in a different format. Both kinds
  below are conversions.
- **Remux** repackages: the encoded bitstreams are copied unchanged into a different container.
  Decoded output is bit-for-bit identical, so a remuxed file can be *proven* equivalent under the
  existing strict decoded-playback definition.
- **Transcode** re-encodes: streams are decoded and recompressed. Decoded output is not identical
  and quality is lost. A transcode can never satisfy the strict playback definition, so discarding
  a transcode's original is genuine, unrecoverable loss.
- **Repair** is distinct from conversion. A repair corrects a file that violates its own format so
  that conforming decoders accept it. The container and encoding are unchanged.

The distinction is load-bearing rather than pedantic. Correcting a false extension changes no
bytes. A repair changes bytes to fix a defect in the file. A remux changes bytes while provably
preserving essence. A transcode changes bytes and provably loses some. Those four operations carry
four different risks and must never be offered through one undifferentiated interface.

### Validation remediation and guidance

Validation should eventually answer “what can I safely do next?” without
silently repairing, ignoring, or deleting evidence. The remediation design
should classify findings by actionability:

- an extension/content mismatch can support a separately reviewed, reversible
  extension-normalization plan when decoder and signature evidence agree;
- a decode failure may support reversible quarantine into a dedicated review
  tree, but cannot be described as repaired and must remain represented in
  subsequent baseline comparison;
- an unsupported recognized format is unverified, not corrupt; resolving it
  requires an explicit, locally installed decoder with reviewed provenance or
  continued exact-byte preservation; and
- informational stream findings need an explanation and usually no mutation.

Remediation must remain dry-run-first, action-journaled, collision-safe, and
separate from ordinary validation. It must define ordering with organization
and renaming, retain the original finding and evidence, and recommend fresh
validation plus migration verification afterward. Quarantine must never become
an implicit ignore list.

### Container and extension truthfulness

Version 0.5.6 uses the ffprobe result standard validation already obtains for every non-empty video,
so container-family comparison adds no probe invocation. The check compares a confidently reported
demuxer family against the family implied by the extension and reports a distinct
`container_extension_mismatch` code at warning severity.
The code is deliberately separate from `extension_content_mismatch`: overloading one code with a
fourth meaning would leave the aggregate report unable to distinguish a misnamed container from
content that is not video at all, with only prose as the discriminator.

The comparison must be **family-level**, never exact-string, because several extensions
legitimately share one demuxer:

| Extension | Expected `format_name` family |
| --- | --- |
| `.3g2`, `.3gp`, `.m4v`, `.mov`, `.mp4` | `mov,mp4,m4a,3gp,3g2,mj2` |
| `.mkv`, `.webm` | `matroska,webm` |
| `.ts`, `.m2ts`, `.mts` | `mpegts` |
| `.avi`, `.divx` | `avi` |
| `.asf`, `.wmv` | `asf` or `asf_o` |
| `.flv` | `flv` |
| `.mpe`, `.mpeg`, `.mpg` | `mpeg` or `mpegvideo` |
| `.vob` | `mpeg` |
| `.rm`, `.rmvb` | `rm` |
| `.ogv` | `ogg` |

ADR 0079 records the resulting limits rather than leaving them implicit:

- MP4 versus MOV, and Matroska versus WebM, are **not distinguishable** by this method, and that is
  acceptable — both pairs are genuinely one container family, and a name inside its own family is
  not a lie worth reporting.
- `.ts` versus `.m2ts`/`.mts` are also reported identically as `mpegts`, although BDAV streams use
  192-byte packets with a timestamp prefix while plain transport streams use 188-byte packets.
  Distinguishing them requires packet-level inspection and is out of scope; the detector must not
  claim a precision it does not have.
- A mismatch is a **warning**, never an error. A misdescribed container is not damage, the media is
  not harmed, and exit status must not change.

Local FFmpeg/ffprobe 9.0.1 measurements initially made a maximum-score boundary look sufficient:
generated MP4, MPEG-TS, Matroska, AVI, ASF, and FLV fixtures reported their listed families with
probe score 100; a raw MPEG-2 elementary stream reported `mpegvideo` at 51, and a generated MPEG
program stream reported `mpeg` at 26. The first three-platform run disproved that boundary. The
FFmpeg builds on macOS, Ubuntu, and Fedora reported the same short valid MPEG-TS fixture as `mpegts`
with score 50, while local FFmpeg 9 reported 100.

FFmpeg's own MPEG-TS probe can return half of `AVPROBE_SCORE_MAX` for a valid short transport stream,
and its public probing contract recommends retry only at scores at or below one quarter of the
maximum. Pymo probes an extensionless descriptor path, so the separately defined filename-extension
score of 50 cannot contribute. The implemented boundary is therefore an integer content score from
50 through 100. Generic `.mpe`, `.mpeg`, and `.mpg` policy accepts both `mpeg` program streams and
`mpegvideo` elementary streams; a raw elementary stream under an unrelated extension remains a
truthful mismatch. Missing, malformed, below-50, above-maximum, or unmapped evidence makes no claim.
The durable primary references are FFmpeg's
[MPEG-TS probe implementation](https://www.ffmpeg.org/doxygen/8.0/mpegts_8c_source.html#l03057),
[probe-score constants](https://ffmpeg.org/doxygen/8.0/avformat_8h.html#l00458), and
[input-probing contract](https://ffmpeg.org/doxygen/8.0/group__lavf__decoding.html).

### Recognizing transport streams, and the `.ts` hazard

Transport streams are ordinary, valid video. A collection may legitimately contain nothing else,
and such files belong in the organized video folder like any other supported video. Their
extensions are already packaged video extensions, so they are already recognized and organized like
any other supported video rather than treated as an anomaly.

One constraint makes this extension unlike the others: **`.ts` is also the conventional extension
for TypeScript source files.** A tool that trusts the extension alone would sweep source code into
a video folder.

Measurement corrected three assumptions recorded here earlier, and the corrections matter more than
the original wording did. Transport-stream extensions are **already** packaged video extensions, so
recognizing them is neither a configuration change nor a classification-policy change. The local
content signature cannot be the sole positive authority for recognizing genuine transport-stream
content: the system content-signature utility carries a transport-stream magic rule but misses
common encoder output that emits the
service description table ahead of the program association table, so a genuine transport stream is
frequently unrecognized. The extension must therefore keep its classification weight, and a
confidence-gated container probe supplies stronger evidence later during validation.

The hazard was real and was an active defect rather than an open design question: a non-media file
bearing one of these extensions was classified as video, probed, and reported as a decode error at
failing exit status. That defect is fixed. A meaningful non-media content signature now outranks a
media extension during validation discovery, so such a file is reported as a warning-severity
naming mismatch, is never probed or decoded, and does not fail the run. The rule is deliberately
narrow and does not require the extension to lose its weight for genuine media, which is why a
genuine transport stream named `.ts` is still classified and validated as video. ADR 0078 records
the decision. Container-family detection builds on this corrected discovery behavior.

### Correcting a false extension

Correcting an extension changes no bytes, is trivially reversible, and is the safest possible
remediation. It should be a **separate narrow command**, not an option on the deterministic
renamer: the two change different kinds of truth, since renaming decides what a file is *called*
while correction decides what a file *claims to be*, and folding them together would let one
silently perform the other.

The safe order is validate, then correct extensions, then organize, then rename, so that every
later stage sees a file whose name no longer lies and the deterministic renamer never has to
preserve a false extension. The maintainer promoted this work to version 0.5.9 as the separate
`pymo correct-extensions COLLECTION` command.

The unreleased candidate implements those constraints through fresh stable-descriptor Pillow
verification and extensionless ffprobe evidence, immutable packaged canonical/synonym maps,
dry-run/apply/undo, a distinct journal tool ID carrying ordinary rename actions, existing collision
naming, and stable target rehashing. Valid synonyms remain unchanged. Shared MOV/MP4/3GP and
Matroska/WebM demuxer families, weak probes, unsupported or corrupt media, meaningful non-media
content, and custom classification extensions have no correction authority. The command protects
`dups`, consumes no validation cache evidence, and fails before state when discovery or evidenced
file state changes. ADR 0082 owns the accepted implementation decision; release evidence remains
outstanding until the candidate passes independent review, hosted checks, merge, and tag.

### What an isolation folder would mean

`pics`, `vids`, and `dups` established a pattern: move a file aside within the collection, never
delete it, record the move in the append-only journal, keep it reversible, and keep reporting it.
Extending that pattern to damaged media is plausible but is **not decided**, and the naming
exploration below is recorded so it is not repeated from scratch.

The candidate principle is **one folder per disposition, not per operation.** `dups` is fed by two
different commands with different matching rules and shares one folder, splitting by media type
rather than by which finder produced the file, because both produce the same disposition:
redundant, removable after evidence. Where dispositions genuinely differ — particularly in how
dangerous it is to empty the folder — separate folders are justified on the same reasoning.

A second candidate principle is that **isolation is only for files proven not-good.** Anything
unproven should stay in the active folders with a standing warning, because removing possibly
perfect media from active use is a worse error than a noisy report.

Applying both principles, a folder asserting data loss would need to *exclude*:

- **undecodable but unproven** files, such as a destroyed header or an unreadable index. The tool
  can prove it cannot decode them; it cannot prove data is gone, and a specialist tool may recover
  them entirely. Asserting loss here would be a false claim.
- **unsupported formats**, where the format is recognized but the local runtime has no decoder.
  Nothing is wrong with those files.
- **merely mislabeled** files, which are healthy and need only a rename.

If undecodable-but-unproven media should also be shelved, it requires its own folder and an honest
name meaning *cannot be verified* rather than *is broken*. That is a separate decision.

Names considered for the proven-loss folder, with the reasoning: `errs` and `fail` describe the
event or the report rather than the file's condition; `bugs` belongs to software defects, not
media; `warn` is a severity and the wrong one; `junk` implies worthlessness and invites deletion of
files that must never be deleted automatically; `dead` implies unopenable, which is untrue of a
file that still renders most of its content; `lost` reads as missing files rather than damaged
ones; `gaps` fits truncation but not corruption. `loss` describes the condition itself, is accurate
for both partial and total damage, claims nothing about worth, and carries permanence. It is the
leading candidate but is not adopted.

Names considered for a folder holding originals superseded by a byte-changing operation: `orig`,
`prev`, `past`, `hist`, `asis`, `fixd`, `muxd`, and `redo`. `redo` must be rejected outright
because the tool already exposes `--undo` on every mutating command and a `redo` folder would read
as an operation queue. `fixd` and `muxd` are precise about the operation but narrow, and would
multiply as operations are added. `prev` and `asis` stay accurate across any operation but say less
about why the file was kept. No selection is made.

### Byte-changing remediation and its preservation consequences

Any operation that changes bytes creates a preservation question, and one case is easy to get
wrong.

Repairing a truncated image in place would be **strictly worse than leaving it broken**. The
repaired file has different bytes, so under directional verification the original stream becomes
absent — and it cannot be rescued by the exact displayed-image layer either, because the *source*
file is precisely the one that fails to decode, and a source that cannot be decoded can never
receive an exact-pixel claim. The result would convert a reported health finding into an
unaccounted byte stream.

Two candidate resolutions, neither adopted:

1. **Retain the original** in a dedicated folder, with the journal recording the lineage. Simple,
   consistent with the existing pattern, and requires no new evidence type.
2. **Prefix containment as evidence.** A file repaired by appending a terminator contains the
   original byte stream as an exact leading prefix, which is cheaply provable and would let
   verification account for the original without retaining a second copy. This would be a genuinely
   new evidence layer needing its own contract, algorithm identifier, and ADR, and should not be
   adopted merely to save storage.

For container conversion specifically, the existing layered contract already models the outcome
correctly and needs no new machinery: if the original is retained its bytes are still present and
the byte layer accounts for it, and if the original is discarded the strict decoded-playback layer
represents it instead, separately and honestly, without claiming container bytes or metadata
survived. The unresolved question is not verification but **primacy** — for a conversion the
original is authentic and fully valid while the derivative merely plays in more software, so it is
genuinely unclear which of the two belongs in the organized media folder and which belongs aside.
That question does not arise for a repair, where the repaired file is unambiguously the better one.

### Test evidence for the shipped detection work

Synthetic fixtures only, generated at test time and removed afterwards: a short clip muxed into a
transport stream but named `.mp4`; the same clip in Matroska named `.mp4`; correctly named `.mp4`,
`.mov`, `.mkv`, and `.ts` controls that must produce no finding, with the `.mov` control
specifically proving the shared MP4/MOV family does not false-positive; and a raw MPEG elementary
stream named `.mpg`, which must also produce no finding because it probes as an elementary-stream
format at low confidence and would otherwise be accused falsely. A non-media file bearing a media
extension belongs to the separate classification-severity release that precedes this work, not to
detection. Fixtures must use FFmpeg's native encoders rather than `libx264`, which finding CI-004
established is absent from the Fedora CI image; `.webm` cannot be produced by a native encoder at
all and must not be used as a fixture, so rename a Matroska instead. Reporting must create no
media, action history, duplicate tree, or cache state.

### Open questions

- Should damaged media be isolated into a folder at all, or reported in place indefinitely?
- If isolated, does undecodable-but-unproven media get its own folder separate from proven loss?
- For a container conversion, is the authentic original or the widely playable derivative the
  primary file in the organized folder?
- Is prefix containment worth adopting as a preservation evidence layer, or does retaining an
  original make it unnecessary?
- Should a partially readable file whose surviving content is still viewable be isolated at all,
  given that only the maintainer can judge whether the surviving portion is worth keeping?

## Duplicate finalization and collection history

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

Ordinary migration verification must continue to describe the physical target
that actually exists, including media under `dups`; silently excluding that
tree by default could hide that it contains the only representative of unique
content. Version 0.5.10 is promoted to add an explicit
`--simulate-without-dups` mode that discovers and inventories the destination
review tree, reports its files and bytes separately,
exclude those files only from destination preservation evidence, perform no
writes, and label the resulting verdict as a simulated post-finalization
outcome. It must become non-complete when removing `dups` would leave any source
content unaccounted and should provide the evidence gate consumed by a later
duplicate-finalization command.

## Migration orchestration and queues

The single-collection coordination boundary is promoted to version 0.5.11. It
owns one declared unchanged baseline and one working collection, the staged
sequence in [MIGRATION.md](MIGRATION.md), restartable stage state, explicit
human checkpoints, and one opt-in private log directory. It does not
rescue-copy media, create baseline/working trees automatically, quarantine or
delete media, hide a child command's status, or treat prior evidence as
current. Each mutating stage retains its own preview and explicit apply
boundary.

Full copying and multi-collection queues remain research. Naive recursive copy
and unconstrained collection-level parallelism are unsafe defaults. That later
work must cover:

- a declarative local manifest of source, unchanged baseline, working target,
  quarantine, and final destination rather than fragile positional queues;
- capacity and case-folded collision preflight before copying between
  case-sensitive and case-insensitive filesystems;
- resumable, no-overwrite copying with retained copy evidence instead of
  assuming `cp -R` or a Finder duplicate completed;
- explicit checkpoints before transformation, duplicate finalization, baseline
  removal, and final collection renaming;
- sequential execution by default on one physical disk, with bounded
  cross-collection parallelism only when storage topology and benchmarks show
  it will not increase contention or recovery risk; and
- restartable per-collection state whose reports remain path-private by
  default and never treat a successful prior stage as proof that current files
  are unchanged.

Automatic creation of `_base` and `_target` trees may improve usability, but
their names are policy rather than identity. The design must handle interrupted
copies, insufficient space, existing destinations, external quarantine,
cross-filesystem moves, and the fact that two copies on one device are not
independent backups.

## Organizing files beyond pictures and video

Organization currently sorts pictures into `pics`, videos into `vids`, and deliberately leaves
every other file at the collection root untouched. That behavior is correct and must remain the
safe default. Local use of rescued collections surfaced ordinary text and markup documents sitting
at the root alongside media, which raises the question of whether categorization should eventually
extend past the two media kinds.

The direction is accepted as potentially useful. No design exists, and none should be invented
before the maintainer has a clear picture of the categories worth having.

Constraints any future design must satisfy:

- **Tool-owned state is never categorized or moved.** The collection action log, the derived cache
  and its lock, staging databases, collection configuration, and explicitly requested log files are
  pymo's own artifacts. Packaged ignore defaults already protect them and must continue to.
- The four-character folder convention would need a vocabulary for any additional category, and
  each new folder inherits the same protection, collision, verification, and undo obligations that
  `pics`, `vids`, and `dups` already carry.
- Categorization must keep using content-signature-first classification with extension fallback,
  never extension alone, exactly as media classification does today.
- Files that remain unknown or ambiguous must keep their current behavior of staying at the root
  untouched. A catch-all folder that silently absorbs anything unrecognized would be worse than
  the present honest default.
- Adding a category in a later release changes where an already organized file belongs. The undo
  contract is driven by recorded actions rather than current policy, so recategorization must not
  retroactively reinterpret history.

Open questions: which categories genuinely earn a folder; whether documents belong in a media
collection tool at all or are better left alone; whether a catch-all is ever desirable; and how a
newly added category should treat files a previous release already left at the root.

## Persistent diagnostic logging

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

## AI-tool repository coordination

**Resolved by [ADR 0077](adrs/0077-multi-assistant-coordination.md).** `AGENTS.md`
is the single authoritative instruction file; a tool-specific entry point is
navigational rather than normative. Assistant branches carry a `claude/` or
`codex/` prefix; ADR numbers are reserved when a branch starts and re-checked
against the target branch before merge; each release has one owner and one
reviewer, with the reviewer reporting findings rather than committing to the
branch; evidence and tests settle technical disputes while the maintainer is the
final product and policy tiebreaker; and any tool-specific local handoff stays
outside Git when it contains private acceptance data.

One part was deliberately left unresolved rather than decided. A common `.ai`
directory with `.claude`/`.codex` symlinks was considered and not adopted:
symlink behavior, host-tool discovery conventions, POSIX portability, and
conflicting generated settings are all unexamined, and none of them need to be
settled while a delegating entry point per tool works. Revisit only if a future
host tool cannot be served that way.

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
