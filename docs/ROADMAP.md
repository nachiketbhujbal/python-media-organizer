# Roadmap

This is the delivery plan for `python-media-organizer`. It records work that
has been promoted from [research](RESEARCH.md) into an intended release.
[CHANGELOG.md](CHANGELOG.md) records what actually shipped. Plans can move as
evidence changes; released entries are removed from this file once their final
behavior is captured in the changelog and handoff.

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
| 0.3.10 | Image read safety | Descriptor-pin exact-image classification and pixel reads without changing duplicate semantics. | Planned |
| 0.3.11 | Cache access safety | Harden the derived SQLite cache path, locking, replacement, corruption, and interruption boundaries. | Planned |
| 0.3.12 | Progress cadence | Eliminate repeated forced progress rows and make count-based output stable across fast and slow work. | Planned |
| 0.3.13 | Heartbeat and ETA | Distinguish active-item heartbeats from completed-work progress and suppress unstable ETA until enough observations exist. | Planned |
| 0.3.14 | Stage timing | Report discovery, probing, fingerprinting, planning, apply, and verification durations independently. | Planned |
| 0.3.15 | Cache wording | Make hits, misses, newly persisted records, and no-cache behavior unambiguous. | Planned |
| 0.3.16 | Concise summaries | Add `--summary` for aggregate, path-private command results without verbose group listings. | Planned |
| 0.3.17 | Timestamp default | Timestamp human-readable console lines by default; add an explicit opt-out while preserving clean JSON and compatibility with `--timestamps`. | Planned |

The order may change when a safety dependency is found, but unrelated primary
purposes are not folded together merely to reduce tag count.

## Version 0.4 cache foundation

Version 0.4 introduces a shared, derived cache service. The append-only
collection action log remains the authoritative mutation history; SQLite stays
disposable and rebuildable.

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

## Later promoted work

These have an accepted product direction but no release number yet:

- richer local collection statistics and historical comparisons;
- metadata inspection/export with date provenance and confidence;
- read-only collection and backup comparison;
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
