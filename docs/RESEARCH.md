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

## Container truthfulness, media remediation, and safe transformation

### Why this is open

Validation detects a still image whose decoded format disagrees with its filename extension and
reports `extension_content_mismatch`. The equivalent video check is only category-level:
classification asks whether the detected content and the extension are both video, so a transport
stream named `.mp4`, a Matroska named `.mp4`, or a QuickTime file named `.webm` are all accepted
in silence. Local acceptance work surfaced a real instance — a file whose bytes are an MPEG
transport stream, whose name claims MP4, which decodes without a single error, and which the
exact-video finder conservatively skipped because it declares an empty timed-metadata track.
Nothing about that file is unsafe or damaged. The report was simply silent about the one thing
that was untrue: its name.

The same work surfaced two still images that fail full decode with the identical finding code and
exit status, despite being nothing alike. In one, a large share of the image rows are genuinely
absent and unrecoverable. In the other, every row decodes and only the two-byte end-of-image
terminator is missing, so the picture is visually complete and strict decoders reject it on
principle alone.

Together these define one problem: pymo can prove what a file *is*, but has no vocabulary for
telling the user what to *do* about it, and no mechanism for doing it safely.

### Stage 1 — video container detection

Standard validation already runs ffprobe on every video, so the container family is available at
no additional cost. The check compares the demuxer family ffprobe reports against the family
implied by the extension, reusing the existing `extension_content_mismatch` code and warning
severity.

The comparison must be **family-level**, never exact-string. Several extensions legitimately
share one demuxer:

| Extension | Expected `format_name` family |
| --- | --- |
| `.mp4`, `.m4v`, `.mov`, `.3gp` | `mov,mp4,m4a,3gp,3g2,mj2` |
| `.mkv`, `.webm` | `matroska,webm` |
| `.ts`, `.m2ts`, `.mts` | `mpegts` |
| `.avi` | `avi` |
| `.wmv` | `asf` |
| `.flv` | `flv` |
| `.mpg`, `.mpeg` | `mpeg` |

An exact-name comparison would emit a mismatch for every legitimate `.mov`, because ffprobe
reports the whole MP4/MOV family for all of them. Two consequences follow and should be stated in
the implementing ADR rather than discovered later:

- MP4 versus MOV, and Matroska versus WebM, are **not distinguishable** by this method. That is
  acceptable: both pairs are genuinely the same container family, and a name inside its own family
  is not a lie worth reporting.
- `.ts` versus `.m2ts`/`.mts` are also reported identically as `mpegts`, even though BDAV streams
  use 192-byte packets with a timestamp prefix while plain transport streams use 188-byte packets.
  Distinguishing them requires packet-level inspection and is deliberately out of scope; the
  detector should not claim a precision it does not have.

A mismatch remains a **warning**, never an error. A misdescribed container is not corruption, the
media is not damaged, and exit status must not change.

### Stage 2 — actionable guidance

Findings today state what is wrong. They should also state what can be done, without performing
it. Each finding gains a short, deterministic remediation hint — for example, that a container
mismatch can be corrected by renaming to the truthful extension, or that an image missing only its
terminator is a candidate for completion. Guidance must never appear for cases where the safe
action is unknown, and must never be phrased so that an unsupported format reads as corrupt.

Guidance is report-only and path-private under the existing rules.

### Stage 3 — reversible extension normalization

Renaming a file to its truthful extension changes no bytes, is trivially reversible, and is
already the kind of operation the renamer owns and journals. It is therefore the safest possible
remediation and should ship before any transformation exists.

Constraints:

- Only when content identity is certain — a confidently detected container family with an
  unambiguous canonical extension. An ambiguous or unrecognized detection is left alone.
- Dry-run by default, `--apply` to act, recorded as an ordinary reversible `RENAME` action in the
  collection journal, verified after apply, with existing collision naming.
- Must not fight the deterministic renamer: normalization changes only the extension, never the
  generated stem, and the two must agree on ordering so a normalized file is not renamed back.
Extension correction is a **separate narrow command**, not an option on `rename`. The two change
different kinds of truth: `rename` decides what a file is *called*, while extension correction
decides what a file *claims to be*, and folding them together would let one silently perform the
other. The safe order is validate, then correct extensions, then organize, then rename, so every
later stage sees a file whose name no longer lies. `rename` continues to leave extensions
untouched. The command's name is still open.

### Stage 4 — container remux as an irreversible transformation with preserved lineage

Remuxing rewrites a media stream into a different container without re-encoding. It is fast,
loses no quality, and makes files playable in players that reject the original container. It also
produces a **new byte stream**, which places it in a different safety class from renaming.

The critical realisation is that **the existing layered preservation contract already models this
correctly, and no new verification machinery is required**:

