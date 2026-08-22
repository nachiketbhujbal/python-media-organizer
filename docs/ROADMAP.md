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

## Version 0.3 stabilization

| Version | Primary purpose | Acceptance boundary | Status |
| --- | --- | --- | --- |
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

## Version 0.4 cache foundation

Version 0.4 introduces a shared, derived cache service. The append-only
collection action log remains the authoritative mutation history; SQLite stays
disposable and rebuildable. The service must support analyzing a read-only
source while persisting derived evidence only at an explicitly writable cache
location. This separation is a prerequisite for migration verification: pymo
must never create a cache, lock, configuration file, or action log on a source
being preserved.

| Version | Primary purpose | Intended result |
| --- | --- | --- |
| 0.4.0 | Shared cache core | Versioned schema, file identity, algorithm/runtime keys, migrations, and reusable service interfaces. |
| 0.4.1 | Cache status | Read-only cache health, coverage, version, and stale-record reporting. |
| 0.4.2 | Video cache warm | Explicitly precompute exact-video fingerprints without running duplicate planning. |
| 0.4.3 | Stable hashes | Reuse carefully keyed whole-file SHA records while rechecking content before an exact move. |
| 0.4.4 | Probe cache | Reuse validated ffprobe structure records with tool-version invalidation. |
| 0.4.5 | Image fingerprint cache | Persist deterministic displayed-pixel image fingerprints for safe rescans. |
| 0.4.6 | Unified cache warm | Warm selected image/video records or all supported derived records explicitly. |
| 0.4.7 | Validation evidence | Record validation profile, result, file identity, runtime/tool versions, and completion time as disposable history without allowing an old healthy result to satisfy a fresh full validation. |
| 0.4.8 | Explicit cached validation | Offer an explicitly named cache-assisted validation mode for unchanged files while retaining fresh reads as the default contract of `validate --full`. |
| 0.4.9 | Targeted cache refresh | Recompute selected validation or fingerprint records without deleting unrelated cache evidence; reserve `--no-cache` for disabling both cache reads and writes. |

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
planned command is directional rather than a symmetric directory diff:

```text
pymo verify-migration SOURCE DESTINATION
```

Collection-root names, relative paths, and organization are not identity. The
command must be able to account for a source file after safe moves or renames,
and it must report duplicate multiplicity separately from preservation. It is
report-only: it never changes either media tree, never appends action history,
and never writes derived state to `SOURCE`.

| Version | Primary purpose | Intended result |
| --- | --- | --- |
| 0.5.0 | Directional byte coverage | Inventory two stable trees and prove whether every readable unique source byte stream has an exact SHA-backed representative in the destination, independent of paths and filenames. Report missing, extra, duplicate-count, unreadable, changing, and storage facts with a machine-readable schema and health-style exit status. |
| 0.5.1 | Image-content coverage | Account separately for source pictures represented by the existing exact displayed-pixel definition when a byte-identical representative is absent, without describing metadata or container bytes as preserved. |
| 0.5.2 | Video-content coverage | Account separately for source videos represented by the existing strict decoded-playback definition when a byte-identical representative is absent, retaining all conservative unsupported-case boundaries. |
| 0.5.3 | Preservation verdict hardening | Combine byte and declared media-equivalence layers into an explicit evidence report, exercise interrupted and changing-source cases, reuse only validated cache evidence, and reserve a complete-success verdict for runs with no unreadable, unstable, unsupported, or unaccounted source entry. |

The report must distinguish at least three conclusions: strict byte
preservation, exact media-content preservation, and unproven or missing data.
Deleting byte-identical copies can preserve both bytes and content while
reducing multiplicity. Deleting a metadata-only image variant or a remuxed
video may preserve displayed or playback content but does not preserve every
source byte stream. A statement such as “100% preserved” is permitted only
with the preservation contract named and all source input readable and stable.

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
- Version 0.5.0 is the earliest planned release for pymo-backed strict
  byte-coverage verification before content-equivalent duplicate variants are
  removed.
- Version 0.5.3 is the earliest planned release candidate for a complete
  pymo-assisted sign-off after organization, renaming, and reviewed duplicate
  removal. The release tag alone is not approval: the command must complete
  without unreadable, changing, unsupported, or unaccounted source input, and
  the relevant synthetic and local acceptance scenarios must pass.

The preferred acceptance setup is an unchanged baseline copy and a separate
working copy on healthy storage. pymo mutates only the working copy, then
verifies it directionally against the baseline. Keeping both on one physical
device avoids additional reads from degraded media but is not an independent
backup and requires enough free capacity for both trees and derived cache
state.

## Later promoted work

These have an accepted product direction but no release number yet:

- richer local collection statistics and historical comparisons;
- metadata inspection/export with date provenance and confidence;
- report-only perceptual image/video similarity;
- explainable keeper-quality recommendations;
- reversible metadata or quarantine actions only after dedicated safety ADRs;
- benchmark-driven bounded native-process concurrency;
- broader POSIX portability beyond the tested Debian-family Linux, Red
  Hat-family Linux, macOS, and Linux-based WSL execution models, including safe
  atomic no-replace mutation primitives;
- dependency inventory, release SBOM, and outbound-network-denied tests;
- a local interface over the same command engine.

Optional local AI naming and semantic search remain in research until the
deterministic toolkit is mature and model origin, license, checksum, network
isolation, and suggestion-only behavior have an accepted design.
