# Changelog

All notable changes to `python-media-organizer` will be recorded here.

## 0.5.10 - Unreleased

- Add explicit zero-write
  `pymo verify-migration SOURCE DESTINATION --simulate-without-dups` while
  leaving ordinary physical-destination verification unchanged.
- Freshly hash the complete destination, inventory the fixed `dups` review tree
  separately, and exclude only its stable regular files from simulated byte,
  exact displayed-image, strict decoded-video, multiplicity, and
  destination-only evidence.
- Keep unsafe, unreadable, unstable, ignored, and other excluded review-tree
  evidence visible and fail-closed. Revalidate the complete physical source and
  destination namespaces after every content layer rather than validating only
  the counterfactual view.
- Advance migration JSON to schema 5 with observed-versus-simulated mode,
  separate path-private review-tree accounting, and explicit simulated labels
  on byte, image, video, and final preservation verdicts.
- Make simulated completion eligible only for human quarantine review. It never
  moves, quarantines, deletes, caches, locks, action-logs, replaces ordinary
  post-move verification, or authorizes final migration sign-off.
- Resolve the canonical review directory by no-follow filesystem identity so a
  stored case variant on a case-insensitive destination cannot remain in the
  simulated evidence, while preserving distinct case-sensitive directories.
- Qualify status 0 as simulated quarantine-review eligibility in counterfactual
  mode rather than observed final sign-off.
- Record the decision in ADR 0083 and add byte, image, real-FFmpeg video,
  privacy, unsafe-entry, physical-stability, regular-file-name, multiplicity,
  filesystem-identity, and zero-write regressions.

## 0.5.9 - 2026-08-29

- Add preview-first `pymo correct-extensions COLLECTION`, with explicit
  `--apply` and dependency-aware `--undo`, between fresh validation and
  organization or deterministic renaming.
- Correct fully decoded image formats and confidently probed video containers
  only through immutable packaged canonical/synonym policy. Keep valid JPEG
  and video synonyms unchanged; leave TIFF-derived images, camera raw files,
  shared MOV/MP4/3GP and Matroska/WebM families, audio-capable ASF/Ogg/RealMedia
  families, raw MPEG elementary streams, weak probes, unsupported formats,
  corrupt inputs, meaningful non-media content, and custom extensions
  untouched. Add the canonical suffix to conclusive extensionless media.
- Read classification, Pillow, ffprobe, and SHA-256 evidence through stable
  collection-anchored descriptors without consuming validation cache state.
  Fully decode every image frame. Require an extensionless video content-probe
  score from 50 through 100 and at least one video stream before a mapped
  family can authorize correction.
- Require packaged policy to account exactly for every classified image
  extension and every validation video family as mapped or protected; reject
  overlap, omissions, and inconsistent accepted synonyms before analysis.
- Reuse Finder-style collision naming and the descriptor-relative atomic
  no-replace journal boundary. Record correction runs under their own tool ID,
  preserve ordinary rename action semantics, hash planned sources before any
  mutation, and rehash stable targets during final verification.
- Protect packaged ignored paths, pymo-owned state, symbolic links, and the
  complete `dups` tree. Fail before state on incomplete discovery, unsafe
  entries, changing evidence, invalid configuration, or missing required
  ffprobe; report inconclusive media without renaming it.
- Place the preview command in scan recommendations after fresh validation and
  before organization or deterministic renaming.
- Record the decision in ADR 0082 and add synthetic, concurrency, journal,
  privacy, collision, dependency-order, all-mapped-image corruption,
  TIFF-derived raw, extensionless-image, and real-FFmpeg transport-stream,
  raw-elementary-stream, and audio-primary ASF coverage.

## 0.5.8 - 2026-08-29

- Add the complete Apache-2.0 root license, SPDX package metadata, contribution
  terms, privacy-conscious issue forms with blank issues disabled, and private
  security-reporting guidance. Record the separate source-rights and hosted
  repository-authority boundaries in ADR 0081.
