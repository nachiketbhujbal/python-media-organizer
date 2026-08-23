# Adversarial code review

This is the durable finding ledger for the pre-validation review begun on
2026-08-22. It covers every file under `src/pymo`, the complete test suite,
package metadata, release documentation, and independent lint, type, complexity,
and coverage checks. Findings stay here after resolution so their reasoning and
release history remain auditable.

Severity means impact if the condition occurs, not likelihood. `Accepted` means
the behavior is deliberate and documented; it does not mean a defect was
ignored.

## Findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| REV-001 | High | Action execution validates only the final path and immediate destination parent. A path component replaced by a symbolic link between planning and execution can redirect a move outside the collection. | 0.2.3 | Resolved |
| REV-002 | High | The JSONL parser accepts unknown, duplicated, and out-of-order lifecycle events and does not reconcile a commit's recorded action count. Corrupt or edited history must fail closed before undo. | 0.2.3 | Resolved |
| REV-003 | High | Exact image/video grouping can become stale if a source or retained file changes after analysis but before an applied move. The apply path re-hashes moved copies but does not compare them with the analyzed state or revalidate the keeper. | 0.2.4 | Resolved in ADR 0022 |
| REV-004 | Medium | File identity hashing captures stat data only before reading. A concurrently changing file can produce an internally inconsistent identity record. | 0.2.3 | Resolved |
| REV-005 | Medium | A corrupt or incompatible video SQLite cache is silently treated as empty, then may abort only after an expensive decode; malformed row values can also escape as uncontrolled exceptions. | 0.2.4 | Resolved in ADR 0023 |
| REV-006 | Medium | Some malformed Pillow/ffprobe inputs can escape the conservative per-file skip boundary, including decompression-bomb exceptions, non-object stream entries, and non-finite rotation/time values. | 0.2.4 | Resolved |
| REV-007 | Low | The video finder resolves FFmpeg before discovering whether enough videos exist to compare, so an empty or single-video collection can fail for a dependency it does not need. | 0.2.4 | Resolved in ADR 0024 |
| REV-008 | Medium | Checksum scan results can combine an old size with new bytes when files change during a run, and disappearing files can remain in inventory totals without a clear changed-file warning. | 0.2.5 | Resolved in ADR 0025 |
| REV-009 | Medium | Ctrl-C or an unexpected command failure bypasses the final elapsed-time message; a video run can therefore end with neither a clean status nor its observed runtime. | 0.2.5 | Resolved in ADR 0026 |
| REV-010 | Medium | Large command entry points mix discovery, analysis, reporting, cache work, planning, mutation, and verification. This raises change risk and makes safety branches difficult to unit test. Layout checks and size formatting are also duplicated. | 0.2.6 | Resolved in ADR 0027 |
| REV-011 | Medium | The repository had no committed lint, format, static-type, or pre-commit gate. Independent Ruff and type-checker runs found real defects plus inconsistent imports and formatting. | 0.2.2 | Resolved |
| REV-012 | Medium | Most CLI behavior tests run child processes, so ordinary coverage reports cannot observe those executed lines. Critical malformed-history, concurrent-change, cache-corruption, and interrupted-command branches were untested. | 0.2.2-0.2.6 | Resolved in ADR 0028 |
| REV-013 | Low | `fcntl` makes action history POSIX-only at import time, but the supported-platform boundary was not documented in package metadata or user documentation. | 0.2.2 | Accepted in ADR 0020 |
| REV-014 | High | A destination created after the last existence check could be overwritten by the underlying rename. Collision refusal needs to be atomic, not only a preflight convention. | 0.2.3 | Resolved in ADR 0021 |

## Validation review findings

