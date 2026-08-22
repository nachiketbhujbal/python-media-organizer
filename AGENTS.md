# python-media-organizer project instructions

This is the durable, local-first Python project for safe media collection
organization. The package is `python-media-organizer`, its import package is
`pymo`, and its CLI command is `pymo`. Release versions come from Git tags;
never duplicate the version in source or static project metadata.

## Start here

- Read `HANDOFF.md` completely before making changes.
- Read the relevant modules and tests before editing behavior.
- Keep all repository language generic: say `collection`. Never record private
  sample collection names, paths, media, statistics, or identifying metadata.

## Non-negotiable safety and privacy rules

- Default every mutating command to dry run; require `--apply` to change files.
- Never delete media automatically and never overwrite an existing file.
- Resolve collisions safely for forward operations. Require exact restoration
  paths for undo and abort on conflicts.
- Perform file moves with descriptor-relative, atomic no-replace operations.
  Never replace them with check-then-rename or a non-atomic cross-filesystem
  copy fallback.
- Preserve the collection-local, append-only
  `{collection-name}-actions-log.jsonl` audit trail.
  Undo appends events and never rewrites or removes history.
- Preflight complete undo plans before mutating and verify every applied run.
- Parse action-log schema 1 as a strict lifecycle and fail closed on unknown,
  duplicate, out-of-order, malformed, or inconsistent records.
- Reject unsafe symbolic links and do not follow media outside the collection.
- Keep processing local. No telemetry, analytics, automatic networking, cloud
  AI, hosted model fallback, or automatic downloads.
- Persistent logs are opt-in because paths and filenames are sensitive.
- Prefix every physical line of normal human-readable console logging with an
  ISO timestamp by default. Keep `--no-timestamps` as the explicit console
  opt-out, retain `--timestamps` for compatibility, and never prefix structured
  JSON, help, version, or argument-parser output.
- Keep ignored path names private by default. `--verbose` may add diagnostics
  but must not reveal ignored paths; only the explicit `--show-ignored` option
  may list them, using deterministic collection-relative paths.
- Keep duplicate-finder `--summary` output aggregate and path-private across
  forward scans, applies, and undo previews. It must suppress collection paths,
  filenames, run IDs, group/action details, and per-file skip reasons. Reject
  its use with `--show-ignored`; do not weaken analysis or verification.
- Keep packaged ignore defaults active for every forward command. Ignored paths
  are never moved, renamed, fingerprinted, deleted, or action-logged.
- A collection `.pymo.toml` or explicit `--config` may only extend packaged
  list defaults; the validated video timeout may override its packaged value.
  Reject malformed or unsafe configuration before mutation. Undo is driven by
  recorded actions and remains independent of current configuration.
- Treat `.pymo.sqlite3` as derived, disposable cache data, never as the
  authoritative action history.
- Bind exact-media analysis to a stable regular-file state. Revalidate complete
  duplicate groups before apply and retained originals through journal commit.
- Keep exact-media classification, hashing, probing, and decoding pinned to
  stable, collection-anchored no-follow descriptors. A before/after pathname
  check alone does not prevent a transient read outside the collection.
- Treat an invalid derived cache as an explicit early error. Never delete or
  replace it automatically; `--no-cache` is the deliberate bypass.
- Open an existing SQLite cache through a stable collection-anchored no-follow
  descriptor. A pathname check followed by `sqlite3.connect(path)` is not a
  safe cache-read boundary.
- Serialize cache readers and writers with the dedicated collection lock.
  Build writes as fully validated private staging databases, sync them, and
  publish with an atomic no-replace or verified exchange; never write through
  the public cache pathname.
- `scan` must never alter media, collection layout, or action history. Exact
  video dry runs may update the documented disposable fingerprint cache by
  default; `--no-cache` restores a zero-cache-read/write run.
- Describe video-cache activity as reusable records, fingerprints required,
  and new records actually persisted. When `--no-cache` is selected, state the
  no-read/no-write boundary without implying that a lookup or update occurred.
- Scan inventory, classification, and checksum facts must come from stable file
  state. Omit detected changes and report only their aggregate count by default.
- `validate` is report-only: it never repairs, quarantines, moves, deletes,
  caches, or action-logs media. Collection roots and filenames are private by
  default; filenames require explicit `--show-files`. An unreadable subtree is
  a health error, and changing input supersedes any decoder conclusion.
- Keep validation content reads pinned to the same stable descriptor boundary.
  Do not reintroduce pathname-based decoder opens after a separate state check.

## Package layout and tools

- `src/pymo/organize.py`: recursive collection organization into `pics`,
  `vids`, and root-level non-media files. It protects `dups`.
- `src/pymo/scan.py`: path-private inventory, layout/naming readiness,
  duplicate potential, estimated work, and stable JSON output.
- `src/pymo/validate.py`: standard and full-decode media health reports over
  any collection layout, with path-private JSON and health exit status.
- `src/pymo/rename.py`: deterministic timestamp/descriptor-based media names.
  It protects `dups` and does not claim visual recognition.
- `src/pymo/duplicates/images.py`: exact displayed-pixel duplicate detection.
  It owns only `pics` and `dups/pics`.
- `src/pymo/duplicates/videos.py`: conservative exact decoded-playback
  duplicate detection using FFmpeg/ffprobe. It owns only `vids` and `dups/vids`.
- `src/pymo/duplicates/common.py`: shared duplicate-folder validation,
  collision naming, review destinations, and undo display without combining
  image/video analysis policy.
- `src/pymo/action_log.py`: shared append-only mutation journal and guarded
  dependency-aware undo.