- Replace the earlier private-minute CI draft with a contained workflow: a
  trusted fail-closed change classifier, lightweight documentation/privacy
  checks, full Ubuntu/Fedora/macOS evidence for executable or workflow changes,
  one unconditional aggregate `quality-gate`, applicable exact-`main` checks,
  and a narrower annotated-mainline tag artifact and isolated-install proof.
- Promote reversible truthful-extension correction to 0.5.9, zero-write
  preservation simulation without `dups` to 0.5.10, and guided
  single-collection migration to 0.5.11 while leaving rescue copying,
  irreversible duplicate finalization, and damaged-media remediation later.
- Add a production migration runbook that documents the current manual
  baseline/working-copy sequence, explicit opt-in logs, future command gates,
  quarantine semantics, and final human sign-off.
- Complete the maintainer-authorized public bootstrap after a clean history,
  hosted-metadata, and workflow-log exposure audit. Keep issues closed while
  installing and API-verifying no-bypass `main` protection, immutable `v*`
  tags, read-only workflow tokens, immutable action references, a narrow action
  allowlist, and approval for every external contributor before enabling
  Actions. Enable structured issues and private vulnerability reporting only
  after their versioned files reach `main`.
- Change no runtime, configuration, or media behavior.

## 0.5.7 - 2026-08-29

- Rename the architecture-decision directory from `docs/adr/` to `docs/adrs/`
  so its name describes the plural set of records it contains.
- Update every tracked link, documentation map, instruction, handoff reference,
  and coordination path to the plural directory without changing the numbered
  decision files or their history.
- Ignore repository-local `.pvt/` and `.worktrees/` state so private operational
  records and linked worktrees cannot be added accidentally.
- Remove a stale numeric inventory of module constants from the handoff and
  retain the durable rule that module constants represent explicit on-disk
  compatibility boundaries.
- Record the maintainer's path-only independent-review waiver and its explicit
  follow-up debt instead of silently omitting the review.
- Record the documentation-layout decision in ADR 0080. Runtime behavior,
  package contents outside documentation, configuration, and tests are
  unchanged.

## 0.5.6 - 2026-08-26

- Report a warning-severity `container_extension_mismatch` when a successful
  video probe identifies a container family that disagrees with the filename
  extension, without changing validation exit status or running an additional
  probe.
- Require an integer content-probe score from 50 through ffprobe's maximum of
  100, a non-empty demuxer family, and an explicitly mapped packaged video
  extension before reporting a mismatch. The probe uses an extensionless
  descriptor, so filename-extension scoring cannot satisfy that boundary.
  Treat MOV/MP4, Matroska/WebM, transport-stream, raw/program MPEG, and other
  shared demuxers as families so valid names do not produce false accusations.
- Keep container findings distinct from non-media
  `extension_content_mismatch` findings and preserve probe, stream, duration,
  and container evidence when a later full decode fails.
- Add immutable packaged family policy covering every packaged video extension;
  collection and explicit configuration cannot redefine it, while custom video
  extensions simply receive no container accusation.
- Advance standard and full validation evidence algorithms to version 2.
  Version-1 records remain structurally valid but stale and non-reusable, so
  cache status remains usable and targeted refresh can publish version-2
  evidence without deleting historical or unrelated records.
- Record the confidence and cache-compatibility boundaries in ADR 0079 and add
  synthetic plus real FFmpeg coverage for correct, shared, misnamed, weak,
  missing, malformed, private-report, and full-decode-failure cases.

## 0.5.5 - 2026-08-25

- Stop reporting a healthy non-media file that merely bears a configured media
  extension as damaged media. Validation discovery no longer promotes a file to
  a media kind on the strength of its extension once the content signature has
  positively identified non-media content, so such a file is never probed or
  decoded and no longer returns a failing exit status for an otherwise healthy
  collection.
- Report that file as a warning-severity `extension_content_mismatch` entry
  instead of dropping it silently, so the naming problem stays visible and
  actionable, and count it as a non-media file rather than as a picture or
  video.
