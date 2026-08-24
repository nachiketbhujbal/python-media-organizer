# python-media-organizer handoff

## Project scope

This repository is the complete durable source for the Python package. Future
work should rely on this handoff, the project instructions, source modules, and
tests; no earlier task or machine-specific path is required.

Private media-collections are never project fixtures and must never be moved
into this repository or named or described in source, tests, documentation,
logs, or Git history.

The primary product outcome is safe, local preservation when a media
collection is copied or rescued between storage locations and then reorganized,
renamed, validated, or deduplicated. The roadmap now treats directional
migration verification as the next product subsystem after the version 0.4
corruption-tolerant evidence and shared-cache foundation. Optional metadata
enrichment, perceptual similarity, and local AI remain secondary to proving
that source content is accounted for.

Migration-verification reports must expose ignored and policy-excluded entry
points and define their verdict relative to the declared media-collection
scope. They must not silently turn system-managed or ignored trees into proven
absence, and they must not claim whole-device recovery.

## Product decisions

The package is named `python-media-organizer`, imports as `pymo`, exposes the
`pymo` command, and includes the version 0.5.3 layered preservation release.
The package is a deliberately local-first tool for personal media collections.
Git tags are the authoritative version source; package code and `[project]` do
not contain a static version.

Version 0.4.0 makes directory traversal failures visible in scan reports and
places non-mutating validation first in every scan recommendation plan. Existing
validation behavior continues after known per-file decoder failures, and direct
regression coverage proves a damaged video does not prevent a healthy neighbor
from being checked. No health finding is converted into ignore configuration.

Version 0.4.1 adds a shared fail-closed filesystem discovery boundary.
Organization, renaming, and undo planning stop before mutation when recursive
enumeration is incomplete. The exact duplicate finders stop before creating
cache, duplicate directories, or action history when their owned flat media
directory cannot be listed completely. Organizer verification also refuses an
apparently complete verdict after a traversal failure. Report-only scan and
validation retain their distinct evidence-collection behavior.

Version 0.4.2 closes the remaining entry-level gap exposed by a read-only
damaged-filesystem acceptance check. Every enumerated name in a mutation,
undo, duplicate-analysis, or organizer-verification boundary now requires an
explicit no-follow metadata result; a name that returns `ENOENT`, another
metadata error, or a changed walk category stops the command before state is
created. Report-only scan and validation continue to count such names as
unreadable evidence and process readable neighbors.

Version 0.4.3 extracts cache filesystem coordination into a shared cache
service and introduces schema version 1. Generic derived evidence
is keyed by content SHA-256, evidence type, algorithm, and runtime. Stable file
observations retain an explicit analysis scope, relative path, device/inode,
size, modification/change times, and optional verified byte hash. Valid legacy
video caches remain read-only during lookup and migrate inside the private
staged database only when a subsequent fingerprint is successfully saved.
Migration uses an explicit SQLite savepoint, and schema validation rejects
non-standard JSON values and non-canonical observation paths.

Version 0.4.4 adds `pymo cache status COLLECTION [--cache PATH] [--json]`.
It inspects a
descriptor-pinned SQLite snapshot without creating a cache lock or any other
state, validates known exact-video payloads, reports aggregate algorithm and
observation freshness plus evidence coverage, and leaves runtime compatibility
to the consuming command. Missing and healthy caches return 0, invalid cache
health returns 1, and setup errors return 2. Human and schema-1 JSON reports do
not expose collection roots, cache paths, filenames, scopes, hashes,
algorithms, or runtime strings.

Version 0.4.5 adds `pymo cache warm videos COLLECTION [--cache PATH]`. It
fingerprints every safely discovered flat video instead of only duplicate
candidates, publishes each successful new exact-playback record immediately,
and performs no grouping or media mutation. An explicit cache path anchors the
database and sibling lock outside the analyzed collection so a read-only source
receives no derived state. The exact-video finder accepts the same external
cache path; it cannot be combined with `--no-cache`. Normal output is aggregate
and path-private;
`--show-files` explicitly reveals collection-relative failures. Incomplete
media coverage or unsafe cache state returns 1, invalid setup returns 2, and an
empty organized video directory returns 0 without creating cache state.

Version 0.4.6 activates whole-file SHA-256 observations in the shared cache.
An observation is reusable only for the same path-private collection root
identity, relative path, device, inode, size, modification time, and change
time. Video inspection publishes new hashes in configurable bounded atomic
batches and `--no-cache` disables both hash and fingerprint records. Before an
applied exact-video result may create any state, every reused hash involved is
read and verified again through a stable descriptor. Checksum scan may reuse
the same current observations from the local or an explicit external cache,
but remains strictly read-only and never persists its newly computed hashes.

Version 0.4.7 establishes `pymo.cache` as the cohesive package boundary for
disposable derived state before additional producers are added. A curated
facade exposes supported storage operations, while focused modules own the
schema/publication service, hash observation policy, read-only status,
deliberate warming, and nested CLI. The architecture review retains the
existing duplicate-media boundary, root command coordinators, shared safety
foundations, and authoritative action journal because those responsibilities
already have distinct lifecycles. Shared media classification moves out of the
organizer command into its own foundation module so cache, scan, validation,
rename, and duplicate code no longer depend on organizer ownership for that
policy. No CLI, schema, configuration, action-log, cache-path, or media behavior
changes.