The same adversarial method was repeated after the first validation release.

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| VAL-001 | High | Default human-readable validation output disclosed the absolute collection root even though the path-private report contract excludes collection names and roots. | 0.3.1 | Resolved in ADR 0030 |
| VAL-002 | Medium | Recursive directory-walk errors were not supplied to an error callback, so an unreadable subtree could be silently omitted while the report appeared complete. | 0.3.1 | Resolved in ADR 0035 |
| VAL-003 | Medium | Native video tools captured broader metadata and diagnostic output than validation needs, increasing memory use, output instability, and the chance of filename disclosure. | 0.3.1 | Resolved in ADR 0033 |
| VAL-004 | Medium | A decoder failure could be recorded before the final state check, mislabeling a concurrently replaced file as corrupt. | 0.3.1 | Resolved in ADR 0034 |
| VAL-005 | Low | Video validation relied on an assertion for a runtime dependency and accepted video streams without checking their codec name or positive dimensions. | 0.3.1 | Resolved |
| VAL-006 | Medium | Validation discovery and video inspection mixed traversal, classification, stream policy, decoding, and reporting through branch-heavy functions and long positional interfaces. | 0.3.2 | Resolved in ADR 0036 |
| VAL-007 | High | Validation checks path state before and after content reads, but a hostile pathname swap could still redirect Pillow or a native tool to a symbolic link during the read itself. | 0.3.3 | Resolved in ADR 0037 |
| VAL-008 | High | Content SHA-256 alone cannot key complete validation results because extension and detected-kind context can produce distinct findings for byte-identical files. | 0.4.11 | Resolved with a canonical semantic-context plus exact-runtime evidence namespace in ADR 0070 |
| VAL-009 | High | Persisting an earlier healthy result must not let ordinary or full validation skip a current descriptor-pinned probe or decode. | 0.4.11 | Resolved by write-after-fresh-read evidence with no cached-result consumer |
| VAL-010 | Medium | Validation evidence needs the external writable-cache and complete opt-out boundaries required for analyzing read-only sources without unannounced state. | 0.4.11 | Resolved with explicit `--cache`, `--no-cache`, schema-2 report facts, and integration coverage |
| VAL-011 | Medium | Validation observations and results could diverge if published through separate SQLite replacements or if malformed known evidence were accepted. | 0.4.11 | Resolved with strict runtime/payload decoding and one atomic batch publication |
| VAL-012 | High | Cache-assisted validation must not accept content evidence solely by SHA or a stale pathname observation; profile, semantic context, runtime, and exact current file identity all affect compatibility. | 0.4.12 | Resolved with one coordinated exact-key lookup plus descriptor-pinned hit revalidation |
| VAL-013 | High | A file can change after a compatible cache row is selected but before its result enters the report. | 0.4.12 | Resolved by reopening every proposed hit through the stable collection descriptor boundary and treating change as a miss |
| VAL-014 | Medium | Reusing cached error/warning results must preserve ordinary health counts, privacy, and exit status rather than treating cache hits as implicitly healthy. | 0.4.12 | Resolved by reconstructing the strict persisted findings into normal `ValidationResult` records |
| VAL-015 | Medium | A cache-assisted full validation mode could accidentally become the default and weaken the current-read contract needed for preservation checks. | 0.4.12 | Resolved with the explicit `--reuse-validation` opt-in and always-fresh default regressions |

## Scan review findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| SCAN-001 | Low | Scan counted non-canonical media names but suppressed rename advice whenever organization was also needed, even though it continued to show later duplicate-finder recommendations. | 0.3.5 | Resolved in ADR 0040 |
| SCAN-002 | Medium | Scan does not pass an error callback to recursive traversal, so an unreadable or corrupt subtree can be silently omitted while the inventory appears complete even though validation reports the equivalent failure. | 0.4.0 | Resolved in ADR 0058 |
| SCAN-003 | Low | Scan's ordered recommendations omit report-only validation, allowing organization and renaming advice to precede an explicit health check in a preservation-first workflow. | 0.4.0 | Resolved in ADR 0058 |

## Filesystem discovery findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| DISC-001 | High | Organizer and renamer planning, organizer verification, and action-log undo snapshots can consume an `os.walk` traversal without an error callback, allowing an unreadable subtree to be mistaken for a complete namespace. Flat duplicate discovery also exposes raw enumeration failures instead of a consistent no-state failure boundary. | 0.4.1 | Resolved in ADR 0059 |
| DISC-002 | High | A corrupt filesystem can return a name from directory enumeration and then return `ENOENT` for that same name. `Path.is_file()`, `is_dir()`, and `is_symlink()` suppress these metadata failures as false, so v0.4.1 traversal completeness can still omit a ghost entry from mutation and undo plans. | 0.4.2 | Resolved in ADR 0060 |