- Keep an empty media file an error: an empty stream is not a non-media content
  signature but the absence of one, so the extension remains the only available
  evidence. Package both spellings the content-signature utility uses for an
  empty result, because descriptor-pinned callers read standard input and
  receive the spelling that was not previously listed.
- Leave classification unchanged where the content-signature utility is
  unavailable, since no meaningful signature exists to outrank the extension;
  that case already reports its own distinct fallback warning. Take configured
  image and video extensions before interpreting the filename MIME guess that
  remains, so a platform database that does not recognize a configured
  extension cannot report genuine media as a naming mismatch, and apply the
  same rule when the utility is present but fails for one file.
- Record the precedence rule in ADR 0078, and add coverage for a text file under
  video and picture extensions, a genuine transport stream that must still
  validate as video, an empty media file, and the unavailable-utility boundary.

## 0.5.4 - 2026-08-24

- Record multi-assistant repository coordination in ADR 0077: `AGENTS.md` is the
  only authoritative instruction file and a tool-specific entry point is
  navigational rather than normative, an assistant branch carries a `claude/` or
  `codex/` prefix that the merge commit preserves, and every subagent reads
  `AGENTS.md` and `HANDOFF.md` completely because imported context is not
  inherited.
- Reserve each `docs/adrs/` number when a branch starts, claim it in that branch's
  first commit, and re-check it against the target branch immediately before
  merge, renumbering on conflict, because claiming alone cannot stop two
  branches selecting the same number.
- Give each release one owner and one reviewer rather than two co-owners: the
  owner writes the branch and its review-ledger resolutions, and the reviewer
  reports findings through its own channel instead of committing to that branch.
- Settle technical disputes with evidence and tests, with a measured or traced
  result outranking an inferred or assumed one; make the maintainer the final
  product and policy tiebreaker, and record unresolved dissent rather than
  averaging it away.
- Add those conventions to the `AGENTS.md` development-workflow list and reduce
  the repository `CLAUDE.md` to a navigational entry point, so the rules have one
  home rather than two.
- Record media truthfulness, damage, and remediation as one research subject,
  covering terminology, validation-remediation actionability, container and
  extension truthfulness, and the deliberately deferred repair, container
  conversion, and quarantine directions.
- Record duplicate finalization and collection history, migration orchestration
  and queues, organizing files beyond pictures and video, and persistent
  diagnostic logging as separate research subjects with one home each.
- Reconcile those overlapping planning records to a single section level and
  close the AI-tool repository coordination question with a pointer to ADR
  0077, retaining only its unresolved shared-directory part.
- Correct the container and extension truthfulness records, which described a
  local content signature as authoritative for transport streams, treated their
  extensions as not yet recognized, and left an already-answered question
  standing as open; retarget the roadmap row to 0.5.6 and schedule 0.5.5 for the
  media-extension classification severity defect.
- This release deliberately carries both the coordination decision and the
  planning-record reconciliation as one documentation purpose; runtime
  behavior, packaging, configuration, and tests are unchanged.

## 0.5.3 - 2026-08-23

- Add the final `layered-exact-preservation` verdict that accounts for each
  unique source stream through exact bytes, exact displayed pixels, or strict
  decoded playback while keeping all three evidence layers visible.
- Return success for supported exact image transformations and video remuxes
  only when every source stream is accounted for; retain `incomplete` for
  definite missing supported content and `unproven` for unreadable, unstable,
  unsupported, or otherwise incomplete evidence.
- Re-discover both declared collection scopes after media inspection and
  revalidate every hashed file, in-scope directory namespace, unsafe entry
  category, and collection-root identity before allowing a complete verdict;
  refresh excluded-entry counts without making excluded state a blocker.
- Advance migration JSON to schema 4 with aggregate layered accounting, final
  stability, exclusions, unsupported and unaccounted content, fresh-evidence
  status, and an explicit human-signoff disposition.
- Keep normal output path-private and relative differences opt-in, perform no
  cache reads or writes, and state that completion covers stable namespace-
  visible collection content rather than whole-device recovery.
