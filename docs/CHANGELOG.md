# Changelog

All notable changes to `python-media-organizer` will be recorded here.

## 0.3.7 - 2026-08-22

- Limit automatic GitHub Actions runs to pull requests targeting `main` and
  pushes to `main`, avoiding duplicate private-repository runs on ordinary
  branch pushes and version tags.
- Retain explicit manual workflow dispatch for deliberate pre-PR or tag
  verification.
- Cap every platform job at ten minutes so a stalled dependency or subprocess
  cannot consume the private-repository allowance indefinitely.
- Keep the full Ubuntu, Fedora, and macOS quality matrix on every automatic
  pre-merge and post-merge run.

## 0.3.6 - 2026-08-22

- Add a least-privilege GitHub Actions `quality` job for branch pushes, pull
  requests to `main`, mainline pushes, and version tags.
- Reproduce the locked Python 3.11, uv 0.12.5, pre-commit, real FFmpeg,
  subprocess-aware coverage, and package-build release gates in CI.
- Fetch complete history for hatch-vcs and verify that each release tag matches
  the installed CLI version.
- Stream descriptor-pinned classification bytes to the `file` utility through
  standard input, avoiding platform-specific `/dev/fd` type detection on Linux.
- Run the complete quality gate on Ubuntu, Fedora, and macOS representatives;
  Linux-based WSL follows the Linux execution model, while native Windows
  remains out of scope.
- Make exact-video integration coverage independent of FFmpeg's
  container-specific remux timestamp choices while retaining a
  non-byte-identical exact-playback case.
- Generate synthetic video fixtures with an encoder available in official free
  FFmpeg builds, avoiding an unnecessary H.264 encoder requirement in tests.
- Document the short-lived branch, sole-maintainer protection, and release
  workflow in `docs/CONTRIBUTING.md` and separate ADRs.

## 0.3.5 - 2026-08-22

- Recommend `pymo rename` whenever scan finds non-canonical source-media names,
  even when collection organization is also needed.
- Keep recommendations ordered as organize, rename, image duplicates, then
  video duplicates so the full plan remains safe and immediately actionable.
- Add text and JSON regression coverage for the recommendation content and
  order.

## 0.3.4 - 2026-08-22

- Separate evaluated research from promoted release plans in `docs/RESEARCH.md`
  and `docs/ROADMAP.md`.
- Centralize the changelog, adversarial review, research, roadmap, and ADRs
  under an indexed `docs/` tree while retaining root operational documents.
- Define small, single-purpose patch releases through the planned 0.3
  stabilization and 0.4 cache foundation.
- Record the repository documentation map and cohesive-release policy in
  separate ADRs.

## 0.3.3 - 2026-08-22

- Pin validation classification, Pillow, ffprobe, and FFmpeg reads to stable
  regular-file descriptors beneath the resolved collection root.
- Refuse symbolic links in every collection-relative parent component and
  prevent pathname swaps from redirecting a decoder outside the collection.
- Recheck both the open descriptor and its pathname after inspection, reporting
  concurrent replacement as changed rather than corrupt.
- Add adversarial final-file and parent-link tests while retaining real FFmpeg
  integration coverage.

## 0.3.2 - 2026-08-22

- Split validation directory filtering, file discovery, video stream policy,
  duration checks, and native inspection into focused typed stages.
- Replace long positional validation/report interfaces with immutable option
  objects while preserving CLI behavior and schema 1 output.
- Record the maintainability finding and orchestration decision in the durable
  adversarial review and ADR ledgers.

## 0.3.1 - 2026-08-22

- Remove the absolute collection root from default validation text.
- Report unreadable directory traversal as a health error instead of silently
  omitting the subtree.
- Request only required ffprobe fields and discard native-tool diagnostics so
  normal validation failures remain stable and path-private.
- Give concurrent file changes precedence over image/video corruption findings.
- Validate video codec names and positive dimensions, and replace an internal
  dependency assertion with an explicit safe failure.
- Add direct regression tests and ADRs for each validation hardening decision.

## 0.3.0 - 2026-08-22

- Add report-only `pymo validate COLLECTION` for recursive media health checks
  without requiring an organized `pics`/`vids` layout.
- Add a standard profile with Pillow image verification and local ffprobe video
  structure checks, plus `--full` image-frame and FFmpeg stream decoding.
- Report empty, invalid, unreadable, changing, extension-mismatched,
  unsupported, multi-stream, extra-stream, and duration findings without ever
  moving, deleting, repairing, quarantining, caching, or action-logging media.