## CI portability findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| CI-001 | Medium | Descriptor-backed classification supplied `/dev/fd/N` as a filename. BSD `file` followed it to content, while GNU `file` classified the descriptor link/device itself, causing Linux media misclassification. | 0.3.6 | Resolved in ADR 0043 |
| CI-002 | Medium | The exact-video integration fixture assumed an MP4-to-Matroska stream copy preserves canonical playback across FFmpeg releases, but container timestamp behavior can legitimately differ. | 0.3.6 | Resolved with a metadata-only, non-byte-identical stream-copy fixture |
| CI-003 | Low | Container checkout marked the worktree safe only in the action's temporary home, so Fedora pre-commit could not invoke Git afterward. | 0.3.6 | Resolved by persisting the isolated worktree trust entry |
| CI-004 | Medium | Real-media tests generated H.264 with `libx264`, an encoder intentionally absent from Fedora's official free FFmpeg build even though the product only requires decoding. | 0.3.6 | Resolved by generating synthetic fixtures with FFmpeg's native `mpeg4` encoder |
| CI-005 | Low | Branch, pull-request, mainline, and tag triggers repeated the complete three-platform matrix for the same private-repository release. | 0.3.7 | Resolved in ADR 0044 |
| CI-006 | Medium | GitHub Free does not expose branch protection or rulesets for a private repository, so `main` cannot yet reject force pushes, deletion, unchecked direct pushes, or unresolved pull-request conversations at the server boundary. | 0.3.9 | Accepted with an explicit activation prerequisite in ADR 0046 |

## Exact-media review findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| DUP-001 | High | The exact-video finder checked file state around pathname-based classifier, hash, ffprobe, and FFmpeg opens, but a concurrent link swap could still redirect a transient content read outside the collection. | 0.3.8 | Resolved in ADR 0045 |
| DUP-002 | High | The exact-image finder checked state around a pathname-based Pillow open, leaving the equivalent transient path-redirection window. | 0.3.10 | Resolved in ADR 0047 |

