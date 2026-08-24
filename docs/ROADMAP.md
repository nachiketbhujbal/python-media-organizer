# Roadmap

This is the delivery plan for `python-media-organizer`. It records work that
has been promoted from [research](RESEARCH.md) into an intended release.
[CHANGELOG.md](CHANGELOG.md) records what actually shipped. Plans can move as
evidence changes. Released entries remain as a compact status and sequencing
ledger, while the changelog and handoff hold the detailed shipped behavior.

## Release policy

- Each patch has one primary purpose and remains independently testable and
  revertible.
- Documentation, tests, and an ADR land with the behavior they describe.
- A patch may contain tightly coupled corrections discovered while testing its
  primary change, but unrelated work moves to another patch.
- A new minor release introduces a coherent subsystem or an intentionally new
  compatibility boundary. Pre-1.0 does not mean that patch releases may remove
  or silently redefine existing interfaces.
- Release tags are cut only after the locked quality, test, coverage, build,
  installation, privacy, and repository-cleanliness checks pass.

## Version 0.1 foundation

| Version | Primary purpose | Acceptance boundary | Status |
| --- | --- | --- | --- |
| 0.1.0 | Installable safety-first toolkit | Package organization, deterministic renaming, exact image/video duplicate isolation, privacy-conscious logging, synthetic and real-FFmpeg tests, and collection-named append-only action history behind the `pymo` CLI without changing dry-run, no-overwrite, or reversible-operation guarantees. | Released |
| 0.1.1 | Reproducible packaging | Use uv and a committed lockfile for development, Hatchling for standards-compatible builds, hatch-vcs for Git-tag-derived versions, and installed distribution metadata for runtime version reporting. | Released |
| 0.1.2 | Shared ignore configuration | Apply validated packaged TOML ignore defaults across every forward command, allow additive collection or explicit configuration, protect ignored state from analysis and mutation, and reject invalid policy before mutation. | Released |
| 0.1.3 | Policy and collection architecture | Move adjustable classification, rename, inspection, and timeout policy into frozen typed configuration; centralize fixed collection paths; remove mutable command/logger globals; and preserve all existing behavior with expanded tests. | Released |
| 0.1.4 | Explicit ignored-path review | Keep ignored names private by default and under `--verbose`, while adding deterministic collection-relative disclosure only through explicit `--show-ignored` across forward commands. | Released |
| 0.1.5 | Compatibility deprecation boundary | Warn for CSV organizer undo and manifests, grouped image-output migration, no-op image recursion, and the fixed action-log filename while retaining their complete v0.1 behavior and announcing removal in v0.2.0. | Released |

## Version 0.2 inspection and hardening

| Version | Primary purpose | Acceptance boundary | Status |
| --- | --- | --- | --- |
| 0.2.0 | Collection scan and v0.2 compatibility boundary | Add path-private text/JSON collection inventory, optional same-size checksum analysis, bounded scan classification, and resumable exact-video fingerprints; remove every interface deprecated in v0.1.5 while preserving current JSONL history, exact matching, dry-run, collision, and undo guarantees. | Released |
| 0.2.1 | Runtime and progress observability | Report privacy-safe command elapsed time, opt-in console timestamps, timestamped explicit log files, observed file/data rates and ETA, long-decode heartbeats, and configurable progress intervals without disturbing structured JSON. | Released |
| 0.2.2 | Engineering review and quality gates | Establish the adversarial review and ADR ledgers, lock Ruff, Black, mypy, coverage, and pre-commit checks, resolve findings exposed by those gates without behavior changes, and document the POSIX action-locking boundary. | Released |
| 0.2.3 | Action-journal and move safety | Parse schema-1 history as a strict fail-closed lifecycle, reject unsafe or substituted journals, require stable file identities, use descriptor-relative atomic no-replace moves, and refuse cross-filesystem or raced destinations. | Released |
| 0.2.4 | Exact-media analysis hardening | Bind image/video conclusions to stable regular-file state, revalidate duplicate groups and retained originals through commit, conservatively skip changed or malformed media, fail early on invalid cache data, and resolve FFmpeg only when comparison work exists. | Released |
| 0.2.5 | Stable scan and interruption reporting | Exclude changing files from scan facts, distinguish changed from unreadable entries without path disclosure, return status 130 for interruption, and retain observed final runtime reporting on interrupted or unexpected stops. | Released |
| 0.2.6 | Staged command architecture | Separate discovery, analysis, cache, grouping, planning, apply, verification, and report construction into typed testable stages; consolidate shared duplicate policy; and include CLI subprocesses in coverage without changing public behavior. | Released |