- Add stable path-private JSON schema 1 and aggregate text output, with explicit
  `--show-files` and `--show-ignored` relative-path opt-ins.
- Return health-aware status 0/1 while reserving 2 for setup/usage failures,
  and keep full video decoding sequential despite configurable standard workers.
- Add synthetic privacy/read-only/error/animation/config tests and real FFmpeg
  full-decode integration coverage.

## 0.2.6 - 2026-08-22

- Split exact-media discovery, analysis, fingerprint-cache work, grouping,
  planning, apply, and verification into typed, independently testable stages.
- Split organizer and renamer apply/verification stages from their command
  coordination and separate scan entry summarization from report assembly.
- Consolidate duplicate-folder ownership checks, review destinations,
  collision naming, undo display, and human-readable byte formatting.
- Configure subprocess-aware Coverage.py collection so real child-process CLI
  tests contribute to the report; the full 127-test suite now measures 86%.
- Preserve command text, dry-run/apply behavior, exact matching, cache rules,
  action history, collision refusal, and privacy defaults through the refactor.

## 0.2.5 - 2026-08-22

- Carry stable regular-file state through scan discovery, classification, and
  optional checksumming so reports never combine old sizes with changed bytes.
- Omit files detected changing during a scan, distinguish them from unreadable
  entries, and report a path-private changed count in text and JSON output.
- Return conventional exit status 130 for Ctrl-C while reporting the observed
  elapsed runtime and interruption status.
- Emit a stopped-runtime line before propagating an unexpected command error,
  while preserving quiet and structured-JSON output contracts.
- Add direct regression coverage for concurrent scan changes and command-level
  interruption/failure paths that subprocess-only coverage could not observe.

## 0.2.4 - 2026-08-22

- Bind exact image and video analysis to stable regular-file identity and state,
  then revalidate every group before apply and retained originals through the
  journal commit boundary.
- Skip changing inputs conservatively and abort a stale applied plan without
  moving media or creating action history when detected before a transaction.
- Promote Pillow decompression-bomb warnings to per-file skips and reject
  malformed ffprobe stream entries and non-finite timing values.
- Fail early and clearly on corrupt, incompatible, or malformed video cache
  data without deleting it; retain `--no-cache` as an explicit bypass.
- Discover videos before resolving FFmpeg so empty and single-video collections
  can produce a zero-duplicate report without unnecessary native dependencies.
- Add focused adversarial tests for changing inputs, retained-file mutation,
  malformed media metadata, cache corruption, and lazy tool resolution.

## 0.2.3 - 2026-08-22

- Make action-log parsing a strict fail-closed state machine that rejects
  unknown, duplicated, out-of-order, malformed, and inconsistent lifecycle
  records before undo or new mutation.
- Reject journal symlinks even when substituted after `ActionLog` construction,
  reject hard-linked or non-regular journals, and validate timestamps, tools,
  modes, targets, action fields, identities, and commit counts without changing
  schema 1 records written by prior releases.
- Calculate file identities only when pre/post stat state remains stable, and
  verify the identity again after each file move.
- Open every move parent through no-follow directory descriptors and use atomic
  macOS/Linux no-replace rename calls, preserving a destination created after
  preflight and rejecting ancestor-symlink substitution.
- Refuse non-atomic cross-filesystem moves and add adversarial regression tests
  for path substitution, target races, changing files, and journal tampering.

## 0.2.2 - 2026-08-22

- Add a durable adversarial review ledger with evidence, severity, release
  targets, and resolution states before validation work begins.
- Add one architecture decision record per established product, safety,
  packaging, privacy, cache, performance, testing, and validation decision.
- Add locked Ruff linting, Black formatting, mypy typing, pytest coverage tools,
  and an installed pre-commit gate with basic file-safety checks.
- Correct the type-narrowing, closure binding, import, and formatting findings
  exposed by the new gates without changing command behavior.
- Document that the current `fcntl`-locked action journal supports macOS and
  Linux; Windows runtime support requires a later locking decision and tests.

## 0.2.1 - 2026-08-22

- Add a privacy-safe final elapsed-time summary to every normal CLI command.
- Add opt-in `--timestamps` console output and ensure every physical line in an
  explicitly requested log file carries an ISO timestamp, level, and logger.
- Add shared observed progress, file/data rates, and ETA calculations for
  collection classification, checksums, image decoding, video inspection, and
  exact-video fingerprinting.
- Add periodic heartbeats during a single long FFmpeg decode and report
  uncached fingerprint counts and bytes before decoding begins.
