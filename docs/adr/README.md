# Architecture decision records

Each numbered file records one durable project decision. Accepted records are
append-only history: when a decision changes, add a new ADR that supersedes the
old one rather than rewriting why the earlier choice was made.

| ADR | Decision |
| --- | --- |
| [0001](0001-local-first-privacy.md) | Local-first privacy boundary |
| [0002](0002-dry-run-and-no-deletion.md) | Dry-run-first, no-deletion mutations |
| [0003](0003-collection-layout.md) | Fixed collection layout and ownership |
| [0004](0004-jsonl-action-history.md) | Append-only JSONL action history |
| [0005](0005-src-package-and-cli.md) | `src` package and unified CLI |
| [0006](0006-uv-workflow.md) | uv environment and lock workflow |
| [0007](0007-hatchling-vcs-versioning.md) | Hatchling and Git-tag versions |
| [0008](0008-toml-configuration.md) | Validated TOML configuration |
| [0009](0009-privacy-conscious-logging.md) | Privacy-conscious Python logging |
| [0010](0010-deterministic-renaming.md) | Deterministic non-AI renaming |
| [0011](0011-exact-image-matching.md) | Exact displayed-pixel image matching |
| [0012](0012-strict-video-matching.md) | Strict local FFmpeg video matching |
| [0013](0013-disposable-sqlite-cache.md) | Disposable SQLite fingerprint cache |
| [0014](0014-read-only-scan.md) | Read-only collection scan |
| [0015](0015-bounded-concurrency.md) | Bounded measured concurrency |
| [0016](0016-semantic-versioning.md) | Semantic compatibility boundaries |
| [0017](0017-quality-toolchain.md) | Ruff, Black, mypy, and pre-commit |
| [0018](0018-synthetic-test-data.md) | Synthetic, collection-neutral tests |
| [0019](0019-report-only-validation.md) | Report-only validation first |
| [0020](0020-posix-platform-boundary.md) | Current POSIX platform boundary |
| [0021](0021-atomic-no-replace-moves.md) | Atomic no-replace file moves |
| [0022](0022-bind-analysis-to-file-state.md) | Stable file state for exact analysis |
| [0023](0023-fail-closed-on-invalid-derived-cache.md) | Fail closed on invalid derived cache |
| [0024](0024-resolve-native-tools-only-when-needed.md) | Lazy native-tool resolution |
| [0025](0025-omit-changing-files-from-scan.md) | Omit changing files from scan reports |
| [0026](0026-interruption-exit-and-runtime.md) | Interruption exit and runtime reporting |
| [0027](0027-staged-command-orchestration.md) | Explicit command stages and shared duplicate policy |
| [0028](0028-subprocess-aware-test-coverage.md) | Subprocess-aware test coverage |
| [0029](0029-standard-and-full-validation-profiles.md) | Standard and full validation profiles |
| [0030](0030-path-private-validation-reports.md) | Path-private validation reports |
| [0031](0031-validation-health-exit-status.md) | Validation health exit status |
| [0032](0032-sequential-full-video-validation.md) | Sequential full video validation |
| [0033](0033-minimize-native-validation-output.md) | Minimized native validation output |
| [0034](0034-changing-input-precedes-corruption.md) | Changing input precedes corruption findings |
| [0035](0035-report-discovery-failures.md) | Validation discovery failures are health findings |
| [0036](0036-staged-validation-orchestration.md) | Staged validation orchestration |
| [0037](0037-descriptor-pinned-validation-reads.md) | Descriptor-pinned validation reads |
| [0038](0038-repository-documentation-map.md) | Repository documentation map |
| [0039](0039-small-cohesive-releases.md) | Small cohesive release tags |
| [0040](0040-complete-ordered-scan-recommendations.md) | Complete ordered scan recommendations |
| [0041](0041-continuous-integration-quality-gate.md) | Continuous-integration quality gate |
| [0042](0042-feature-branch-merge-policy.md) | Feature-branch merge policy |
| [0043](0043-portable-descriptor-classification.md) | Portable descriptor-backed classification |
| [0044](0044-private-repository-actions-budget.md) | Private-repository Actions budget |
| [0045](0045-descriptor-pinned-video-duplicate-reads.md) | Descriptor-pinned video duplicate reads |
| [0046](0046-private-free-main-protection-prerequisite.md) | Private-Free main-protection prerequisite |
| [0047](0047-descriptor-pinned-image-duplicate-reads.md) | Descriptor-pinned image duplicate reads |
| [0048](0048-descriptor-pinned-sqlite-cache-reads.md) | Descriptor-pinned SQLite cache reads |
| [0049](0049-locked-atomic-sqlite-cache-writes.md) | Locked atomic SQLite cache writes |
| [0050](0050-stable-progress-cadence.md) | Stable progress cadence |
| [0051](0051-distinct-heartbeats-and-eta-confidence.md) | Distinct heartbeats and ETA confidence |
| [0052](0052-path-private-stage-timing.md) | Path-private stage timing |
| [0053](0053-explicit-cache-activity-reporting.md) | Explicit cache activity reporting |
| [0054](0054-path-private-duplicate-summaries.md) | Path-private duplicate summaries |
| [0055](0055-default-console-timestamps.md) | Default console timestamps with an explicit opt-out |
| [0056](0056-retain-roadmap-release-ledger.md) | Retained roadmap release-status ledger |
| [0057](0057-directional-migration-verification.md) | Directional migration preservation proof |
| [0058](0058-corruption-findings-are-not-ignore-policy.md) | Corruption findings remain visible evidence |
| [0059](0059-fail-closed-filesystem-discovery.md) | Fail closed on incomplete filesystem discovery |