## Version 0.3 stabilization

| Version | Primary purpose | Acceptance boundary | Status |
| --- | --- | --- | --- |
| 0.3.0 | Report-only validation | Add standard image/video structure checks and optional full frame/stream decoding over any collection layout, with path-private reports, explicit filename opt-in, health exit status, and no mutation, cache, or action-history writes. | Released |
| 0.3.1 | Validation safety and privacy | Surface unreadable traversal, keep collection roots and native diagnostics private, validate core stream facts, and make concurrent change take precedence over a corruption finding. | Released |
| 0.3.2 | Staged validation architecture | Separate discovery, directory policy, media inspection, stream policy, execution options, and report construction into typed testable stages without changing schema 1 or CLI behavior. | Released |
| 0.3.3 | Descriptor-pinned validation | Pin classification and image/video decoder reads to stable collection-relative no-follow descriptors, rejecting path or parent substitution and reporting concurrent replacement as changed. | Released |
| 0.3.4 | Documentation map | Separate research from scheduled work, centralize durable engineering docs, and record the small-release policy. | Released |
| 0.3.5 | Complete scan advice | Recommend rename whenever non-canonical source media exists, while retaining the safe organize-before-rename order. | Released |
| 0.3.6 | Continuous integration | Run the locked quality and test gates on branches, pull requests, `main`, and release tags; document the branch and release workflow. | Released |
| 0.3.7 | Actions cost control | Run the complete platform matrix automatically for pull requests and `main`, retain manual dispatch, remove redundant branch/tag runs, and cap job duration. | Released |
| 0.3.8 | Video read safety | Descriptor-pin exact-video discovery, probing, hashing, and fingerprint inputs without changing duplicate semantics. | Released |
| 0.3.9 | Main protection prerequisite | Record the private-Free protection limitation and the exact no-bypass ruleset to activate after Pro or a public transition. | Released |
| 0.3.10 | Image read safety | Descriptor-pin exact-image candidate opens and displayed-pixel reads without changing duplicate semantics. | Released |
| 0.3.11 | Cache read safety | Descriptor-pin read-only SQLite cache access beneath the collection and fail closed on pathname replacement. | Released |
| 0.3.12 | Cache write durability | Serialize writers and publish validated cache updates atomically without following or modifying a substituted path. | Released |
| 0.3.13 | Progress cadence | Eliminate repeated forced progress rows and make count-based output stable across fast and slow work. | Released |
| 0.3.14 | Heartbeat and ETA | Distinguish active-item heartbeats from completed-work progress and suppress unstable ETA until enough observations exist. | Released |
| 0.3.15 | Stage timing | Report discovery, probing, fingerprinting, planning, apply, and verification durations independently. | Released |
| 0.3.16 | Cache wording | Make hits, misses, newly persisted records, and no-cache behavior unambiguous. | Released |
| 0.3.17 | Concise summaries | Add `--summary` for aggregate, path-private command results without verbose group listings. | Released |
| 0.3.18 | Timestamp default | Timestamp human-readable console lines by default; add an explicit opt-out while preserving clean JSON and compatibility with `--timestamps`. | Released |
| 0.3.19 | Completion documentation audit | Align the retained release ledger, current-version references, and next-work guidance after the 0.3 stabilization. | Released |

The order may change when a safety dependency is found, but unrelated primary
purposes are not folded together merely to reduce tag count.

## Version 0.4 preservation and cache foundation