- Add adversarial coverage for final file, directory, and root changes,
  unsupported recognized media, layered success, privacy, and zero writes.

## 0.5.2 - 2026-08-23

- Add a separate strict decoded-video layer to `verify-migration` for eligible
  source byte identities without an exact destination byte representative.
- Extract descriptor-based probe normalization, native-tool checks, streamed
  frame/audio decoding, and `exact-playback-v2` fingerprinting into a shared
  video-content boundary without coupling duplicate and migration policy.
- Freshly probe one representative per eligible unique source and destination
  byte stream, then fingerprint all supported source streams and structurally
  relevant destination streams with sequential local FFmpeg decoding.
- Distinguish playback `complete`, `incomplete`, `unproven`, and `not-needed`
  results without rewriting the byte verdict or claiming source container,
  metadata, codec bitstream, or complete file bytes are preserved.
- Resolve FFmpeg and ffprobe only when video-content comparison is required;
  add explicit native-tool and positive decode-timeout options while retaining
  configured defaults, path-private progress, and the zero-cache/write boundary.
- Advance migration JSON to schema 3 with aggregate playback eligibility,
  represented, missing, runtime, and uninspectable evidence; keep relative
  paths behind `--show-files`.
- Add real-FFmpeg coverage for supported remuxes, different audio, invalid
  video structure, native-tool demand, privacy, zero writes, and unchanged
  exact-video duplicate behavior.

## 0.5.1 - 2026-08-23

- Add a separate exact displayed-image layer to `verify-migration` for eligible
  source byte identities that have no exact destination byte representative.
- Share the versioned EXIF-transposed, single-image RGBA dimensions-plus-pixels
  algorithm between duplicate analysis, cache evidence, and migration coverage
  without coupling their discovery, reporting, or mutation policy.
- Freshly decode one representative per eligible unique source and destination
  byte stream, while retaining descriptor pinning, no-follow behavior, and
  complete post-read file-state checks.
- Distinguish exact-image `complete`, `incomplete`, `unproven`, and `not-needed`
  results without rewriting the exact-byte verdict or claiming metadata,
  encoding, container, or original source bytes are preserved.
- Advance migration JSON to schema 2 with aggregate image eligibility,
  represented, missing, and uninspectable evidence; keep relative paths behind
  `--show-files` and preserve the command's zero-write boundary.
- Add integration coverage for metadata- and format-varied exact pixels,
  genuinely different pixels, unreadable source and destination candidates,
  byte-represented decode avoidance, privacy, and unchanged image-finder
  behavior.

## 0.5.0 - 2026-08-23

- Add report-only `pymo verify-migration SOURCE DESTINATION` for directional,
  path-independent exact unique-byte-stream coverage.
- Discover both trees without following symbolic links, record ignored,
  pymo-state, non-regular, unreadable, changed, and traversal evidence, and
  hash every in-scope regular file through a stable collection-anchored
  descriptor from a fresh read.
- Distinguish complete in-scope coverage, definitely incomplete coverage, and
  unproven coverage when filesystem evidence could hide a representative.
- Report unique bytes and streams, missing content, destination-only content,
  source/destination duplicate copies, and reduced or added multiplicity
  independently of filenames, paths, and collection-root names.
- Add path-private human output and schema-1 JSON, with collection-relative
  differences only under `--show-files` and ignored paths only under
  `--show-ignored`.
- Reject same or nested roots, write no cache, lock, configuration, action
  history, or media state, and return health-style statuses 0, 1, and 2.
- Add adversarial coverage for renames, reorganization, duplicate reduction,
  destination extras, missing data, policy exclusions, tool state, symbolic
  links, changing and unreadable files, traversal failures, root overlap,
  privacy, and zero-write behavior.

## 0.4.13 - 2026-08-23

- Add `pymo cache refresh` targets for image fingerprints, video fingerprints,
  standard validation, and full validation.
- Force selected image/video refreshes to recompute exact hashes and dependent
  evidence instead of accepting compatible cached values; byte-identical image
  content remains decoded once within the same refresh run.
