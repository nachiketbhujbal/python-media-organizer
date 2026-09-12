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

This subsystem verifies an already performed rescue or copy. Version 0.5.11's
`pymo migrate` coordinates only the post-copy single-pair runbook. Rescue
copying remains separate because damaged storage requires recovery-specific
policy, resumability, destination capacity checks, and a much larger mutation
boundary.

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

Version 0.5 delivered directional preservation verification. Its later patches
retain that subsystem while tightening evidence behavior and repository records.

| Version | Primary purpose | Intended result | Status |
| --- | --- | --- | --- |
| 0.5.4 | Coordination and planning records | Record the multi-assistant repository coordination decision in one ADR, keep its conventions in the single authoritative instruction file rather than in a tool-specific entry point, and reconcile the overlapping research and roadmap planning records so each subject has one home. Runtime behavior, packaging, configuration, and tests are unchanged. | Released |
| 0.5.5 | Media-extension classification severity | Stop reporting a non-media file that merely bears a configured media extension as a decode error at failing exit status. Let a meaningful non-media content signature outrank the extension where discovery trusted the extension alone, keep genuine media classified as media, and state the outcome for a machine where the local content-signature utility is unavailable. | Released |
| 0.5.6 | Container and extension truthfulness | Report a video whose container family disagrees with its filename extension, comparing the ffprobe demuxer family against the family implied by the extension during standard validation and reporting a distinct `container_extension_mismatch` warning at no extra probing cost, kept separate from `extension_content_mismatch` so the aggregate report can tell a misnamed container from content that is not video at all. Compare families rather than exact names so shared-demuxer pairs do not false-positive, require a confident probe so evidence too weak to accuse is ignored, accept both program-stream and raw elementary-stream families for generic MPEG extensions, keep the finding a warning that does not change exit status, and place it where a full-decode failure cannot discard it. Transport streams are already configured supported video; their classification rests on the extension unless a meaningful non-media signature contradicts it, because no reliable local content signature identifies them in practice, and ffprobe supplies the authoritative container identity at validation time. Preserve historical validation algorithms as structurally valid but stale so targeted refresh is the supported upgrade path. | Released |
| 0.5.7 | Plural architecture-decision directory | Rename `docs/adr/` to `docs/adrs/`, retain every numbered decision record unchanged, update all tracked links plus current path references, and ignore repository-local private operational state without changing runtime or package behavior. | Released |
| 0.5.8 | Public governance and contained CI | Adopt Apache-2.0 in the root license and package metadata; add privacy-conscious issue forms, a security policy, and private vulnerability reporting guidance; replace trigger-level path skipping with a fail-closed classifier plus one unconditional aggregate gate; keep ordinary branch pushes quiet; run the complete Ubuntu, pinned Fedora, and macOS gates for runtime, packaging, toolchain, or workflow changes; use an applicable lightweight gate for documentation-only changes; repeat applicable checks on the exact `main` commit; and verify tag ancestry, artifacts, and an isolated install without redundantly rerunning the full platform suite. Complete and durably record the authorized public transition, conservative Actions permissions, external-contributor approvals, issue/security settings, and no-bypass branch/tag rulesets. | Released |
| 0.5.9 | Reversible truthful-extension correction | Add `pymo correct-extensions COLLECTION`, sequenced after fresh validation and before organization or deterministic renaming. Act only on fresh descriptor-pinned content evidence with an unambiguous packaged canonical extension; fully decode every mapped image frame; require exact mapped-or-protected packaged-policy coverage; and leave valid synonyms, TIFF-derived and camera-raw images, shared or audio-capable video families, raw elementary streams, weak probes, unsupported formats, and other ambiguity untouched. Add a canonical suffix to conclusive extensionless media. Change no media bytes, preview by default, require `--apply`, use atomic no-replace collision handling, append distinct journal actions, verify applied state, and support dependency-aware undo. | Released |
| 0.5.10 | Simulated preservation without `dups` | Add zero-write `verify-migration --simulate-without-dups`. Inventory the destination review tree and report its files and bytes separately, but prevent it from satisfying destination coverage; label every verdict simulated; retain distinct byte, exact-pixel, strict-playback, multiplicity, exclusion, and uncertainty accounting; and become non-complete whenever removing `dups` would leave the declared source contract unaccounted. Do not move, quarantine, delete, cache, lock, or action-log anything. | Released |
| 0.5.11 | Guided single-collection migration | Add a production coordinator over one declared baseline/working pair and the documented runbook. Carry common options and one explicit private log directory through scan, fresh validation, initial preservation proof, extension correction, organization, deterministic renaming, duplicate isolation, simulated duplicate removal, external-quarantine confirmation, and final fresh sign-off. Preserve previews, explicit apply boundaries, real exit statuses, restartable stage state, and human checkpoints. Do not rescue-copy media, delete content, silently continue after a failed stage, or enable persistent logs by default. | Released |
| 0.5.12 | Filesystem-identity verification roots | Make standalone `verify-migration` reject a source and destination that are the same or nested physical directory through case, Unicode, or other same-filesystem aliases. Retain initial identities through strict existing-root ancestry and final endpoint revalidation, contain every guided-coordinator command-line path resolution before optional private-state creation, retain genuinely distinct case-sensitive roots, and leave report-only inventory, preservation, privacy, and zero-write behavior unchanged. | Released |
| 0.5.13 | Authoritative release-documentation reconciliation | Reconcile every current availability, review, roadmap, changelog, and handoff claim with the verified v0.5.12 release; adopt one concise public product description; and identify privacy-preserving workflow trials on existing real collections as the next evidence-gathering phase without changing runtime behavior. | Released |