Version 0.4 first makes collection discovery and first-pass health guidance
explicitly corruption-tolerant, then introduces a shared, derived cache
service. The append-only collection action log remains the authoritative
mutation history; SQLite stays disposable and rebuildable. The service must
support analyzing a read-only source while persisting derived evidence only at
an explicitly writable cache location. This separation is a prerequisite for
migration verification: pymo must never create a cache, lock, configuration
file, or action log on a source being preserved.

| Version | Primary purpose | Intended result | Status |
| --- | --- | --- | --- |
| 0.4.0 | Corruption-tolerant evidence | Make scan report directory traversal failures instead of silently omitting them, keep per-file decode failures as validation findings without aborting the collection, recommend validation before mutation, and prove through synthetic plus local acceptance tests that corrupt, unreadable, changing, unsupported, and mismatched media remain visible rather than becoming automatic ignore rules. | Released |
| 0.4.1 | Complete filesystem discovery | Require complete recursive enumeration before organization, renaming, or undo planning; require complete flat enumeration before duplicate analysis; and fail safely without creating state when the namespace cannot be read completely. | Released |
| 0.4.2 | Entry-level discovery integrity | Require every enumerated name to resolve through no-follow metadata inspection, reject entries that disappear or change category during a walk, and prove that mutating planners create no state from a ghost directory entry. | Released |
| 0.4.3 | Shared cache core | Versioned schema, file identity, algorithm/runtime keys, migrations, and reusable service interfaces. | Released |
| 0.4.4 | Cache status | Read-only cache health, coverage, version, and stale-record reporting. | Released |
| 0.4.5 | Video cache warm | Explicitly precompute exact-video fingerprints without running duplicate planning. | Released |
| 0.4.6 | Stable hashes | Reuse carefully keyed whole-file SHA records while rechecking content before an exact move. | Released |
| 0.4.7 | Package architecture | Review package cohesion and dependency direction, establish durable subsystem boundaries—especially for cache services—and reorganize only where behavior-preserving ownership becomes clearer. | Released |
| 0.4.8 | Probe cache | Reuse validated ffprobe structure records with tool-version invalidation. | Released |
| 0.4.9 | Image fingerprint cache | Persist deterministic displayed-pixel image fingerprints for safe rescans. | Released |
| 0.4.10 | Unified cache warm | Warm selected image/video records or all supported derived records explicitly. | Released |
| 0.4.11 | Validation evidence | Record validation profile, result, file identity, runtime/tool versions, and completion time as disposable history without allowing an old healthy result to satisfy a fresh full validation. | Released |
| 0.4.12 | Explicit cached validation | Offer an explicitly named cache-assisted validation mode for unchanged files while retaining fresh reads as the default contract of `validate --full`. | Released |
| 0.4.13 | Targeted cache refresh | Recompute selected validation or fingerprint records without deleting unrelated cache evidence; reserve `--no-cache` for disabling both cache reads and writes. | Released |

Cache reuse is incremental: new or changed files add or replace only their own
derived records. Unchanged records survive collection growth. No scan command
silently creates state, and `--no-cache` remains a complete cache read/write
opt-out where supported. It never means "delete the cache." A requested
`validate --full` continues to decode current file content from scratch by
default, because cached success cannot prove that the bytes remain readable
now. Validation may write new evidence after that fresh read, while any future
reuse of prior validation results must be explicit and identity/version keyed.

## Version 0.5 migration verification

Version 0.5 promotes preservation proof ahead of optional enrichment work. The
command is directional rather than a symmetric directory diff:

```text
pymo verify-migration SOURCE DESTINATION
```

Collection-root names, relative paths, and organization are not identity. The
command must be able to account for a source file after safe moves or renames,
and it must report duplicate multiplicity separately from preservation. It is
report-only: it never changes either media tree, never appends action history,
and never writes derived state to `SOURCE`.