## Derived-cache review findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| CACHE-001 | High | Cache reads checked and resolved the public pathname before giving it to SQLite, so a concurrent link substitution could redirect a transient read outside the collection. | 0.3.11 | Resolved in ADR 0048 |
| CACHE-002 | High | Cache writes use check-then-open pathname access without a dedicated inter-process lock or atomic publication, allowing path substitution, racing updates, and an interrupted update to affect the public cache directly. | 0.3.12 | Resolved in ADR 0049 |
| CACHE-003 | Low | Video-cache output calls every absent record a miss and promises incremental updates without saying how many fingerprints were successfully persisted; `--no-cache` is mixed into the same hit/miss sentence. | 0.3.16 | Resolved in ADR 0053 |
| CACHE-004 | Medium | Shared-schema creation used `executescript()` inside legacy migration even though that API may commit a pending transaction before executing, weakening the cache service's all-or-nothing migration guarantee. | 0.4.3 | Resolved with transaction-preserving statements and rollback regression coverage |
| CACHE-005 | Low | Schema signatures were stored as several module globals despite the project's rule that assigned constants represent durable persisted identifiers only. | 0.4.3 | Resolved by constructing validation signatures locally; only persisted cache identifiers remain constants |
| CACHE-006 | Medium | The existing coordinated cache reader creates the persistent lock when absent, so reusing it for status would violate a zero-write inspection contract. | 0.4.4 | Resolved with a descriptor-pinned read-only snapshot that creates no lock or other state |
| CACHE-007 | Medium | A cached relative observation containing a symbolic-link parent could redirect a metadata freshness check outside the selected collection. | 0.4.4 | Resolved with collection-anchored no-follow descriptor traversal |
| CACHE-008 | Low | Cache status composed independently validating readers and therefore rescanned every current cache row three times before reporting it. | 0.4.4 | Resolved with one validated aggregate snapshot read |
| CACHE-009 | High | Generalizing the video-cache reader to an external directory initially retained a pinned safe read but omitted the final public-entry identity check, allowing a concurrent replacement to go unreported. | 0.4.5 | Resolved by rechecking the locked public entry after the SQLite read and retaining the path-swap regression |
| CACHE-010 | Medium | Two simultaneous writers creating a previously absent cache lock can race on macOS and make one writer fail with `ENOENT` instead of serializing. | 0.4.6 | Resolved with a pinned exclusive-create-or-open sequence and concurrent first-writer regression coverage |
| CACHE-011 | Medium | Cache status checked every observation's relative path against the selected collection without interpreting its scope, so a multi-collection external cache could misreport another collection's coincidentally matching path as current. | 0.4.6 | Resolved by requiring the path-private root identity scope before an observation can be current |
| CACHE-012 | Low | Publishing one whole-file observation per video would serialize, validate, sync, and atomically replace the complete cache for every inspected file, adding avoidable storage latency. | 0.4.6 | Resolved with validated configurable batches that retain incremental interruption recovery |
| CACHE-013 | Low | Exact-video reruns reused stable whole-file hashes but still invoked ffprobe for every file even when the same normalized structure had already been established under the same tool runtime. | 0.4.8 | Resolved with strict content/algorithm/runtime-keyed probe evidence |
| CACHE-014 | Medium | Probe reuse needs a field-exact payload validator; accepting merely valid JSON could let malformed dimensions, timing, or audio shape enter exact-video candidate grouping. | 0.4.8 | Resolved with strict typed payload decoding and fail-closed status/consumer tests |
| CACHE-015 | Low | Publishing hashes and probes through separate staged replacements would double durable cache publication work and allow one inspection batch to become only partially represented between updates. | 0.4.8 | Resolved with one combined atomic batch transaction |
| CACHE-016 | Low | A pre-hash “probes required” estimate would be false when a newly added path hashes to content whose probe is already cached. | 0.4.8 | Resolved by reporting compatible records at lookup and observed reused/computed counts after inspection |
| CACHE-017 | Low | Exact-image reruns decoded every unchanged image through Pillow even after the same displayed pixels had been established for the same bytes and runtime. | 0.4.9 | Resolved with content/algorithm/Pillow-runtime-keyed pixel evidence |
| CACHE-018 | High | A displayed-pixel group derived from a reused byte hash must not authorize mutation solely from disposable cache state. | 0.4.9 | Resolved by descriptor-pinned byte recomputation before any image apply state is created |
| CACHE-019 | Medium | Image-cache payloads, external target selection, and complete cache opt-out needed the same fail-closed and no-local-write boundaries as video evidence. | 0.4.9 | Resolved with strict payload validation plus external and `--no-cache` regressions |
| CACHE-020 | Medium | Exact-image inspection and duplicate grouping were one operation, so image cache warming would either duplicate analysis policy or perform work outside its stated cache-only contract. | 0.4.10 | Resolved by separating reusable inspection/publication from grouping while retaining the finder wrapper |
| CACHE-021 | Medium | A combined image/video warm could publish image evidence before discovering an invalid video layout or missing native tool, leaving state from a setup-invalid request. | 0.4.10 | Resolved with complete selected-layout, discovery, and native-tool preflight before the first cache write |
| CACHE-022 | Low | Generalized warming needed selector-specific option validation, privacy, external-cache, empty-input, and no-mutation tests rather than assuming the video-only guarantees transferred automatically. | 0.4.10 | Resolved with explicit selector contracts and focused integration coverage |
| CACHE-023 | Medium | Warming intentionally reuses compatible evidence, so it cannot prove that a selected derived record was recomputed after a tool/runtime concern or deliberate audit request. | 0.4.13 | Resolved with explicit image, video, standard-validation, and full-validation refresh targets that bypass reusable selected evidence |
| CACHE-024 | Medium | A targeted refresh implemented as cache deletion would discard unrelated algorithms, profiles, runtimes, collection scopes, or media evidence and weaken resumability. | 0.4.13 | Resolved by atomic selected-key upserts with unrelated-record retention coverage |
| CACHE-025 | Low | Reusing the validation cache-assisted mode for refresh would silently preserve old health rather than recording a current check. | 0.4.13 | Resolved by routing both validation refresh targets through the always-fresh validation path |

## Checksum-read review findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| SCAN-004 | High | Checksum scan opened a pathname between state checks, allowing a transient parent or file substitution to redirect content reads outside the collection before the later change was noticed. | 0.4.6 | Resolved by hashing through the collection-anchored stable no-follow descriptor boundary |