Version 0.4.8 caches normalized ffprobe structure by content SHA-256, persisted
probe algorithm, and exact ffprobe runtime. Compatible payloads are decoded
through a strict typed schema before reuse; a runtime or algorithm change is a
cache miss, and malformed selected evidence stops safely. Newly computed hash
observations and probes from each bounded inspection batch publish together in
one locked atomic cache update. Output distinguishes compatible probe records,
actual reused probes, computed probes, and newly persisted records without
exposing paths. Cache status recognizes and validates probe evidence while
remaining runtime-agnostic and zero-write.

Version 0.4.9 adds the equivalent safe acceleration boundary for exact images.
Displayed-pixel fingerprints are keyed by complete-file SHA-256, persisted RGBA
normalization algorithm, and exact Pillow runtime. Hash observations and newly
decoded pixel evidence publish together in bounded atomic batches. The finder
supports its collection-local cache, an explicit external cache, or a complete
`--no-cache` opt-out. Before an apply may create state or move an image, every
reused byte hash involved is freshly descriptor-pinned and recomputed. Strict
payload validation also makes cache status recognize malformed or stale image
evidence without invoking Pillow. Shared writable-target policy and descriptor
hashing now live in the cache subsystem rather than video command ownership.

Version 0.4.10 generalizes deliberate cache warming to
`pymo cache warm {images,videos,all} COLLECTION`. Image inspection and cache
publication are separated from duplicate grouping, so every selector remains
strictly cache-only. Every selected layout and media set is preflighted before
the first write; combined warming also resolves required native video tools
before publishing image evidence. Empty selections create no cache or lock,
normal output remains aggregate and path-private, external caches remain
supported, and per-file failures retain resumable evidence while returning
incomplete coverage.

Version 0.4.11 records every freshly completed standard or full validation as
strict disposable evidence. The record links complete-file SHA-256 and exact
file observation to profile, semantic classification context, applicable
Pillow/ffprobe/FFmpeg versions, findings, outcome, and UTC completion time.
Content hash alone is deliberately insufficient because byte-identical files
with different extensions can produce different classification findings.
Normal validation never consumes old health as a substitute for a current
probe or decode. `--cache PATH` moves derived writes outside the collection;
`--no-cache` restores a zero-cache-read/write run. Validation JSON schema 2
reports fresh execution and cache-publication facts without paths.

Version 0.4.12 adds explicit `pymo validate --reuse-validation`. It reuses only
strictly compatible evidence with an exact file observation, content SHA-256,
profile, semantic context, validation algorithm, and applicable runtime. Every
candidate hit is reopened through the stable descriptor boundary before use;
changed or incompatible files fall back to fresh validation and publication.
Ordinary validation remains fresh, and fresh validation remains the required
mode for final migration sign-off.

Version 0.4.13 adds targeted `pymo cache refresh` operations for image
fingerprints, video fingerprints, standard validation, and full validation.
Image/video refresh bypasses persistent selected evidence and recomputes hashes
plus the applicable pixel, probe, and playback records. Validation refresh uses
the ordinary always-fresh descriptor-pinned path. Atomic selected-key upserts
preserve unrelated cache types, algorithms, runtimes, profiles, and collection
scopes. Refresh keeps the external-cache, privacy, bounded-publication,
organized-media ownership, and zero media/action-history mutation boundaries.

Version 0.5.0 adds report-only
`pymo verify-migration SOURCE DESTINATION`. It freshly hashes every in-scope
regular file in two distinct, non-nested trees through stable, no-follow,
collection-anchored descriptors and compares SHA-256-plus-length identities
independently of roots, paths, and filenames. Unique coverage is distinct from
duplicate multiplicity and destination-only content. Reports distinguish
complete in-scope coverage, definitely incomplete coverage, and unproven
filesystem evidence; schema-1 JSON and normal text remain root- and
filename-private unless relative path disclosure is explicit. Neither tree
receives cache, lock, configuration, action-history, duplicate-tree, or media
writes. Version 0.5.0 is exact-byte scope only; versions 0.5.1 through 0.5.3
subsequently add media equivalence and final layered sign-off.

Version 0.5.1 layers exact displayed-image evidence over source byte identities
that lack a destination byte representative. One representative per eligible
unique byte stream is freshly decoded through the same EXIF-transposed,
single-image RGBA dimensions-plus-pixels algorithm used by the exact-image
finder. Exact pixel coverage, missing pixels, and uninspectable source or
destination candidates are reported separately from byte coverage. Schema-2
JSON retains path privacy; relative image differences require `--show-files`.
The image layer does not claim metadata, encoding, container bytes, or original
file bytes survived, and it does not yet replace the byte verdict or exit
status. The shared normalization now lives in `src/pymo/image_content.py`
because duplicate and migration domains both consume it.

Version 0.5.2 adds the corresponding strict decoded-video layer for configured
video-extension source identities whose bytes are absent. It freshly probes one
representative per unique source and destination byte stream, then fully
fingerprints every supported source and only structurally relevant destination
stream through local FFmpeg. Supported remuxes can match under
`exact-playback-v2`; different frames, normalized timing, or decoded audio do
not. Schema-3 output keeps playback results separate from byte preservation and
does not claim source containers, metadata, codec bitstreams, or original bytes
survived. Native tools resolve only when video work is required, decoding is
sequential and timeout-bounded, and migration comparison never uses or writes
cache evidence. Shared probe/fingerprint primitives now live in
`src/pymo/video_content.py`; duplicate and migration policy remain separate.