Release numbers are assigned by the maintainer; this ledger records the
accepted sequence rather than promised delivery dates. Each planned row remains
unshipped until its implementation, tests, documentation, review, exact hosted
checks, tag, and installed-version proof are complete. The operational order is
captured in [MIGRATION.md](MIGRATION.md).

Everything else explored alongside this work — damaged-media isolation folders,
byte-changing repair, container conversion, remediation quarantine, and the
preservation consequences of each — remains **research rather than schedule**
and is recorded under "Media truthfulness, damage, and remediation" in
[RESEARCH.md](RESEARCH.md). None of it is approved for implementation.

## Version 0.6 operator experience

Privacy-preserving operational trials after v0.5.13 reproduced the expected
content and preservation outcomes while exposing the released coordinator as
too repetitive for long unattended work.
[ADR 0087](adrs/0087-operator-first-migration-roadmap.md) therefore makes
operator experience—not another media transformation—the version 0.6 theme.

| Version | Primary purpose | Acceptance boundary | Status |
| --- | --- | --- | --- |
| 0.6.0 | Safe operator loop | Add a foreground driver over the existing restartable stage engine that automatically advances routine successful stages in one process but stops at every existing finding, mutation, duplicate-disposition, and sign-off boundary. Preserve preview-before-apply, exact child statuses, fresh evidence, and stop-on-ambiguity behavior. | Released |
| 0.6.1 | Interactive checkpoints | Keep the operator session alive at reviewed status, apply, duplicate-disposition, and sign-off boundaries; ask explicit questions; and continue only from an affirmative, context-specific answer. This completes the interactive one-invocation path without adding unattended authorization. | Released |
| 0.6.2 | Human migration synopsis | Emit a concise end-of-run account of inventory, health, transformations, duplicate isolation, potential or realized storage recovery, cache reuse, observed durations, warnings, and preservation disposition. Keep collection paths and filenames private unless explicitly requested. | Released |
| 0.6.3 | Saved invocation context and resume | Persist the already-private run binding for exact roots, log location, options, and current checkpoint so an interrupted operator can resume without reconstructing the long original command. Restart bookkeeping remains non-evidence. | Released |
| 0.6.4 | Stable migration report artifact | Define and export a versioned machine-readable report from the same typed outcome model as the human synopsis, with deterministic path-private output and explicit compatibility rules. | Released |
| 0.6.5 | Pre-authorized unattended mode | Add a deliberately explicit non-interactive policy that may cross only enumerated, pre-authorized checkpoints and stops on every unexpected finding, changed state, failed proof, or unrecognized decision. | Released |
| 0.6.6 | Logging surfaces and levels | Separate console output, durable private diagnostics, restart state, and final reports; add conventional console/file log levels and retention rules without changing path disclosure defaults. | Released |
| 0.6.7 | Visibility and privacy profiles | Add explicit full, private, and quiet profiles over existing console and disclosure controls while preserving the path-private default, opt-in persistence, legacy flags, and strict path-private report modes. | Release candidate |
| 0.6.8 | Retained-in-place duplicate disposition | Integrate the existing without-`dups` simulation into the operator flow so a reviewed tree may remain in place with an honest simulated preservation disposition and an explicit statement that no storage was reclaimed. Do not silently change ordinary physical verification. | Planned |
| 0.6.9 | Same-filesystem managed quarantine | Add dry-run-first, descriptor-relative, atomic no-replace movement of a reviewed duplicate tree to a retained quarantine on the same filesystem, with journal, undo, interruption, and fresh post-move verification boundaries. | Planned |
| 0.6.10 | Cross-filesystem managed quarantine | Add an explicit capacity-checked copy, verify, and no-replace publication protocol for retained quarantine across filesystems, with restart and failure semantics distinct from same-filesystem movement. Never treat it as an implicit move fallback. | Planned |
| 0.6.11 | Queue manifest and planning | Define and validate a declarative local manifest binding each baseline, working collection, private state, quarantine destination, policy, and desired disposition; report a complete execution plan without running it. | Planned |
| 0.6.12 | Sequential queue execution | Execute validated manifest entries sequentially by default, isolate every collection's state, and stop safely on the first unhandled outcome. | Planned |
| 0.6.13 | Queue recovery | Resume individual collection jobs without rerunning completed work, define retry and skip policy, and preserve every fresh-evidence boundary. | Planned |
| 0.6.14 | Queue synopsis | Aggregate stable per-collection outcomes into a path-private queue report without allowing one collection's success to mask another's failure or uncertainty. | Planned |
| 0.6.15 | Storage-aware scheduler measurements | Model stage dependencies and storage topology and collect representative CPU, memory, thermal, cache-lock, and device-contention evidence without enabling new concurrency. | Planned |
| 0.6.16 | Bounded intra-collection scheduling | Enable only benchmark-proven independent work within one collection, with explicit limits, current cache-publication safety, and a sequential fallback. | Planned |
| 0.6.17 | Bounded cross-collection scheduling | Add storage-aware cross-collection execution and later-collection cache warming only where measured topology and workload evidence show a material benefit; remain sequential by default. | Planned |