## Package architecture review findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| ARCH-001 | Low | Cache schema, publication, observation policy, status, warming, and command-dispatch modules shared one derived-state lifecycle but were scattered across the package root without a discoverable subsystem boundary. | 0.4.7 | Resolved in ADR 0065 |
| ARCH-002 | Low | Splitting modules by size alone would create new interfaces across cohesive action-journal and exact-media invariants without improving dependency direction or ownership. | 0.4.7 | Accepted and documented in ADR 0065 with explicit future extraction criteria |
| ARCH-003 | Low | Scan, validation, rename, duplicate analysis, and cache warming imported media classification from the organizer command, giving shared policy misleading command ownership. | 0.4.7 | Resolved by the shared classification foundation in ADR 0065 |
| ARCH-004 | Low | Writable cache paths and complete descriptor hashing were implemented under the video duplicate command even though image and video producers share both policies. | 0.4.9 | Resolved by shared cache target and hash primitives in ADR 0068 |

## Progress and timing review findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| PROG-001 | Low | Exact-video fingerprinting forces a completed-work progress row after every candidate, producing hundreds of rows on large collections and an immediate extra row after a heartbeat even when the configured interval is not due. | 0.3.13 | Resolved in ADR 0050 |
| PROG-002 | Low | A long-item heartbeat reuses the completed-work formatter, so it repeats stale throughput and a volatile ETA while no additional work has completed; ETA also appears after only one observation. | 0.3.14 | Resolved in ADR 0051 |
| PROG-003 | Low | The CLI reports only whole-command runtime, so an expensive exact-video run does not reveal whether discovery, probing, fingerprinting, planning, mutation, or verification consumed the time. | 0.3.15 | Resolved in ADR 0052 |

## Output privacy review findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| OUT-001 | Low | Duplicate-finder previews always print collection paths, filenames, per-group plans, and skipped-file details, leaving no concise aggregate mode for private logs or quick status checks. | 0.3.17 | Resolved in ADR 0054 |
| OUT-002 | Low | Wall-clock correlation required an opt-in flag, so ordinary long-running console records lacked timestamps even though elapsed and stage durations were available. | 0.3.18 | Resolved in ADR 0055 |
| OUT-003 | Low | Help and argument errors raised by a dispatched command parser were followed by the outer CLI's timestamped stopped-runtime message. | 0.4.4 | Resolved by recognizing parser exits and leaving their output plain |
| OUT-004 | Medium | Global configuration options were inserted before nested cache arguments, which would make the cache dispatcher parse an option where it required the action verb. | 0.4.5 | Resolved by forwarding applicable global options immediately after the `warm` action and retaining status-option refusal |
| OUT-005 | Low | The first nested cache dispatcher exposed a generic implementation-oriented remainder positional in top-level help instead of describing the supported operations. | 0.4.5 | Resolved with documented `status` and `warm` subparsers that delegate their own detailed help |

## Documentation review findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| DOC-001 | Low | The roadmap claimed released rows were removed even though it retained the stabilization ledger, while the README still described the completed validation review as future work. | 0.3.19 | Resolved in ADR 0056 |

## Release groups

- `0.2.2`: establish ADRs and the locked Ruff, Black, mypy, pre-commit, and
  coverage-aware test-quality baseline; document the actual platform boundary.
- `0.2.3`: harden append-only journal grammar, stable file identity, path
  component checks, and post-operation verification.
- `0.2.4`: make exact-media analysis stable under changes and make corrupt or
  malformed image, video, and cache inputs fail or skip conservatively.
- `0.2.5`: correct changing-file scan reports and interruption behavior.
- `0.2.6`: split high-risk orchestration into testable stages and consolidate
  duplicate utilities without changing command behavior.
- `0.3.0`: add report-only validation after all preceding findings are closed or
  explicitly accepted in an ADR.
- `0.3.1`: preserve path privacy, surface incomplete traversal, minimize native
  tool output, and make changed-file findings supersede decoder conclusions.
- `0.3.2`: split validation discovery, stream policy, execution options, and
  report options into typed, independently reviewable stages.
- `0.3.3`: pin classification and decoder reads to stable, descriptor-relative,
  no-follow file handles beneath the collection root.
- `0.3.4`: separate durable research, roadmap, shipped behavior, review, and
  decision records under an indexed documentation tree.