- If the original file is retained, its byte stream is still physically present, so
  `verify-migration` continues to account for it at the byte layer with no special knowledge.
  The transformation is invisible to preservation, exactly as it should be.
- If the original is later discarded, the byte layer legitimately loses that stream and the strict
  decoded-playback layer represents it instead — which the tool already reports honestly and
  separately, and which already refuses to describe container bytes or metadata as preserved.

So the design is: **remux never deletes.** The original moves into a retained tree and the new
file takes its place in the working layout. The operation stays fully reversible while the
original exists — undo restores it and removes the derived file — and becomes irreversible only
at the separate moment the retained original is discarded, which must route through the same
quarantine-first, evidence-gated, explicitly confirmed finalization ceremony as duplicate
disposal, and be recorded as an irreversible audit event.

The action journal carries the lineage. A transformation action should record both file
identities, the equivalence evidence that justified it (the shared versioned playback algorithm
and the native tool runtimes that produced it), and the direction of derivation. That record is
what lets a future collection-history view explain why two files with identical playback exist,
and what lets a finalization command recognise that discarding the retained original is the
irreversible step rather than a routine cleanup.

The retained originals live in `fixd`, a four-character tree beside `pics`, `vids`, and `dups`,
mirroring the same `pics`/`vids` subfolder layout. `fixd` names the outcome of the event exactly
as `dups` does: both trees hold the file that was set aside, and the name says why. A file is
paired with its replacement by **stem**, not by full filename, because a remux legitimately
changes the extension.

`fixd` is deliberately scoped to originals superseded by a **repair**. The membership rule for the
tree is that new bytes replaced old bytes, and repair is only a subset of that; a future
convenience transformation such as a compatibility transcode would supersede an original that was
never broken. If that capability is ever added, it takes its own tree rather than stretching this
name, which also keeps "I repaired this" and "I converted this for convenience" distinguishable at
a glance. The implementing ADR must record this scope explicitly.

A rename never places anything in `fixd`. Renaming changes no bytes, so the journal alone can
reconstruct the prior state exactly on undo, and copying the file would double storage to preserve
a filename that is already recorded. The rule is that a tree holds only what the journal cannot
reconstruct.

Remuxing must remain opt-in per file or per finding. It must never run automatically, never be
implied by validation, and never be applied to media whose streams the tool does not fully
support — the conservative unsupported-case boundaries that govern the exact-video finder apply
unchanged.

### Stage 5 — still-image terminator completion

An image whose rows all decode but whose end-of-image marker is absent can be completed by
appending the two-byte terminator. The result is a file that strict decoders accept, with pixel
content identical to what the damaged file already produced.

Eligibility must be narrow and provable: every row decodes under a permissive read, the only
defect is the absent terminator, and the appended bytes are exactly the canonical marker. An image
that is genuinely missing rows is **not** eligible — that damage is not repairable by completion,
and offering it would be misleading.

This carries a preservation subtlety that is easy to miss and must be handled explicitly. A
completed file has different bytes from the original, so under directional verification the
original byte stream becomes absent. It cannot be rescued by the exact displayed-image layer
either, because the *source* file is precisely the one that fails to decode, and a source that
cannot be decoded can never receive an exact-pixel claim — the layer would report unproven rather
than covered. Repairing in place would therefore convert a reported health error into an
unaccounted byte stream, which is a strictly worse outcome.

Two candidate resolutions, both worth evaluating before implementation:

1. **Retain the original**, exactly as remux does, in `fixd` with the same journal lineage.
   Simple, consistent, and requires no new evidence type.
2. **Prefix containment as evidence.** A completed file contains the original byte stream as an
   exact leading prefix, which is provable cheaply and would let verification account for the
   original without retaining a second copy. This is a genuinely new evidence layer and would need
   its own contract, algorithm identifier, and ADR; it should not be adopted merely to save space.

### Ordering constraints

These stages have real dependencies and should not be reordered for convenience:

1. Detection precedes guidance — nothing can be advised about a condition that is never reported.
2. Guidance precedes normalization — the user should see the finding before a command offers to
   act on it.
3. **Normalization precedes transformation.** A file must carry a truthful extension before it is
   remuxed, so that a mislabeled container is never baked into organized layout, deterministic
   names, or duplicate analysis under a name that lies about it.
4. Transformation precedes any discard, and discard happens only through the finalization
   ceremony, never as a side effect.

### Test plan

Synthetic fixtures only, generated at test time and removed afterwards:

- A short clip muxed into a transport stream but named `.mp4`; the same clip in Matroska named
  `.mp4`; correctly named `.mp4`, `.mov`, `.mkv`, and `.ts` controls that must produce **no**
  finding; and a `.mov` control specifically proving the MP4/MOV family does not false-positive.
- Fixtures must use FFmpeg's native encoders rather than `libx264`, which finding CI-004 already
  established is absent from the Fedora CI image; the existing `mpeg4` fixture approach applies.