Version 0.5.3 defines the final `layered-exact-preservation` contract. Each
unique source byte identity is accounted for by exact bytes, exact displayed
pixels, or strict decoded playback without hiding the lower-layer result. A
fresh second discovery validates every hashed file state, in-scope directory
namespace, unsafe entry category, and collection-root identity after media
decoding while refreshing non-blocking exclusion counts.
The final verdict is complete only when all declared source content is
accounted for and no unreadable, unstable, unsupported, or incomplete evidence
remains. Migration comparison still reads no cache and writes no state.
Completion is only eligible for human sign-off over stable namespace-visible
collection content; it neither proves whole-device recovery nor authorizes
automatic deletion.

Version 0.5.4 records multi-assistant repository coordination in ADR 0077 and
reconciles the overlapping research and roadmap planning records so each subject
has one home. `AGENTS.md` remains the only authoritative instruction file, a
tool-specific entry point states no rule of its own, an assistant branch carries
a `claude/` or `codex/` prefix that the merge commit preserves, ADR numbers are
claimed in a branch's first commit, each assistant adversarially reviews the
other's pull request by default, and every subagent reads `AGENTS.md` and
`HANDOFF.md` completely. Runtime behavior, packaging, configuration, and tests
are unchanged.

Version 0.3.19 aligns the roadmap's retained release ledger, the README's
next-work guidance, and the completed review record without changing runtime
behavior. Version 0.3.18 prefixes every physical line of normal human-readable
command logging with an ISO timestamp by default, retains `--timestamps` as an
explicit compatible spelling, and adds `--no-timestamps` as the console opt-out.
Structured JSON, help, version, and argument-parser output remain unprefixed,
while explicitly requested log files remain timestamped regardless of the
console choice. Version 0.3.17 adds `--summary` to both duplicate finders
for aggregate, path-private scans, applies, and undo previews without changing
dry-run, matching, cache, action-log, or verification semantics. Version 0.3.16
reports reusable fingerprint-cache records, fingerprints
required, and newly persisted records separately; `--no-cache` states its
complete no-read/no-write boundary without lookup or update claims. Version
0.3.15 adds independent, path-private monotonic durations for the
exact-video discovery, probing, fingerprinting, planning, apply, and
verification stages. Only stages that actually execute are reported, while the
CLI retains its whole-command runtime. Version 0.3.14 separates active-item
heartbeats from completed-work status and
withholds ETA projections until three items have completed. Heartbeats report
only the active item, completed count, and elapsed time, so a long decode never
repeats stale throughput or ETA. Version 0.3.13 replaces per-item forced
progress rows with at most ten stable
count milestones, genuinely due interval rows, and one final completed-work
row. Version 0.3.12 serializes cache access with a dedicated collection lock and
publishes fully synced, validated updates through atomic no-replace or verified
exchange operations without writing in place. Version 0.3.11 opens an existing
video fingerprint cache read-only through a
stable collection-anchored descriptor and fails closed if its pathname changes
or is unsafe. Version 0.3.10 pins Pillow image decoding to stable collection-anchored
descriptors. Version 0.3.9 records that GitHub Free cannot enforce branch
protection on this private repository and specifies the no-bypass `main`
ruleset to activate after a Pro upgrade or public transition. Version 0.3.8
pins video classification, hashing, ffprobe, and frame/audio fingerprinting to
stable collection-anchored descriptors. Version 0.3.7 limits automatic GitHub
Actions runs to pull requests targeting `main` and pushes to `main`, retains
deliberate manual dispatch, and caps each platform job at ten minutes while the
repository is private. Version 0.3.6 adds a pinned GitHub
Actions quality gate, adopts short-lived branches with CI-verified merge
boundaries, and streams descriptor-backed classification through portable
`file` standard input rather than asking the utility to classify `/dev/fd`.
The gate verifies Ubuntu, Fedora, and macOS representatives with the locked
release commands; WSL uses the supported Linux execution model, while native
Windows remains outside the current platform boundary. Version 0.3.5 makes scan
recommendations list every applicable action in safe
workflow order instead of suppressing rename advice when organization is also
needed. Version 0.3.4 separates evaluated research, promoted release plans, shipped
behavior, adversarial findings, and architecture decisions under the indexed
`docs/` tree, and establishes one primary purpose per patch release. Version
0.3.3 pins validation classification and decoder reads to stable,
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
14. `scan` never writes media, action history, or cache state, reports directory
    traversal failures, and recommends fresh validation before mutation.
    Exact-video previews may persist disposable fingerprints by default so
    later preview or apply runs resume; `--no-cache` disables both cache reads
    and writes.
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
23. Validation is media-non-mutating and independent of organized layout.
    Fresh validation evidence is disposable cache state; `--no-cache` restores
    the zero-state boundary. Repair or quarantine requires a future ADR and
    reversible mutation design.
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
  README.md
  AGENTS.md
  HANDOFF.md
  docs/
    README.md
    CHANGELOG.md
    CODE_REVIEW.md
    CONTRIBUTING.md
    RESEARCH.md
    ROADMAP.md
    adr/
  src/pymo/
    __init__.py
    __main__.py
    cli.py
    classification.py
    collection.py
    config.py
    default_config.toml
    logging_config.py
    progress.py
    discovery.py
    file_safety.py
    image_content.py
    cache/
      __init__.py
      cli.py
      hashes.py
      images.py
      paths.py
      probes.py
      service.py
      status.py
      validation.py
      warm.py
    migration/
      __init__.py
      coverage.py
      images.py
      inventory.py
      report.py
      videos.py
    action_log.py
    organize.py
    rename.py
    scan.py
    validate.py
    verify_migration.py
    video.py
    video_content.py
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
pymo cache status COLLECTION
pymo cache warm {images,videos,all} COLLECTION
pymo cache refresh {images,videos,validation-standard,validation-full} COLLECTION
pymo validate COLLECTION
pymo verify-migration SOURCE DESTINATION
pymo find-image-duplicates COLLECTION
pymo find-video-duplicates COLLECTION
```

The four mutating tools support dry-run/apply behavior and `--undo`, which is
also a preview unless combined with `--apply`. `scan` and `cache status` are
strictly read-only. `validate` may write fresh disposable evidence unless
`--no-cache` is explicit; `cache warm` and `cache refresh` write only
disposable cache state. Neither changes media or action history. Global
`--verbose`, `--quiet`,
`--log-file PATH`, `--timestamps`, `--no-timestamps`, `--config PATH`, and
`--show-ignored` options go before the subcommand. `--show-ignored` and
command-specific options are also accepted by the selected command after its
collection argument. Configuration and ignored-path options are not applicable
to `cache status` and are rejected rather than silently ignored.

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
the optional config, disposable shared derived cache and lock, and collection-named
action log. These names are intentionally not configurable because cross-tool
ownership, portable undo, and compatibility require one interpretation.

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

The source contains only eight assigned module constants: the config schema,
action-log schema, shared cache schema, shared exact-video evidence type,
video fingerprint algorithm, cache-status report schema, scan-report schema,
and validation-report schema versions or identifiers. Each is an
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

The promoted future direction includes a path-private collection-history
synopsis over this journal and a separate duplicate-finalization command. Any
irreversible disposal must remain outside the duplicate finders, require fresh
preservation evidence and explicit confirmation, and be recorded as an
irreversible audit event without pretending it can be undone. Its journal
schema and quarantine/deletion ceremony are not yet designed or implemented.
Normal verification continues to include `dups` because it reports the real
target namespace. Promoted future work adds an explicit zero-write
`--simulate-without-dups` mode that inventories that tree but prevents it from
satisfying coverage and clearly reports a simulated post-finalization verdict.

Later promoted work also includes actionable validation guidance, reversible
extension normalization and damaged-media quarantine designs, plus migration
orchestration over explicit baseline and working-copy state. Multi-collection
queues, copying, final naming, and cleanup remain research until capacity,
case-collision, resumability, storage-contention, and evidence-checkpoint
policies are designed. Existing organizer collisions are already resolved to
Finder-style numbered names during planning and still protected by atomic
no-replace moves during apply.

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
Every candidate is opened through a no-follow descriptor relative to the
collection root. Pillow receives a non-owning binary stream over that pinned
descriptor, and both the descriptor and pathname are revalidated after pixel
decoding. A concurrent pathname or parent-directory swap therefore cannot
redirect Pillow to unrelated local content.

Whole-file observations and displayed-pixel fingerprints use the shared cache
by default. Reuse requires matching content SHA-256, normalization algorithm,
and exact Pillow runtime. The finder accepts an external writable cache or
`--no-cache`; a reused hash participating in apply is recomputed before any
review directory, action history, or move is created.

Within an exact group it keeps the largest file, then oldest on a size tie,
then stable filename order. Extra copies move to flat readable names such as
`retained_copy(1).jpg`. The report distinguishes scanned bytes, retained
original bytes, duplicate bytes, and potentially reclaimable storage. Nothing
is deleted.

The matching, keeper policy, readable names, conservative skips, action-log
integration, and undo behavior are approved. Do not change these core choices
without an explicit user request.

Both duplicate finders accept command-specific `--summary`. It preserves
aggregate progress, counts, storage, cache/timing facts, final outcomes,
dry-run guidance, and verification status while suppressing collection paths,
filenames, run IDs, group/action listings, per-video start rows, and per-file
skip details. The same boundary applies to undo previews and applies. It cannot
be combined with `--show-ignored`, which explicitly requests path output.

## Exact video duplicates

`src/pymo/duplicates/videos.py` is implemented and owns only `vids` and
`dups/vids`. It does not require, inspect, create, validate, or modify `pics` or
`dups/pics`.

FFmpeg and ffprobe are explicit native executables. The implementation:

1. Discovers flat videos with the same conservative classifier used by the
   collection tools.
2. Computes whole-file SHA-256 as a cheap exact-byte identity and cache key, or
   reuses it only for an exact current file observation.
3. Uses ffprobe JSON for structure, dimensions, timing, orientation, audio, and
   candidate bucketing, reusing only content/algorithm/runtime-compatible
   normalized probe evidence.
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

Every inspected video carries a stable device/inode/size/time snapshot.
Classification, whole-file hashing, ffprobe, and both FFmpeg decode passes use
one no-follow descriptor opened relative to the collection root; native tools
receive an inherited `/dev/fd` input. The finder rechecks the descriptor and
pathname before grouping and during applied moves. Both exact-media finders
reject a changed file or stop an apply rather than reuse a stale exact-match
conclusion. A hash reused from disposable cache state is freshly recomputed
before an apply creates the review tree, action history, or a move.

FFmpeg input protocols are restricted to `file,pipe`, and tests assert that
decode commands contain no macOS, Windows, or X11 capture input. The tool does
not need Screen & System Audio Recording, Camera, or Microphone permission.

Preview and applied runs use collection-root `.pymo.sqlite3`. It is a derived
cache keyed by exact file observations plus content SHA-256, evidence algorithm
version, and the relevant native runtime. Fingerprints are persisted
immediately; new whole-file hashes and normalized ffprobe evidence are persisted
together in bounded batches controlled by
`performance.cache_publication_batch_size` (default 32). An interrupted preview
retains completed publications and a later `--apply` reuses them. The command
reports reusable and required hashes, actual probe reuse and computation,
candidate-relevant reusable fingerprints, and how many new records were durably
persisted. `--no-cache`
disables all cache reads and writes and emits no lookup or update claim.
`--cache PATH` instead selects an external database and sibling lock; the two
options are mutually exclusive.
Existing cache schemas and rows are validated read-only before decoding. The
read-only SQLite connection uses a stable no-follow descriptor anchored beneath
the collection root, and a pathname swap stops safely rather than redirecting
the read. An invalid cache is preserved and reported; moving it aside or
explicitly using `--no-cache` is the recovery path. FFmpeg is resolved only when
discovery finds at least two eligible videos.

Schema version 1 is shared rather than video-specific. It contains exact
schema metadata, generic derived evidence, and file-identity observations.
Validation evidence uses this generic schema with profile-specific algorithms,
canonical semantic-context/runtime namespaces, strict path-private payloads,
and exact observations; no schema migration is required.
Existing valid legacy `video_fingerprints` databases are still read without a
write; the next successful cache update migrates their rows in memory and
publishes the complete versioned database atomically. The low-level service
anchors safety to the cache directory rather than the analyzed media root, and
both exact-video warming and duplicate analysis can therefore use an explicitly
separate writable cache for a read-only source.

Cache readers share collection-root `.pymo.sqlite3.lock`; writers acquire it
exclusively and re-read the latest public database before merging a completed
update. Concurrent first writers use an exclusive create-or-open sequence and
serialize on the same verified lock. Updates are built in memory, serialized to a random private
`.pymo.sqlite3.new.*` descriptor, synced, reopened read-only, and fully
validated. A missing public cache is published with an atomic no-replace rename;
an existing cache uses an atomic exchange whose displaced identity is verified
before the prior derived database is removed. The collection directory is
synced after publication. SQLite never writes through the public pathname, and
successful runs leave no journal, WAL, shared-memory, or staging sidecars.
Interruption before publication leaves the prior cache intact and may leave an
ignored staging database for inspection; pymo does not silently remove it.

The finder mirrors image behavior for deterministic keeper choice, readable
`copy(n)` destinations, no overwrite/delete, action-log undo, post-operation
verification, and retained/duplicate/reclaimable storage reporting.

Full FFmpeg fingerprint decoding remains sequential. FFmpeg already performs
internal threading, and parallel decode processes can contend for disk and CPU,
especially on external media. Add bounded process-level decoding only after
representative benchmarks demonstrate a reliable benefit.

The finder reports required candidate-fingerprint count and bytes before
decoding, an observed aggregate rate after completed candidates, and an ETA
after at least three completed observations. A configurable heartbeat while a
single FFmpeg
subprocess remains active reports only active item, completed count, and
elapsed time; it never repeats stale rate or ETA data. Completed-work
status uses ten evenly spaced count milestones, interval-due rows, and one final
row rather than forcing output for every candidate. These reports do not include
filenames. The default interval is 15 seconds through
`performance.progress_interval_seconds`; accepted values are 1..3600.

The exact-video pipeline reports independent `Stage timing` records for
discovery, probing, fingerprinting, and planning. Applied runs also report
apply and verification when duplicate moves actually execute. These monotonic
records contain a fixed stage label and duration only; they do not disclose a
collection path or filename and do not replace the final command runtime.

## Derived cache status

`pymo cache status COLLECTION` inspects the default collection-local
`.pymo.sqlite3` without creating `.pymo.sqlite3.lock` or any other state.
`--cache PATH` selects an external cache for this inspection only; it does not
authorize another command to write there. Human and schema-1 JSON reports are
path-private and aggregate cache format/storage, evidence types and namespaces,
algorithm compatibility, file-observation freshness, evidence linkage, and
pending legacy migration.

Status opens the cache directory and public database through no-follow
descriptors in SQLite read-only mode, validates the exact generic or legacy
schema plus every known exact-video payload, and rechecks the cache and
directory identities afterward. Observation scope must match the current
collection root identity; another collection's record is stale even when its
relative path happens to match. A concurrent atomic replacement invalidates
the snapshot. Observation freshness walks collection-relative parents through
no-follow descriptors and never reads media content. Runtime compatibility is
not checked because status does not invoke FFmpeg; the exact-video command
remains authoritative for actual reuse.

A missing cache is healthy operational state and returns 0. Valid current and
legacy caches also return 0, with legacy migration reported as pending. Unsafe,
unreadable, corrupt, malformed, or incompatible caches return 1 without being
changed. Invalid collection setup returns 2. Dispatched help and parser errors
remain plain and do not receive the normal timestamped runtime footer.

## Derived cache warming

`pymo cache warm {images,videos,all} COLLECTION` deliberately populates one or
both supported evidence families. Images use the exact-image descriptor-pinned
hash and displayed-pixel inspection path over `pics`; videos use the hash,
probe, and decode path over `vids`. Inspection is separate from duplicate
grouping. Selected layouts, discovery, and any required native tool setup
complete before the first cache write. Bounded atomic publication keeps
successful evidence resumable without planning duplicates, creating `dups`,
moving media, or appending action history.

The default cache remains collection-local. `--cache PATH` selects an existing
external parent directory and anchors both the database and sibling lock there,
allowing a read-only collection to remain unchanged. Normal output does not
name paths; `--show-files` deliberately lists collection-relative failures.
Any unrepresented discovered media produces exit 1 while preserving completed
evidence. An empty selected media set returns 0 without creating state; empty
video input does not resolve FFmpeg. Image-only and video-only warming require
only their owned organized folder, while `all` requires both. The command does
not replace collection scan, validation, or preservation verification.

## Targeted cache refresh

`pymo cache refresh {images,videos,validation-standard,validation-full}
COLLECTION` forces one named evidence family to be recomputed. Image refresh
re-hashes and re-decodes displayed pixels in `pics`; video refresh re-hashes,
re-probes, and re-decodes playback in `vids`. Byte-identical content may share
one derived computation inside the current run, but persistent selected
evidence is never accepted as a hit. Validation targets run the fresh standard
or full profile over any layout and publish their current results.

Refresh performs atomic upserts and never deletes the cache, so unrelated
records survive. It supports the same external writable-cache, path-private
failure reporting, configuration, and ignored-path rules as its underlying
operation. It never creates `dups`, moves media, or appends action history.
Invalid structural cache state fails closed; refresh is deliberate
recomputation, not automatic repair or a preservation verdict.

## Collection scan

`src/pymo/scan.py` provides the read-only first-run `pymo scan COLLECTION`
report. Its fast profile inventories files, storage, extensions and detected
content types; reports layout and canonical-name readiness; summarizes review
storage and same-size duplicate potential; estimates checksum and exact-video
work; reports existing local pymo state; and recommends next commands.

`--checksums` hashes only same-size picture and video candidates and reports
exact-byte copies. It does not substitute for displayed-pixel image or decoded-
playback video matching. Current whole-file observations may be read from the
collection cache or `--cache PATH`; aggregate output distinguishes reuse from
new computation. Scan never creates a cache or lock and never persists its
computed hashes. `--json` emits stable schema version 1 without the
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
Directory traversal failures are counted and warned about instead of silently
omitted. Recommendations begin with fresh, non-mutating validation before
organization, renaming, or duplicate isolation.

## Directional migration verification

`src/pymo/verify_migration.py` coordinates report-only
`pymo verify-migration SOURCE DESTINATION`. The `src/pymo/migration/`
subpackage owns fresh stable inventory, layered byte/image coverage and
multiplicity accounting, and the root-free schema-3 report. The command never
writes cache, locks, configuration, action history, duplicate trees, or media
to either collection.

Version 0.5.0 identifies each in-scope regular-file stream by complete SHA-256
plus length. Paths, filenames, root names, and aggregate sizes are not content
identity. One destination representative may cover several byte-identical
source copies; duplicate reduction and destination-only content are reported
separately. Both trees are freshly read through collection-anchored no-follow
descriptors rather than relying on cached historical hashes.

The verdict is `complete` only for the declared in-scope byte contract,
`incomplete` when complete evidence proves source identities absent, and
`unproven` when source evidence is incomplete or destination failures could
hide a missing representative. Symbolic links are never followed. Ignored
entry points and pymo-owned state are counted but outside the byte scope; the
stricter post-transformation sign-off boundary is implemented by version 0.5.3.
Normal output reveals no roots or filenames. `--show-files` and
`--show-ignored` deliberately expose collection-relative details.

Version 0.5.1 adds the separate exact displayed-image layer for byte-missing
source identities with configured exact-image extensions. It freshly decodes
one representative per unique source and destination byte identity using
EXIF-transposed single-image RGBA dimensions plus pixels. A metadata-varied or
losslessly re-encoded image can therefore be content-represented while its
absent source bytes remain visible. Source decode failures make that layer
unproven; destination decode failures make an otherwise missing match
unproven. Schema 2 reports the layer independently and keeps command status
tied to the byte verdict until version 0.5.3 defines combined sign-off.

Version 0.5.2 adds strict decoded-video evidence for byte-missing configured
video-extension identities. It freshly normalizes supported structure through
ffprobe and streams complete displayed frames, timing, and decoded audio through
FFmpeg under `exact-playback-v2`. Structurally incompatible destination streams
are not fully decoded because they cannot match. Source inspection failures, or
relevant destination failures that could hide a match, make the video layer
unproven. Schema 3 reports exact playback independently and keeps command status
tied to the byte verdict until the version 0.5.3 final-sign-off policy.

Version 0.5.3 combines those fresh layers in schema 4, re-discovers both trees
after all media work, and bases command status on the final preservation
verdict. Exact bytes, pixels, and playback remain separately visible; missing
unknown content is incomplete, while unsupported recognized media or uncertain
filesystem evidence is unproven.

## Media validation

`src/pymo/validate.py` implements media-non-mutating
`pymo validate COLLECTION` over any collection layout. It never repairs,
quarantines, moves, renames, deletes, creates duplicate trees, or appends action
history. By default it may write only fresh disposable validation evidence;
`--no-cache` performs no cache reads or writes, while `--cache PATH` keeps
derived state outside the collection.

The standard profile uses Pillow integrity verification for supported images
and local ffprobe structure inspection for non-empty videos. `--full` also
loads every image frame and decodes selected video/audio streams completely
through local FFmpeg. Standard validation uses bounded workers; a full run
containing video reports and uses one worker so full FFmpeg decodes remain
sequential.

`--reuse-validation` is an explicit acceleration mode. It can reconstruct a
prior healthy, warning, or error result only from a strict exact match and only
after reopening the current path safely; misses are checked freshly. It is not
the default and must not replace fresh validation for migration sign-off.

Text and schema-2 JSON aggregate severity/code findings without collection
names, root paths, or filenames. `--show-files` adds collection-relative
affected paths, while `--show-ignored` remains a separate opt-in. Status 0 means
no error-severity finding, 1 means health errors or incomplete cache publication
were reported, and 2 means the command could not run safely. Animated or
multi-page images are counted, not
classified as corrupt. Unsupported recognized formats remain warnings rather
than unverified claims of corruption. Unreadable subtrees are health errors,
native-tool diagnostics are discarded, and concurrent changes supersede
decoder conclusions. Known decoder failures become per-file findings and do not
abort inspection of healthy neighboring media. Pillow and native tools read
inherited stable descriptors, not a pathname that can be redirected after
preflight. When caching is enabled, the same descriptor is freshly hashed and
its result publishes afterward in bounded atomic batches. Old health never
satisfies a normal current request. Health evidence remains distinct from
user-authored ignore policy.

## Logging

`src/pymo/logging_config.py` routes all command output through the standard
library logging package while preserving readable text expected by existing
behavioral tests.

- Default `INFO` messages go to stdout.
- Warnings/errors go to stderr.
- `--verbose` enables diagnostic `DEBUG` output.
- `--quiet` keeps only warnings and errors.
- `--log-file PATH` creates a timestamped local log only at the requested path.
- Normal human-readable command logging prefixes every physical console line
  with an ISO timestamp by default.
- `--no-timestamps` omits console timestamps; `--timestamps` remains accepted
  for compatibility and explicit invocation.
- Structured JSON, help, version, and argument-parser output remain unprefixed.
- Explicit log files timestamp every physical line, including lines contained
  inside one multi-line message, regardless of the console timestamp choice.
- `--show-ignored` explicitly adds relative ignored paths; `--verbose` alone
  never reveals them.
- No persistent log is created by default.

Automatic collection-local diagnostic logging, conventional log-level
selection, and a `--debug` alias are research items rather than current
behavior. Default logging would conflict with the present opt-in privacy rule,
report-only command guarantees, read-only collections, and two-root migration
verification unless those boundaries receive an explicit design and ADR.

Do not put media bytes or unrelated metadata into exceptions or diagnostics.
Scan JSON is the first machine-readable result contract; human command output
continues to use logging. Every normal non-JSON CLI run ends with total elapsed
time. Long stages use `src/pymo/progress.py` for aggregate file/data rates and
observed ETA. ETA requires at least three completed observations. Active-item
heartbeats contain no completed-work rate or ETA. Completed-work reports use
stable count milestones plus due time intervals and never force a line for
every item; no filenames or fabricated reference speeds enter those metrics.

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
- fail-closed recursive and flat discovery, including late traversal errors
  after visible media, enumerated ghost names, changed walk categories, and
  proof that organization, renaming, undo, and both duplicate finders create no
  new state from an incomplete namespace;
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
- adversarial image decode path swaps that prove Pillow reads the pinned
  collection descriptor rather than unrelated replacement content;
- real FFmpeg byte-copy/remux matches, different-audio and different-timing
  non-matches, corrupt and multi-audio skips, strict ownership, collisions,
  incremental preview cache, interruption recovery, cache opt-out, concise
  path-private summary output, sidecar
  behavior, cross-tool undo dependencies, missing runtime errors, and local-
  descriptor-only/no-capture command construction;
- adversarial video classification, probing, and fingerprint path swaps that
  prove unrelated replacement content is never read;
- adversarial SQLite cache path swaps that prove cache reads remain pinned to
  the original collection file and then fail closed on the changed pathname;
- concurrent-writer, interrupted-staging, cache-publication substitution, and
  lock-substitution tests that prove merged updates, durable atomic publication,
  preserved prior state, and no writes through an outside path;
- read-only cache status for missing, shared, legacy, malformed, substituted,
  externally located, concurrently replaced, current-observation, stale-
  observation, and symbolic-link-parent cases, including JSON privacy and
  proof that no cache lock or collection state is created;
- image, video, and combined cache warming for empty, complete, incomplete,
  reused, setup-invalid, and explicitly external cache runs, including proof
  that media, duplicate trees, action history, and read-only source cache state
  are not written;
- targeted image, video, standard-validation, and full-validation refresh,
  including forced recomputation, unrelated-record retention, external cache
  isolation, profile separation, selector-specific argument rejection, media
  immutability, and real FFmpeg execution;
- fresh standard/full validation evidence for healthy and invalid content,
  strict runtime/context payloads, byte-identical files with distinct
  extensions, local/external/disabled cache modes, old-health non-reuse, cache
  status recognition, JSON schema 2 privacy, and invalid-cache refusal;
- explicit validation reuse for unchanged exact matches, changed/profile/runtime
  misses, external caches, cached error outcomes, decoder non-invocation on a
  hit, post-lookup replacement rejection, and real FFmpeg full-decode evidence;
- directional fresh-byte migration coverage across renamed and reorganized
  trees, duplicate reduction and destination extras, missing content, ignored
  and pymo-owned state, symbolic links, traversal/read/change failures, root
  overlap, path privacy, and zero-write behavior;
- exact displayed-image migration coverage for metadata- and format-varied
  still images, genuinely different pixels, byte-represented no-op cases,
  source/destination decode failures, schema-2 privacy, and unchanged
  duplicate-finder semantics;
- strict decoded-video migration coverage for supported remuxes, different
  audio, invalid structure, native-tool demand, decode timeouts, schema-3
  privacy, zero writes, and unchanged video-finder/cache behavior;
- unified CLI version, default no-log behavior, explicit logging, verbose mode,
  quiet mode, global option forwarding, default ignored-name privacy, and
  explicit relative ignored-path output;
- command runtime summaries, default and explicitly controlled ISO console
  timestamps, timestamped multi-line file logs, deterministic duration/rate/ETA
  formatting, exact-video stage timing, stable
  ten-milestone completed-work cadence, no forced per-item rows, early-ETA
  suppression, and distinct path-private long-FFmpeg heartbeat behavior;
- typed configuration parsing, immutable/additive defaults, validated media
  extensions, MIME types, noise tokens and timeout, alternate-config
  selection, invalid-schema refusal, and config self-protection;
- centralized collection-path derivation and duplicate-tree recognition;
- fixed-name action-log non-detection and removed v0.1 interface refusal;
- path-private fast and checksum scan reports, stable JSON, bounded worker
  validation, readiness recommendations, and explicit cache-state guarantees;
- dynamic package metadata, packaged TOML data, runtime/distribution version
  agreement, and the selected Hatchling plus hatch-vcs configuration.

Run the committed quality gates and complete suite after every change. Release
review also runs subprocess-aware coverage. Do not
replace real FFmpeg integration coverage with mocks alone.
`docs/CODE_REVIEW.md` records findings, severity, target release, and durable
resolution state; keep it synchronized as each release closes a group.

## Research and roadmap

`docs/RESEARCH.md` records evaluated products, privacy evidence, licensing
cautions, and open design questions that are not committed to a release.
`docs/ROADMAP.md` is the promoted delivery plan, with one primary purpose per
patch through the version 0.1 foundation, version 0.2 inspection and hardening,
version 0.3 stabilization, version 0.4 preservation and cache foundation, and
version 0.5 migration-verification sequence.
`docs/CHANGELOG.md` is the shipped-behavior record. Keep these roles separate
instead of maintaining duplicate feature inventories.

`scan` is implemented; do not rename it to `inspect`.

## Git policy

This project uses concise one-line commits authored as `nachiketbhujbal` with
the account-specific GitHub no-reply address. `origin` is the approved personal
repository at `git@github.com:nachiketbhujbal/python-media-organizer.git`, using
a repository-specific deploy key. Push commits or release tags only when the
user explicitly approves that release. Confirm private collection data and
generated state are absent before every commit.

Ordinary changes now use one short-lived branch and pull request per cohesive
release. The pull request and resulting `main` push run all GitHub `quality`
checks automatically; ordinary branch pushes and tags do not. Manual dispatch
is available when pre-PR platform evidence is worth the private-repository
Actions usage. The v0.3.6 workflow merge was the one-time bootstrap because the
check could not be required until the workflow existed on `main`. GitHub CLI is
authenticated for pull-request and Actions management; the repository deploy
key remains the scoped Git transport credential. GitHub's
`delete_branch_on_merge` repository setting is enabled, so merged remote head
branches are removed automatically; local branch deletion and remote-tracking
pruning remain local maintenance. See `docs/CONTRIBUTING.md` for the safe
sole-maintainer ruleset.

An AI assistant's branch carries its own prefix, `claude/<type>/<slug>` or
`codex/<type>/<slug>`, adding the target version as `<type>/v<x.y.z>-<slug>`
when the work is scheduled for a release. The merge commit preserves that name,
so attribution stays visible without changing the one-line, maintainer-authored
commit convention. A branch claims the next free `docs/adr/` number in its first
commit and names it in the pull request so parallel assistant branches cannot
collide. Each assistant adversarially reviews the other's pull request before
merge by default; the maintainer may waive a review, and a waived review is
recorded in `docs/CODE_REVIEW.md` as follow-up debt rather than skipped
silently. ADR 0077 is the durable decision.

GitHub's ruleset and classic branch-protection APIs currently return HTTP 403
because the repository is private under GitHub Free. The repository must remain
private unless the user explicitly changes that decision. Until GitHub Pro is
enabled or the repository becomes public, PR review and the no-force-push,
no-deletion policy are procedural rather than server-enforced. When eligible,
activate the no-bypass `main` ruleset defined in ADR 0046 and verify it through
the API before describing the branch as protected.