- `src/pymo/collection.py`: immutable canonical paths for one collection.
- `src/pymo/logging_config.py`: console logging plus explicitly requested local
  log files.
- `src/pymo/progress.py`: shared elapsed-time, observed-rate, ETA, and heartbeat
  formatting without filenames or persistent state.
- `src/pymo/config.py` and `src/pymo/default_config.toml`: validated shared
  configuration and immutable local safety defaults.
- `src/pymo/cli.py`: thin unified command dispatcher.

Preserve the four-character collection folder convention: `pics`, `vids`, and
`dups`. Do not blur image/video duplicate ownership. Image behavior must not
depend on video folders, and video behavior must not depend on picture folders.

Avoid mutable module-level state. User-adjustable policy belongs in validated
packaged TOML defaults; fixed collection paths belong in `CollectionLayout`.
Module constants are reserved for explicit on-disk compatibility identifiers
such as schema and fingerprint algorithm versions, with an adjacent
justification. Do not replace clear constants with hidden environment-variable
configuration.

The image finder's exact-pixel matching, keeper selection, readable duplicate
naming, conservative skips, shared-log integration, and undo are approved. Do
not change those core decisions unless the user explicitly requests it.

The video finder must remain strict: whole-file SHA-256 fast path, ffprobe
structural checks, exact decoded frames plus normalized timing and orientation,
exact decoded audio plus timing, conservative unsupported-case skips, streamed
processing, and local-file-only FFmpeg inputs. Perceptual similarity is
report-only future work and must never silently enter the exact move path.

## Development workflow

- Use uv 0.12 or newer for Python environments, dependency resolution, locking,
  command execution, and builds. Commit `uv.lock`.
- Use Hatchling as the build backend and hatch-vcs for Git-tag-derived dynamic
  versions. Keep standard PEP 621 metadata so pip remains compatible.
- Manage Python and development dependencies in `pyproject.toml`; do not add
  requirements files.
- Let uv manage the project `.venv`; Python 3.11 or newer is required.
- Keep FFmpeg/ffprobe as explicit native runtime dependencies rather than
  hiding them behind a Python wrapper. Resolve them only when at least two
  eligible videos require comparison.
- Add or update pytest coverage with every behavior change. Use temporary,
  synthetic, collection-neutral fixtures.
- Follow semantic versioning for compatibility removal. The v0.1 line warns
  before compatibility is removed at a minor-version boundary.
- Real FFmpeg integration tests are required for video behavior; controlled
  unit tests remain useful for safety properties and error paths.
- Run the complete suite before handoff.
- Make ordinary changes on a short-lived branch based on `main`; do not place a
  feature or fix commit directly on `main`. Push the branch, open a pull
  request, and require its CI `quality` results before merge. GitHub Free does
  not provide server-side branch protection for this private repository, so
  that boundary is procedural until the account gains Pro or the repository
  becomes public. Never claim the planned `main` ruleset is active before the
  GitHub API confirms it. Ordinary branch pushes and tags do not run CI
  automatically while the repository is private; use the manual workflow only
  when pre-PR platform evidence is worth the additional Actions usage.
- Run subprocess-aware coverage for release review with
  `uv run --locked pytest --cov=pymo --cov-report=term-missing`.
- Run Ruff, Black, and mypy before the complete suite. Keep the installed
  pre-commit gate and its locked configuration passing.
- Base performance rates and ETAs on observed work only. Keep aggregate timing
  path-private, preserve stable ordering, and never publish guessed universal
  decode speeds as if they were measurements.
- Use shared progress milestones for completed work: at most ten evenly spaced
  count checkpoints plus genuinely due time reports and one final row. Do not
  force a row after every item; long active-item output belongs to heartbeat
  reporting.
- Keep active-item heartbeats separate from completed-work rate and ETA output.
  Heartbeats report only the active item, completed count, and elapsed time;
  require at least three completed observations before projecting an ETA.
- Report exact-video discovery, probing, fingerprinting, planning, apply, and
  verification durations independently with monotonic, path-private timing.
  Report only stages that execute; dry runs must not imply mutation occurred.
- Preserve exit status 130 for Ctrl-C and final observed runtime reporting for
  interrupted or unexpectedly stopped human-readable commands.
- Keep `README.md`, `HANDOFF.md`, `docs/ROADMAP.md`, `docs/RESEARCH.md`, and
  `docs/CHANGELOG.md` current when a decision changes their claims.
- Record each durable architecture or product decision in one numbered file
  under `docs/adr/`. Add a superseding ADR instead of rewriting accepted
  history.
- Keep `docs/CODE_REVIEW.md` finding statuses synchronized with the release
  that resolves or explicitly accepts them.
- Keep command entry points as coordinators around explicit discovery,
  analysis, planning, apply, and verification stages. Treat complexity output
  as focused review evidence rather than a blanket commit failure.
- Keep validation traversal, media-specific inspection, execution policy, and
  report construction as separate typed stages; do not reintroduce long
  positional orchestration interfaces.
- Maintain Git history with concise one-line commits and an explicit merge
  boundary per release. Do not configure a new remote or push a release without
  explicit user approval. The approved `origin` is the personal GitHub
  repository recorded in `HANDOFF.md`.

## Current roadmap

`docs/ROADMAP.md` is the authoritative promoted release plan.
`docs/RESEARCH.md` contains uncommitted ideas and open questions. Do not present
research as scheduled work until it is promoted into the roadmap.

Report-only validation is implemented and hardened through version 0.3.3. Full
FFmpeg decoding remains sequential until representative benchmarks justify
bounded native-process concurrency. Any future repair or quarantine behavior
requires a separate ADR and reversible dry-run/action-log design. Local AI
naming remains optional future work only.