- Route validation refresh through the always-fresh descriptor-pinned
  validation path rather than explicit evidence reuse.
- Atomically replace only selected matching evidence and observations while
  preserving unrelated types, algorithms, runtimes, profiles, and collection
  scopes.
- Retain organized-layout boundaries for image/video refresh, any-layout
  validation, external writable-cache support, path-private output, bounded
  resumable publication, and zero media/action-history mutation.
- Add focused synthetic and real-FFmpeg coverage for forced recomputation,
  unrelated-record retention, external caches, profile separation,
  selector-specific arguments, and media immutability.

## 0.4.12 - 2026-08-23

- Add explicit `pymo validate --reuse-validation` mode, which reuses only an
  exact current file observation and matching profile, algorithm, semantic
  classification context, and Pillow/ffprobe/FFmpeg runtime.
- Freshly validate and publish every cache miss while retaining ordinary
  standard and full validation as always-fresh behavior.
- Reconstruct cached warnings and errors into the same health report and exit
  status, with stable schema-2 counts for reused, fresh, and written records.
- Reopen every proposed cache hit through the collection-anchored stable
  descriptor boundary before accepting it, so a post-lookup path or state
  change becomes a fresh-validation miss.
- Require current native tool versions to establish video compatibility even
  on a cache hit, and keep `--reuse-validation` incompatible with `--no-cache`.
- Add real Pillow and FFmpeg coverage for exact reuse, profile/runtime misses,
  changed files, cached errors, external caches, decoder avoidance, and lookup
  races.

## 0.4.11 - 2026-08-23

- Record every freshly completed standard or full media validation as strict,
  path-private, disposable evidence linked to an exact file observation and
  complete-file SHA-256.
- Key validation evidence by profile, semantic classification context, and
  exact Pillow/ffprobe/FFmpeg runtime so byte-identical files with distinct
  extensions cannot overwrite different conclusions.
- Keep normal validation authoritative and fresh: cached health is validated
  before use of the cache but never substitutes for current probing or decode.
- Add validation `--cache PATH` for an external writable evidence store and
  `--no-cache` for the prior zero-cache-read/write performance boundary.
- Publish observations and validation results together in bounded atomic
  batches, retain completed batches after a later cache failure, and make cache
  status strictly validate and recognize the new evidence.
- Advance the path-private validation JSON contract to schema 2 with explicit
  fresh-validation and cache-publication facts.

## 0.4.10 - 2026-08-23

- Extend `pymo cache warm` with `images`, `videos`, and `all` selectors while
  retaining explicit, path-private, cache-only behavior.
- Separate exact-image inspection and cache publication from duplicate
  grouping so deliberate warming never performs duplicate planning.
- Reuse a freshly computed displayed-pixel fingerprint for byte-identical
  files later in the same run instead of decoding identical content again.
- Preflight every selected layout, discover every selected media set, and
  resolve required native video tools before a combined warm may write cache
  state.
- Report per-media coverage and preserve completed evidence when individual
  files are unreadable, while empty selections create no cache or lock.
- Reject video-only options for image-only warming and retain external-cache,
  privacy, exit-status, and no-media-mutation contracts across every selector.

## 0.4.9 - 2026-08-23

- Cache displayed-pixel fingerprints by complete-file SHA-256, normalization
  algorithm, and exact Pillow runtime, including reuse for newly hashed paths
  containing already known bytes.
- Add image-finder `--cache PATH` and `--no-cache` boundaries and report actual
  hash/pixel reuse, computation, and publication without exposing paths.
- Strictly validate cached pixel payloads and make cache status recognize
  current versus stale displayed-pixel algorithms while remaining zero-write.
- Publish each bounded batch's image observations and pixel evidence in one
  atomic update, and freshly recompute every reused hash involved before an
  applied image result can create state or move media.
- Move writable-cache target resolution and descriptor hashing into the shared
  cache subsystem so image and video consumers use one policy owner.

## 0.4.8 - 2026-08-22