| Version | Primary purpose | Intended result | Status |
| --- | --- | --- | --- |
| 0.5.0 | Directional byte coverage | Inventory two stable namespace-visible trees and prove whether every readable unique source byte stream has an exact SHA-backed representative in the destination, independent of paths and filenames. Report missing, extra, duplicate-count, traversal-failure, unreadable, changing, policy-excluded, and storage facts with a machine-readable schema and health-style exit status. | Released |
| 0.5.1 | Image-content coverage | Account separately for source pictures represented by the existing exact displayed-pixel definition when a byte-identical representative is absent, without describing metadata or container bytes as preserved. | Released |
| 0.5.2 | Video-content coverage | Account separately for source videos represented by the existing strict decoded-playback definition when a byte-identical representative is absent, retaining all conservative unsupported-case boundaries. | Released |
| 0.5.3 | Preservation verdict hardening | Combine byte and declared media-equivalence layers into an explicit evidence report, perform a fresh final namespace and file-state pass, use no historical cache evidence, and reserve a complete-success verdict for runs with no unreadable, unstable, unsupported, or unaccounted source entry. | Released |

The report must distinguish at least three conclusions: strict byte
preservation, exact media-content preservation, and unproven or missing data.
Deleting byte-identical copies can preserve both bytes and content while
reducing multiplicity. Deleting a metadata-only image variant or a remuxed
video may preserve displayed or playback content but does not preserve every
source byte stream. A statement such as “100% preserved” is permitted only
with the preservation contract named and all source input readable and stable.
File-level verification cannot discover orphaned allocations or entries hidden
by filesystem corruption. It must describe its scope as namespace-visible
content and preserve recovery-tool evidence as a separate prerequisite rather
than claiming whole-device completeness.

Every report must also make its ignore and exclusion policy explicit, count
excluded entry points, and state that its verdict is relative to that declared
collection scope. A system-managed or intentionally ignored tree is not
silently reclassified as inspected or preserved merely because it is outside
normal media processing.

This subsystem verifies an already performed rescue or copy. A future
`pymo migrate` orchestration command remains separate because copying from
damaged storage requires recovery-specific policy, resumability, destination
capacity checks, and a much larger mutation boundary.

### Operational readiness gates

- Do not delay rescuing readable data from degraded storage while waiting for
  pymo. Recovery or imaging is an earlier, separate operation, and its logs or
  mapfiles are preservation evidence that pymo must not replace.
- Releases through 0.4 may analyze and safely transform a healthy working copy,
  but they do not justify deleting the unchanged baseline or reformatting the
  source on the strength of pymo alone.
- Version 0.5.0 is the earliest release for pymo-backed strict
  byte-coverage verification before content-equivalent duplicate variants are
  removed.
- Version 0.5.3 is the earliest release candidate for a complete
  pymo-assisted sign-off after organization, renaming, and reviewed duplicate
  removal. The release tag alone is not approval: the command must complete
  without unreadable, changing, unsupported, or unaccounted source input, and
  the relevant synthetic and local acceptance scenarios must pass.
- A source and destination with different case-sensitivity rules require an
  explicit case-folding collision preflight. Path-independent hashes can expose
  a lost copy after migration, but they do not make a collision-prone copy
  operation safe in advance.

The preferred acceptance setup is an unchanged baseline copy and a separate
working copy on healthy storage. pymo mutates only the working copy, then
verifies it directionally against the baseline. Keeping both on one physical
device avoids additional reads from degraded media but is not an independent
backup and requires enough free capacity for both trees and derived cache
state.

### Version 0.5 continuation

Version 0.5 delivered directional preservation verification. The remaining 0.5 work is one
documentation release plus patch-level correctness over the same evidence, not a new subsystem.