- `0.3.5`: report the complete ordered scan action plan when both organization
  and deterministic renaming are applicable.
- `0.3.6`: reproduce the locked release gate in CI, use short-lived branches,
  and make descriptor-backed content classification portable to GNU `file`.
- `0.3.7`: retain pre-merge and post-merge platform evidence while eliminating
  redundant private-repository branch and tag runs.
- `0.3.8`: pin all exact-video content reads to stable no-follow descriptors.
- `0.3.9`: record the unavailable private-Free protection boundary and the
  exact `main` ruleset to activate when the repository becomes eligible.
- `0.3.10`: pin exact-image pixel decoding to stable no-follow descriptors.
- `0.3.11`: pin SQLite cache reads to a stable no-follow collection descriptor.
- `0.3.12`: serialize cache access and atomically publish complete, validated,
  durable cache replacements without writing through the public pathname.
- `0.3.13`: replace forced per-item completion rows with stable count milestones,
  due interval reports, and one final completed-work row.
- `0.3.14`: separate active-item heartbeat facts from completed-work estimates
  and require three completed observations before projecting an ETA.
- `0.3.15`: retain total runtime while reporting each executed exact-video
  pipeline stage independently with path-private monotonic timing.
- `0.3.16`: distinguish reusable cache records, required fingerprints, durable
  new records, and the complete no-read/no-write cache opt-out.
- `0.3.17`: add an explicit aggregate, path-private report mode for image and
  video duplicate scans, applies, and undo previews.
- `0.3.18`: timestamp normal human-readable console records by default, retain
  the explicit compatible spelling, and provide a plain-console opt-out without
  affecting structured JSON.
- `0.3.19`: reconcile the roadmap's retained release ledger and repository
  next-work guidance with the completed 0.3 stabilization.
- `0.4.0`: surface scan traversal failures, recommend validation before
  mutation, and prove corrupt or unsupported media remain visible findings
  without becoming automatic ignore policy.
- `0.4.1`: require complete namespace enumeration for mutation planning, undo
  simulation, duplicate analysis, and post-operation layout verification.
- `0.4.2`: require no-follow metadata inspection for every enumerated entry and
  reject names that disappear or change walk category before a plan is trusted.
- `0.4.3`: extract the shared cache safety and schema service, retain atomic
  legacy migration, and reject malformed generic evidence before reuse.
- `0.4.4`: expose strictly read-only cache health and evidence coverage without
  creating coordination state or following observed path components.
- `0.4.5`: warm strict exact-video evidence independently of duplicate planning,
  including an explicitly external writable-cache boundary.
- `0.4.6`: reuse exact-state whole-file hashes without making scan stateful,
  descriptor-pin checksum reads, and re-read cached content before mutation.
- `0.4.7`: establish the cache subsystem facade and document the package-wide
  ownership and dependency rules without changing behavior.
- `0.4.8`: reuse strictly validated, ffprobe-runtime-keyed normalized video
  structure and publish each hash/probe batch atomically.
- `0.4.9`: reuse strictly validated, Pillow-runtime-keyed displayed-pixel
  evidence and recheck cached content before image mutation.
- `0.4.10`: warm image, video, or all supported evidence without duplicate
  planning and preflight a combined request before its first cache write.
- `0.4.11`: persist strictly validated fresh health evidence without using old
  health to satisfy a current validation request.
- `0.4.12`: reuse exact compatible health only under an explicit flag, with
  every miss falling back to current descriptor-pinned validation.
- `0.4.13`: force recomputation of one named evidence family without deleting
  unrelated disposable records or changing media and action history.

## Independent review evidence

- Baseline: 103 tests passed under the locked Python 3.11 environment.
- Ruff found import, modernization, closure-binding, and unused-import issues;
  its optional complexity pass identified the orchestration hotspots in
  REV-010.
- Independent typing found unsafe object narrowing in action-log deserialization
  and an imprecise selector file-object type.
- A first parent-only coverage run reported a misleading 42 percent. After
  subprocess instrumentation and direct adversarial tests, the current 167
  tests pass and the same suite reports 86 percent across real CLI child
  processes.

No private collection, path, filename, statistic, or media content was used or
recorded during this review.