- Persist normalized ffprobe structure by content SHA-256, probe algorithm, and
  exact ffprobe runtime, and reuse it for unchanged paths or newly hashed files
  with already known byte content.
- Strictly validate dimensions, timing, audio shape, field types, and payload
  schema before using compatible probe evidence; runtime changes require a new
  probe and malformed selected evidence fails closed.
- Publish each bounded batch's whole-file observations and new probes in one
  locked atomic cache update, retaining safe incremental interruption recovery.
- Report compatible probe records plus actual reused, computed, and persisted
  counts without revealing paths, and make cache status recognize and validate
  the new evidence while remaining zero-write and runtime-agnostic.

## 0.4.7 - 2026-08-22

- Establish `pymo.cache` as the cohesive package boundary for disposable
  derived state, with focused storage, hash-observation, status, warming, and
  nested-command modules behind a curated facade.
- Document package dependency direction and the ownership criteria for future
  subsystem extraction.
- Move shared local media classification out of the organizer command so scan,
  validation, rename, duplicate, and cache-warming code depend on explicit
  policy ownership.
- Retain command coordinators, exact image/video policy, shared safety
  foundations, and the authoritative action journal at their existing
  boundaries after a whole-package cohesion review.
- Preserve every CLI, configuration, on-disk schema, cache path, journal, and
  media behavior while reorganizing internal implementation ownership.

## 0.4.6 - 2026-08-22

- Persist whole-file SHA-256 observations under a path-private collection
  identity and reuse them only for an exact relative-path, device, inode, size,
  modification-time, and change-time match.
- Reuse current hashes during exact-video probing, publish newly computed
  observations in bounded atomic batches, and make `--no-cache` disable both
  hash and fingerprint cache activity.
- Recompute every reused hash that contributes to an applied exact-video result
  before creating duplicate directories, action history, or moves.
- Let read-only checksum scans reuse current local or explicitly selected cache
  observations while never creating or updating a cache or lock, and report
  aggregate reused-versus-computed hash counts.
- Descriptor-pin checksum reads, interpret observation scope during cache
  status, and make simultaneous first-time cache writers safely converge on one
  lock instead of racing its creation.

## 0.4.5 - 2026-08-22

- Add `pymo cache warm videos COLLECTION` to fingerprint every safely
  discovered organized video without duplicate grouping or media mutation.
- Persist successful exact-video evidence incrementally, reuse records for the
  current FFmpeg runtime, and return an incomplete status when some discovered
  media cannot be represented.
- Add `--cache PATH` so warming can write only to an explicitly selected cache
  and sibling lock outside a read-only media collection, and let the exact-video
  finder consume that same external cache.
- Keep normal output aggregate and path-private, with collection-relative
  failure paths available only through explicit `--show-files`.
- Recheck a cache's public entry after every descriptor-pinned read and forward
  global configuration options safely through the nested cache dispatcher.
- Present documented `status` and `warm` operations in top-level cache help
  while retaining operation-specific detailed help and parser errors.

## 0.4.4 - 2026-08-22

- Add `pymo cache status COLLECTION` with path-private human and stable JSON
  reports for missing, healthy shared, healthy legacy, and invalid caches.
- Report storage, evidence types and namespaces, algorithm compatibility,
  observation freshness, evidence linkage coverage, and pending legacy
  migration without claiming unchecked runtime reuse.
- Support `--cache PATH` for read-only inspection of derived state outside the
  media collection without enabling external writes in other commands.
- Read cache snapshots and observation paths through no-follow descriptors,
  reject concurrent cache replacement, validate known exact-video payloads,
  and create no cache, lock, sidecar, media, or action state.
- Keep dispatched help and argument-parser output free of timestamped runtime
  messages.

## 0.4.3 - 2026-08-22

- Extract descriptor-pinned cache access, process locking, private staging, and
  atomic publication into a reusable cache service whose writable directory is
  independent of the media root being analyzed.
- Add schema version 1 with generic algorithm/runtime-keyed derived evidence
  and stable file-identity observations for future hash, probe, image, and
  validation records.