| Version | Primary purpose | Intended result | Status |
| --- | --- | --- | --- |
| 0.5.4 | Coordination and planning records | Record the multi-assistant repository coordination decision in one ADR, keep its conventions in the single authoritative instruction file rather than in a tool-specific entry point, and reconcile the overlapping research and roadmap planning records so each subject has one home. Runtime behavior, packaging, configuration, and tests are unchanged. | Released |
| 0.5.5 | Media-extension classification severity | Stop reporting a non-media file that merely bears a configured media extension as a decode error at failing exit status. Let a meaningful non-media content signature outrank the extension where discovery currently trusts the extension alone, keep genuine media classified as media, and state the outcome for a machine where the local content-signature utility is unavailable. | Planned |
| 0.5.6 | Container and extension truthfulness | Report a video whose container family disagrees with its filename extension, comparing the ffprobe demuxer family against the family implied by the extension during standard validation and reusing the existing `extension_content_mismatch` warning at no extra probing cost. Compare families rather than exact names so shared-demuxer pairs do not false-positive, require a confident probe so a raw elementary stream is not accused, keep the finding a warning that does not change exit status, and place it where a full-decode failure cannot discard it. Transport streams are already configured supported video; their classification rests on the extension unless a meaningful non-media signature contradicts it, because no reliable local content signature identifies them in practice, and ffprobe supplies the authoritative container identity at validation time. State in the ADR which container pairs the method deliberately cannot distinguish. | Planned |

Release numbers are assigned by the maintainer. The 0.5.5 and 0.5.6 rows are planned work, not
committed dates.

Sequenced after detection, accepted in direction but without a release number:

- a separate narrow command that corrects a false extension, changing no bytes, journaled as a
  reversible rename distinguished from a deterministic rename, and ordered so that validation
  reports the mismatch, correction fixes it, and only then do organization and renaming run. Its
  placement in the command chain and its name are still open.

Everything else explored alongside this work — isolation folders for damaged media, byte-changing
repair, container conversion, quarantine, and the preservation consequences of each — remains
**research rather than schedule** and is recorded under "Media truthfulness, damage, and
remediation" in [RESEARCH.md](RESEARCH.md). None of it is approved for implementation.

## Later promoted work

These have an accepted product direction but no release number yet:

- richer local collection statistics and historical comparisons;
- a collection-history command that summarizes committed runs and actions from
  the portable journal without exposing paths by default, including an explicit
  distinction between reversible operations and any future irreversible event;
- deliberate duplicate finalization as a command separate from the duplicate
  finders, dry-run by default and gated by fresh preservation evidence, with a
  quarantine-first workflow and an unmistakable explicit boundary before any
  irreversible deletion is recorded; add a zero-write
  `verify-migration --simulate-without-dups` preview that inventories the
  destination review tree but prevents it from satisfying preservation
  coverage, clearly labels the verdict as simulated, and reports whether
  finalization would discard unique content;
- validation remediation guidance that turns findings into explicit next
  actions, including reversible quarantine planning for media that cannot be
  decoded, while never converting damage into an ignore rule or claiming an
  unsupported format is corrupt; reversible extension correction is sequenced
  separately under "Version 0.5 continuation" above;
- migration orchestration over a declared baseline/working-copy pair, followed
  later by a resumable queue manifest for multiple collections with capacity,
  case-collision, copy-completeness, validation, transformation, preservation,
  quarantine, and final naming checkpoints;
- categorization of collection files beyond pictures and video, keeping tool-owned state and
  unrecognized files untouched, with the open design questions recorded in
  [RESEARCH.md](RESEARCH.md);
- a task-oriented root README readability and information-architecture sweep,
  including a table of contents, linkable status and command sections, less
  repetition, and links to detailed version, roadmap, and research records
  under `docs/`;
- metadata inspection/export with date provenance and confidence;
- report-only perceptual image/video similarity;
- explainable keeper-quality recommendations;
- reversible metadata or quarantine actions only after dedicated safety ADRs;
- hardware-aware worker selection that benchmarks the storage/CPU boundary,
  remains explicitly overrideable, and warns when a configured override is
  likely to oversubscribe the detected machine;
- benchmark-driven bounded native-process concurrency;
- broader POSIX portability beyond the tested Debian-family Linux, Red
  Hat-family Linux, macOS, and Linux-based WSL execution models, including safe
  atomic no-replace mutation primitives;
- dependency inventory, release SBOM, and outbound-network-denied tests;
- a local interface over the same command engine.

Optional local AI naming and semantic search remain in research until the
deterministic toolkit is mature and model origin, license, checksum, network
isolation, and suggestion-only behavior have an accepted design.