- A still image truncated before its terminator with all rows intact, and a second truncated so
  that rows are genuinely missing, proving the two are classified differently and that only the
  first is offered completion.
- Zero-mutation proofs for detection and guidance: no media, action history, duplicate tree, or
  cache state may be created by reporting alone.
- Round-trip proofs for normalization: apply, verify, undo, and confirm the original name and
  identity return exactly.
- Lineage proofs for transformation: after a remux with a retained original, a fresh directional
  verification still accounts for every source byte stream with no reliance on the playback layer.

### ADRs required

One per durable decision, numbered from the next free entry:

- container family comparison, including the pairs it deliberately cannot distinguish;
- remediation guidance as report-only advice that never becomes ignore policy;
- reversible extension normalization and its ownership relative to `rename`;
- the `fixd` and `errs` trees, their scope boundaries, and their relationship to `dups`;
- container remux as a journaled, reversible-while-retained transformation whose irreversibility
  begins only at discard;
- still-image terminator completion and the chosen preservation resolution.

### Open questions

- Should extension normalization be an option on `rename` or a separate remediation command?
- Should a future non-repair transformation take its own tree, as the current scoping assumes, or
  should `fixd` widen to cover every superseded original?
- Is prefix containment worth adopting as a preservation evidence layer, or does retaining the
  original make it unnecessary?
- Should a remux ever be offered for a container the tool can decode but whose streams it does not
  fully support, or is the conservative skip boundary absolute?
- How should guidance describe a declared-but-empty metadata track, which is accurate to report
  yet carries no payload and is a strong candidate for safe automatic handling?

## Reversible quarantine for unresolvable media

### The problem it solves

A collection containing permanently damaged media returns a health-error exit status on every
validation, forever. That is honest, but it destroys the signal: once a collection always reports
errors, a *newly* appearing corruption is indistinguishable from damage the maintainer already
knows about and has already judged. Quarantine exists to restore that distinction, not to make
findings disappear.

### It is the existing isolation pattern, not a new one

`dups` established the shape: move the file aside within the collection, never delete it, record
the move in the append-only journal, keep it reversible, and keep reporting it. `fixd` reuses that
shape for originals superseded by a repair. Quarantine reuses it a third time, in `errs`, for
media that cannot be repaired and has no working replacement.

The three trees are distinguished by one question — does a usable version of this content exist in
the active folders?

| Tree | Usable version exists? | Disposition |
| --- | --- | --- |
| `dups` | yes, byte-identical or content-identical | removable after evidence and ceremony |
| `fixd` | yes, a repaired replacement | authentic bytes; removable only after ceremony |
| `errs` | **no** | never removable automatically; needs human judgment |

### Why it is not an ignore rule

ADR 0058 forbids converting a health finding into ignore configuration, and quarantine must not
become one by the back door. The distinction is precise: an ignore rule makes pymo **stop
looking**, while quarantine makes pymo **keep looking and report separately**. A quarantined file
is still discovered, still validated when asked, still hashed for preservation, and still carries
the finding code that justified its isolation in the journal. Nothing is forgotten; the shelf is
labelled.

### Preservation is unaffected

Because quarantine moves a file within the collection, directional verification continues to find
and account for its bytes exactly as it does for `dups` today. No new evidence layer, no journal
consultation, and no special verification logic is required.

### Exit status

Fresh validation of the active media reports what is true of the active media. Once damaged files
are quarantined, the active set genuinely has no error-severity findings, so status 0 is accurate
rather than generous. Two rules keep that honest:

- every validation run prints a standing quarantine summary — how many files are held, and the
  finding codes that put them there — whether or not anything else is reported;
- an explicit strict mode re-validates the quarantined media and returns status 1 if any of it
  still reports an error, so the stricter question remains askable at any time.

The existing contract is otherwise unchanged: 0 means no error-severity finding in scope, 1 means
health errors, 2 means the command could not run safely.

### Command shape

Quarantine follows every existing mutating command: dry run by default, `--apply` to act, `--undo`
to restore, complete preflight before mutation, descriptor-relative atomic no-replace moves,
post-apply verification, and one journal entry per action recording the finding code that
justified it. Eligibility should require a **fresh** validation error rather than cached health,
for the same reason migration sign-off requires fresh evidence: an old failure does not prove the
bytes are still unreadable now.

### Open questions

- Should quarantine act only on files a fresh validation reports as errors, or should the
  maintainer be able to nominate a specific file explicitly?
- Should quarantining a file require that a repair was attempted and failed, or is it independent?
- Should the standing quarantine summary appear in `scan` output as well, so a first-run report
  discloses held media without a validation pass?
- Does an `errs` file ever leave the collection, and if so, does that route through the same
  irreversible finalization ceremony as duplicate disposal?

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