- Continue reading valid legacy exact-video caches without modifying them, then
  migrate their completed fingerprints only inside the next successful atomic
  cache update.
- Preserve fail-closed handling for corrupt, malformed, substituted, or
  unsupported cache data without deleting or rewriting the unexpected file.
- Keep legacy migration fully transactional, reject non-standard JSON and
  non-canonical observation paths, and retain only persisted compatibility
  identifiers as cache module constants.

## 0.4.2 - 2026-08-22

- Require explicit no-follow metadata inspection for every name returned by
  recursive or flat discovery instead of relying on error-suppressing `Path`
  type predicates.
- Stop organization, renaming, undo planning, and exact duplicate analysis when
  an enumerated entry disappears or cannot be inspected.
- Reject an entry whose directory/non-directory category changes during a walk
  so a stale traversal cannot omit newly nested content.
- Add synthetic ghost-entry tests proving all mutating command families leave
  media, cache, duplicate directories, and action history unchanged.

## 0.4.1 - 2026-08-22

- Require complete recursive filesystem discovery before organization,
  renaming, or undo planning so an unreadable subtree cannot be mistaken for
  absent content.
- Stop both exact duplicate finders safely before cache, duplicate-tree, or
  action-history creation when their owned media directory cannot be listed
  completely.
- Treat incomplete post-organization discovery as a failed verification rather
  than reporting an apparently complete layout.
- Add adversarial tests proving late traversal and immediate listing failures
  leave media and collection state unchanged.

## 0.4.0 - 2026-08-22

- Report recursive directory traversal failures in `pymo scan` instead of
  silently omitting an inaccessible subtree from an apparently complete
  inventory.
- Make report-only `pymo validate` the first ordered scan recommendation before
  organization, renaming, or duplicate isolation.
- Prove that invalid image and video files remain per-file validation findings
  while healthy neighboring media continues to be checked, with no collection
  state writes.
- Keep corrupt, unreadable, changing, unsupported, and mismatched media visible
  as evidence rather than adding them to ignore configuration.

## 0.3.19 - 2026-08-22

- Correct the roadmap introduction to describe its deliberately retained
  release-status ledger instead of claiming shipped rows are removed.
- Replace stale README guidance that called the completed validation review
  future work with the promoted version 0.4 cache foundation.
- Synchronize the handoff, documentation index, review ledger, and ADR index
  with the completion audit; runtime behavior is unchanged.

## 0.3.18 - 2026-08-22

- Prefix every physical line of normal human-readable command logging with a
  timezone-aware ISO timestamp by default.
- Add `--no-timestamps` as the explicit console opt-out while retaining
  `--timestamps` for backward compatibility and explicit callers.
- Keep `scan --json` and `validate --json` machine-readable regardless of the
  timestamp option, and leave help, version, and argument-parser output plain.
- Keep explicitly requested log files timestamped independently of the console
  choice.

## 0.3.17 - 2026-08-22

- Add command-specific `--summary` output to both exact-media duplicate finders
  for aggregate, path-private forward and undo reports.
- Retain counts, progress, storage, cache activity, stage timing, final results,
  dry-run status, and verification outcomes while suppressing collection paths,
  filenames, run IDs, group details, per-item starts, and skipped-file details.
- Keep dry-run and explicit `--apply` semantics unchanged; summary mode changes
  reporting only and continues to use action history and full verification.
- Reject `--summary` with `--show-ignored` because the two options make
  contradictory path-privacy promises.

## 0.3.16 - 2026-08-22

- Replace ambiguous video-cache hit/miss wording with counts of reusable
  records and fingerprints actually required.
- Report newly persisted records after fingerprinting and distinguish required
  fingerprints that could not be persisted.
- State explicitly that `--no-cache` reads and writes no cache records, without
  emitting lookup or update claims for that run.
- Describe candidate fingerprint work independently from whether caching is
  enabled, without changing cache or duplicate-matching behavior.

## 0.3.15 - 2026-08-22

- Add path-private monotonic timing for exact-video discovery, probing,
  fingerprinting, and planning stages.