- Add validated `performance.progress_interval_seconds` configuration with a
  15-second default; retain deterministic output and clean scan JSON.

## 0.2.0 - 2026-08-22

- Add read-only `pymo scan` reports for inventory, storage, content types,
  layout and naming readiness, review storage, duplicate potential, estimated
  expensive work, local pymo state, warnings, and recommended next steps.
- Add stable, path-private JSON scan output and an opt-in `--checksums` profile
  that hashes only same-size picture and video candidates.
- Add bounded parallel media classification for scans, configurable through
  `performance.scan_workers` or `--workers` and defaulting to four workers.
- Make exact-video fingerprints resumable across preview and apply runs:
  successful cache misses are persisted immediately, cache hits and misses are
  reported, and `--no-cache` disables both reads and writes.
- Keep full FFmpeg decoding sequential pending representative benchmarks;
  avoid speculative parallel decodes and any fuzzy or compression-heavy match
  path.
- Remove the compatibility interfaces deprecated in v0.1.5: CSV organizer
  undo and `--manifest`, grouped image-output migration and its options, the
  no-op image `--recursive` option, and fixed-name `media_actions.jsonl`
  detection.
- Preserve collection-named JSONL action history, exact matching definitions,
  dry-run-first media changes, collision refusal, and reversible operations.

## 0.1.5 - 2026-08-22

- Add user-visible deprecation warnings for CSV organization-manifest undo,
  grouped image-duplicate migration, the no-op `--recursive` option, and the
  fixed `media_actions.jsonl` action-log name.
- Announce removal of those compatibility surfaces in v0.2.0 while preserving
  their complete v0.1 behavior.
- Keep warnings visible on stderr through the shared logging system and cover
  legacy behavior plus its current replacements with synthetic tests.
- Remove an unreachable helper left behind when new organization runs stopped
  creating CSV manifests.

## 0.1.4 - 2026-08-22

- Add an explicit `--show-ignored` option to every forward command and the
  unified CLI for reviewing collection-relative ignored paths.
- Keep ignored filenames private by default, including under `--verbose`,
  while continuing to report the ignored path count.
- Add cross-command tests for private default output, explicit relative-path
  output, and global option forwarding.

## 0.1.3 - 2026-08-22

- Move media classification lists, rename noise tokens, image-inspection
  extensions, and the default video decode timeout into packaged TOML policy.
- Add frozen typed configuration sections with strict validation, additive
  custom arrays, and command-line timeout precedence.
- Centralize fixed collection paths in an immutable `CollectionLayout` rather
  than exposing structural names as scattered configuration or globals.
- Replace tool and action strings with stable enums, remove mutable command and
  logger globals, and retain only justified on-disk version constants.
- Preserve existing organization, rename, exact duplicate, action-log, undo,
  privacy, and dry-run behavior with expanded synthetic coverage.

## 0.1.2 - 2026-08-21

- Add validated, packaged TOML defaults shared by organization, renaming, and
  both exact duplicate finders.
- Ignore common operating-system metadata, version-control directories, pymo
  configuration, and disposable cache artifacts without moving, renaming,
  fingerprinting, deleting, or action-logging them.
- Support collection-root `.pymo.toml` extensions and alternate `--config`
  files while keeping built-in safety rules active.
- Allow organizer verification to preserve source trees that contain only
  ignored metadata, and reject invalid configuration before mutation.
- Expand synthetic regression coverage for shared ignore behavior, config
  parsing, CLI forwarding, package data, and undo compatibility.

## 0.1.1 - 2026-08-21

- Adopt uv for reproducible environments, dependency locking, tests, and
  builds.
- Replace the static Setuptools version with Hatchling and Git-tag-derived
  hatch-vcs versioning.
- Read the runtime version from installed package metadata and test that it
  matches the distribution.
- Document the standards-compatible installation, development, build, and
  release workflow.

## 0.1.0 - 2026-08-21

- Package the organizer, deterministic renamer, and exact duplicate finders
  behind the `pymo` command.
- Preserve dry-run-first, collision-safe, verified, append-only reversible
  collection operations.
- Add strict image and video folder ownership under `pics`, `vids`, and `dups`.
- Add conservative FFmpeg-based exact decoded-playback video matching and a
  disposable collection-local fingerprint cache.
- Route output through privacy-conscious standard-library logging.
- Add synthetic unit, workflow, and real FFmpeg integration tests.
- Name each portable action journal `{collection-name}-actions-log.jsonl` and
  migrate the legacy fixed filename on the next applied journal write.