The sequence deliberately gives each patch one primary acceptance purpose. It
separates the operator loop from checkpoint consent, human output from a stable
report schema, saved context from unattended authority, logging from visibility
policy, logical duplicate disposition from physical movement, queue declaration
from execution and recovery, and measurement from concurrency. Each release
requires its own implementation evidence and independent review; planning
status is not shipped behavior.

## Later promoted work

The post-v0.5.13 trials are complete enough to promote the version 0.6 sequence
above. Collection names, paths, media, statistics, and identifying metadata
remain outside the repository. Further trials may refine acceptance criteria,
but do not silently change a planned release.

These have an accepted product direction but no release number yet:

- richer local collection statistics and historical comparisons;
- a collection-history command that summarizes committed runs and actions from
  the portable journal without exposing paths by default, including an explicit
  distinction between reversible operations and any future irreversible event;
- validation remediation guidance that turns findings into explicit next
  actions, including reversible quarantine planning for media that cannot be
  decoded, while never converting damage into an ignore rule or claiming an
  unsupported format is corrupt; reversible extension correction is sequenced
  separately under "Version 0.5 continuation" above;
- resumable rescue copying with capacity, case-collision, copy-completeness,
  destination, and final naming policy; this remains separate from the planned
  queue over already-declared baseline/working pairs and requires a larger
  mutation boundary;
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
- broader POSIX portability beyond the tested Debian-family Linux, Red
  Hat-family Linux, macOS, and Linux-based WSL execution models, including safe
  atomic no-replace mutation primitives;
- dependency inventory, release SBOM, and outbound-network-denied tests;
- a local interface over the same command engine.

Optional local AI naming and semantic search remain in research until the
deterministic toolkit is mature and model origin, license, checksum, network
isolation, and suggestion-only behavior have an accepted design.