- Report apply and verification durations only when an applied duplicate move
  actually executes those stages; dry runs do not imply mutation work occurred.
- Retain the existing whole-command completion runtime while making expensive
  stage costs independently visible.
- Add shared timer and real FFmpeg workflow coverage for dry-run and applied
  stage boundaries.

## 0.3.14 - 2026-08-22

- Separate active-item heartbeat wording from completed-work status so a long
  native decode no longer repeats a stale rate or ETA.
- Report the active item, completed count, and elapsed time in heartbeats
  without filenames or an implication that the active item has completed.
- Require at least three completed observations before projecting an ETA,
  while retaining observed rates and the stable v0.3.13 reporting cadence.
- Add deterministic-clock coverage for early ETA suppression and distinct
  heartbeat semantics.

## 0.3.13 - 2026-08-22

- Replace per-item forced progress output with at most ten evenly spaced
  completed-item milestones, genuinely due time-interval reports, and one final
  completed-work row.
- Apply the same deterministic count cadence across organizing, renaming,
  scanning, validation, and both duplicate finders while preserving aggregate,
  path-private rates and totals.
- Prevent a heartbeat followed by a quick non-milestone completion from
  immediately printing a redundant completion row.
- Add deterministic-clock tests for stable milestone counts and heartbeat
  cadence without changing heartbeat wording or ETA policy.

## 0.3.12 - 2026-08-22

- Coordinate cache readers and writers through a private collection-local lock,
  and merge each completed fingerprint into the latest locked database so
  concurrent runs do not lose one another's records.
- Build updates away from the public pathname, serialize them to a private
  descriptor, sync and reopen them read-only, and verify schema, rows, and
  integrity before atomic publication.
- Use atomic no-replace publication for a new cache and a verified atomic
  exchange for an existing cache, syncing the collection directory and never
  writing through a substituted path.
- Preserve the prior cache across pre-publication interruption, leave any
  unpublished staging database ignored and inspectable, and continue to leave
  no SQLite journal, WAL, or shared-memory sidecars.
- Add concurrent-writer and adversarial tests for interruption, public-path
  substitution, lock substitution, merged records, and staging cleanup.

## 0.3.11 - 2026-08-22

- Open an existing video fingerprint cache read-only through a stable no-follow
  descriptor anchored beneath the collection root.
- Stop safely when the cache pathname is replaced during a read instead of
  allowing SQLite to follow a substituted path outside the collection.
- Add an adversarial cache-swap test proving SQLite reads the pinned original
  database and the changed public pathname is rejected.

## 0.3.10 - 2026-08-22

- Open each exact-image candidate through a stable no-follow descriptor anchored
  beneath the collection root and give Pillow a non-owning binary stream over
  that descriptor.
- Avoid resolving candidate paths through a transient symbolic link, and
  revalidate both the descriptor and pathname after displayed-pixel decoding.
- Add an adversarial pathname-swap test proving unrelated replacement pixels
  are never read, without changing exact-pixel matching or keeper semantics.

## 0.3.9 - 2026-08-22

- Record the verified GitHub Free limitation that prevents branch protection
  and rulesets from being enabled while this repository remains private.
- Specify a future no-bypass `main` ruleset that blocks force pushes and
  deletion, requires pull requests and all three platform checks, and requires
  resolved conversations without imposing an impossible self-approval rule.
- Keep the repository private and the same safeguards procedural until GitHub
  Pro is enabled or a deliberate public transition makes rulesets available.

## 0.3.8 - 2026-08-22

- Pin exact-video classification, whole-file hashing, ffprobe inspection, and
  FFmpeg fingerprint reads to stable no-follow descriptors anchored beneath the
  collection root.
- Pass inherited `/dev/fd` inputs to ffprobe and both frame/audio FFmpeg passes,
  eliminating transient pathname-redirection reads without changing exact
  duplicate semantics.
- Add adversarial discovery, probe, and fingerprint pathname-swap tests plus
  real FFmpeg regression coverage.

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
