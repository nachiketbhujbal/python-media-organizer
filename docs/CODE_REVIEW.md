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
| VAL-016 | High | Validation discovery fell back to the filename extension even after the content signature positively identified non-media content, so a healthy source file sharing an extension with a media container was probed as media and reported as a decode error at failing exit status. | 0.5.5 | Resolved in ADR 0078 |
| VAL-017 | Medium | The packaged generic content types listed only the empty-result spelling produced when the utility reads a pathname, while descriptor-pinned callers read standard input and receive a different spelling, so an empty media file depended on the extension fallback that VAL-016 removed. | 0.5.5 | Resolved by packaging both spellings |
| VAL-018 | Medium | Comparing ffprobe's exact demuxer label to an extension would falsely accuse containers that share one reported family, while accepting every selected demuxer would overstate weak elementary-stream evidence. | 0.5.6 | Resolved in ADR 0079 with packaged family mappings and an extensionless content-score boundary from 50 through 100 |
| VAL-019 | Medium | Full video decoding occurred inside the probe-inspection helper, so a later decode exception discarded already established stream, duration, and container findings before the generic invalid-video result was built. | 0.5.6 | Resolved by committing probe findings before the optional full-decode stage, with a combined-failure regression |
| VAL-020 | Low | The container mismatch helper's fail-silent path for missing or malformed top-level ffprobe format evidence was documented but had no direct regression test. | 0.5.6 | Resolved with focused missing-key and non-object payload coverage |

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

## Migration-verification review findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| MIG-001 | High | Comparing paths, names, file counts, or total bytes cannot prove preservation after organization, renaming, or duplicate reduction. | 0.5.0 | Resolved with directional complete-file SHA-256 plus length identities |
| MIG-002 | High | Silently omitted source traversal, entry, read, or change failures could turn incomplete filesystem evidence into a false successful migration verdict. | 0.5.0 | Resolved with explicit incomplete evidence and an `unproven` verdict |
| MIG-003 | High | Reusing a historical hash by metadata identity alone cannot prove that the current source bytes remain readable for preservation sign-off. | 0.5.0 | Resolved with fresh stable-descriptor reads for both inventories |
| MIG-004 | Medium | Treating every reduced duplicate copy as missing data would conflate multiplicity with unique-content preservation. | 0.5.0 | Resolved by separate unique coverage and reduced/added copy accounting |
| MIG-005 | Medium | A missing source identity is not definitely absent when destination traversal or reads were incomplete; the candidate representative may be hidden by the failure. | 0.5.0 | Resolved by distinguishing `incomplete` from `unproven` based on destination evidence |
| MIG-006 | Medium | Difference reports can expose two absolute roots and private filenames, doubling the privacy surface of a normal collection command. | 0.5.0 | Resolved with aggregate defaults, root-free JSON, and explicit relative-path opt-ins |
| MIG-007 | Medium | Identical or nested roots let one inventory consume the other and make a directional comparison misleading. | 0.5.0 | Resolved by rejecting same and ancestor/descendant roots before discovery |
| MIG-008 | Low | Pymo cache, configuration, lock, staging, and action-history bytes are tool state rather than media-preservation content. | 0.5.0 | Resolved with counted, zero-read tool-state exclusion in the declared schema-1 scope |
| MIG-009 | High | Treating a metadata-varied image as byte-preserved would hide the loss of its original metadata, encoding, container, and file bytes. | 0.5.1 | Resolved with a separate exact displayed-image layer that leaves the byte verdict unchanged |
| MIG-010 | High | Similar-looking, animated, multi-page, unsafe, unsupported, unreadable, or changing images must not satisfy a deterministic content-preservation claim. | 0.5.1 | Resolved with the existing conservative single-image exact-RGBA algorithm and explicit unproven evidence |
| MIG-011 | Medium | Decoding only destination byte identities absent from the source misses a valid case where one retained source variant represents another removed metadata variant by pixels. | 0.5.1 | Resolved by inspecting one representative of every eligible destination byte identity |
| MIG-012 | Medium | Copying the displayed-pixel algorithm into migration code would allow duplicate and preservation semantics to drift. | 0.5.1 | Resolved by a shared versioned `image_content.py` normalization boundary |
| MIG-013 | Medium | A destination image decode failure can hide a representative for otherwise missing source pixels. | 0.5.1 | Resolved with an unproven image-layer verdict whenever an unmatched source pixel identity coexists with incomplete destination image evidence |
| MIG-014 | High | Treating a remuxed video as byte-preserved would hide loss of its source container, metadata, codec bitstream, and complete file bytes. | 0.5.2 | Resolved with a separate strict decoded-playback layer that leaves the byte verdict unchanged |
| MIG-015 | High | Recompressed, different-audio/timing, cropped, watermarked, ambiguous-stream, HDR/high-bit-depth, unreadable, or changing videos must not satisfy deterministic playback preservation. | 0.5.2 | Resolved by sharing the existing conservative `exact-playback-v2` probe and full-decode contract |
| MIG-016 | Medium | Fingerprinting every destination video wastes full decodes when normalized structure already proves it cannot match any source playback candidate. | 0.5.2 | Resolved by probing unique streams first and decoding only structurally relevant destination identities |
| MIG-017 | Medium | Copying probe and fingerprint logic into migration would let duplicate and preservation semantics drift. | 0.5.2 | Resolved with a shared `video_content.py` primitive boundary and independent domain policy |
| MIG-018 | Medium | A failed relevant destination video probe or decode can hide a playback representative. | 0.5.2 | Resolved with an unproven video-layer verdict whenever unmatched source playback coexists with incomplete destination video evidence |
| MIG-019 | High | Leaving command status tied to byte coverage cannot safely recognize an exact supported image transformation or video remux as content-preserved. | 0.5.3 | Resolved with an explicit layered final verdict that retains the byte result separately |
| MIG-020 | High | Reopening only previously hashed files cannot detect a new entry or directory namespace change during long media decoding. | 0.5.3 | Resolved by a fresh final discovery plus exact file-state, directory, category, and root-identity comparison |
| MIG-021 | High | Recognized source media without a supported deterministic equivalence path could otherwise be reported as definitely missing instead of unproven. | 0.5.3 | Resolved with explicit unsupported-media accounting and an unproven final disposition |
| MIG-022 | Medium | A complete collection-level result could be misread as whole-device recovery or an automatic deletion instruction. | 0.5.3 | Resolved with a named namespace-visible contract, exclusion counts, and human-signoff-only disposition |

## CI portability findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| CI-001 | Medium | Descriptor-backed classification supplied `/dev/fd/N` as a filename. BSD `file` followed it to content, while GNU `file` classified the descriptor link/device itself, causing Linux media misclassification. | 0.3.6 | Resolved in ADR 0043 |
| CI-002 | Medium | The exact-video integration fixture assumed an MP4-to-Matroska stream copy preserves canonical playback across FFmpeg releases, but container timestamp behavior can legitimately differ. | 0.3.6 | Resolved with a metadata-only, non-byte-identical stream-copy fixture |
| CI-003 | Low | Container checkout marked the worktree safe only in the action's temporary home, so Fedora pre-commit could not invoke Git afterward. | 0.3.6 | Resolved by persisting the isolated worktree trust entry |
| CI-004 | Medium | Real-media tests generated H.264 with `libx264`, an encoder intentionally absent from Fedora's official free FFmpeg build even though the product only requires decoding. | 0.3.6 | Resolved by generating synthetic fixtures with FFmpeg's native `mpeg4` encoder |
| CI-005 | Low | Branch, pull-request, mainline, and tag triggers repeated the complete three-platform matrix for the same private-repository release. | 0.3.7 | Resolved in ADR 0044 |
| CI-006 | Medium | GitHub Free does not expose branch protection or rulesets for a private repository, so `main` cannot yet reject force pushes, deletion, unchecked direct pushes, or unresolved pull-request conversations at the server boundary. | 0.3.9 | Accepted with an explicit activation prerequisite in ADR 0046 |
| CI-007 | High | Classification treated a filename MIME guess as a content signature whenever the signature utility was unavailable or failed for one file, so on a platform whose MIME database maps a configured video extension to a non-video type, genuine media was reported as a naming mismatch and never validated. macOS and Fedora agreed with the extension and passed; Ubuntu did not, and a configured extension whose guess is neither a video type nor a generic type failed the same way on every platform. | 0.5.5 | Resolved by taking configured image and video extensions before any filename guess is interpreted, and by forcing a non-video guess in the boundary tests so they hold independently of the platform database |
| CI-008 | High | A probe-score-100-only container rule depended on FFmpeg version: local FFmpeg 9 assigned 100 to a short valid MPEG transport stream, while the macOS, Ubuntu, and Fedora integration builds assigned 50, suppressing a real mismatch on all release platforms. Raw MPEG video also scored 51 and would be falsely accused under a generic MPEG extension if the boundary alone were relaxed. | 0.5.6 | Resolved by using the extensionless content-score range 50 through 100, accepting both program and raw MPEG families for generic MPEG extensions, and exercising the same descriptor path on all three platforms |
| CI-009 | High | The unshipped private-minute v0.5.8 draft used trigger-level path filters for pull requests even though a future ruleset needs one stable required check. A filtered required workflow can remain pending, GitHub diff limits can misclassify a large change, and making macOS manual would discard automatic platform evidence after public standard runners remove the minute constraint. | 0.5.8 | Resolved in the versioned workflow with a trusted exact-commit classifier that fails closed, an unconditional `quality-gate`, lightweight documentation work, and automatic three-platform work for executable changes; live trigger results remain an activation proof rather than an implementation assumption |
| CI-010 | Medium | A public transition without a root license, package license metadata, structured privacy-conscious issues, private security reporting, external-workflow approval, and verified branch/tag rules would expose the repository without its intended legal and governance boundaries. | 0.5.8 | Resolved through the accepted controlled bootstrap: the history/metadata/log audit passed, issue intake stayed closed, visibility changed while Actions was disabled, no-bypass branch and immutable-tag rules plus conservative Actions and external-approval settings were installed and verified before workflows ran, and Apache-2.0, SPDX metadata, contribution terms, issue forms, and `SECURITY.md` land in the versioned release; issues and private reporting remain closed until those files reach `main` |

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
| CACHE-026 | High | Validation evidence is keyed by content, profile, context, algorithm, and runtime, and none of those encode the validation logic itself, so adding a finding leaves prior evidence a valid hit and the new finding unreported under explicit reuse. Advancing the algorithm identifier alone does not fix it: targeted validation refresh runs through the ordinary validation entry point, which preflights the cache before doing fresh work, so every stored record becomes unusable and refresh exits before it can republish. | 0.5.6 | Resolved by recognizing version-1 algorithms as structurally valid but stale and non-reusable, reporting them as stale, and publishing version-2 records through standard/full refresh while preserving historical and unrelated evidence |

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
| ARCH-005 | Low | A finding description intended only for display was introduced as a module-level constant in validation, although module constants are reserved for explicit on-disk compatibility identifiers such as schema and algorithm versions, so the reserved set no longer described what it contained. | 0.5.5 | Resolved by inlining the description at its two report sites, matching every neighbouring finding description |

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
| DOC-002 | Medium | The planning records described a local content signature as authoritative for transport-stream extensions and carried the configuration-versus-policy question as open, after measurement established that those extensions are already packaged video extensions and that the signature utility misses common encoder output. | 0.5.4 | Resolved |
| DOC-003 | Medium | The coordination decision's ADR-number rule could not prevent the collision it described, because two branches can independently select the same next free number and each believe it holds the claim. It also defined no arbitration for a disagreement between reviewers and did not say which branch receives review-ledger changes. | 0.5.4 | Resolved in ADR 0077 |
| DOC-004 | Low | The tool-specific entry point retained a reading list and named the coordination conventions while the coordination decision required it to state no rule of its own, so the contract and its implementation disagreed. | 0.5.4 | Resolved in ADR 0077 |
| DOC-005 | Low | The promoted roadmap row and the research record promised reuse of the existing extension/content finding code for container-family mismatches, while the accepted design used a distinct code, leaving the tracked records inconsistent with the accepted plan. | 0.5.4 | Resolved |
| DOC-006 | Medium | The 0.5.5 records claimed more than the release implemented or proved: the authoritative instruction file said no native tool is invoked when a native utility makes the very determination, the roadmap marked the row released while still describing it as planned work, the decision record asserted that damaged media always retains a media or generic signature, the changelog claimed picture-extension coverage that no fixture provided, and the research record still presented the shipped behavior as scheduled work and an open question. | 0.5.5 | Resolved by narrowing each claim to what was implemented and measured, recording the epistemic limit on severely damaged media, adding the missing non-media picture-extension fixture, and closing the decided research question |
| DOC-007 | Medium | The 0.5.6 roadmap attributed raw elementary-stream protection to the probe-confidence gate even though measured evidence passed that gate and the packaged generic-MPEG family mapping supplied the protection. | 0.5.6 | Resolved by crediting the confidence gate only with suppressing weak evidence and the family map with accepting raw and program MPEG streams |
| DOC-008 | Low | The research quick-reference table grouped `.vob` with generic MPEG extensions even though the packaged policy accepts `mpegvideo` only for `.mpe`, `.mpeg`, and `.mpg`. | 0.5.6 | Resolved by splitting the table rows to match the packaged family map |
| DOC-009 | Low | The architecture-decision directory used the singular name `docs/adr/` even though it contains and indexes a plural set of decision records. | 0.5.7 | Resolved by moving the complete set to `docs/adrs/` and updating every tracked link and current path reference |

## Review waivers and follow-up debt

| Release | Waiver | Follow-up debt | Status |
| --- | --- | --- | --- |
| 0.5.7 | The maintainer waived the independent Claude review on 2026-08-29 because the release changes documentation paths and repository-local ignore boundaries only. | The next completed adversarial release review must recheck the move-only ADR diff, tracked path references, and private-state ignore boundary. | Resolved during the 0.5.8 adoption review: unchanged ADR blobs remain exact renames, intentional path-reference edits account for the modified coordination record and index, tracked references use `docs/adrs/`, both private roots are anchored in `.gitignore`, and neither root is tracked |

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
- `0.5.0`: establish fresh, path-independent directional byte coverage with
  explicit complete, incomplete, and unproven evidence states.
- `0.5.1`: layer exact displayed-image coverage over byte-missing source
  identities without weakening or relabeling the byte-preservation contract.
- `0.5.2`: layer strict decoded-playback coverage over byte-missing source
  identities without weakening or relabeling the byte-preservation contract.
- `0.5.3`: combine fresh exact-byte, displayed-image, and decoded-video
  evidence only after both declared namespaces remain stable through a final
  pass, without claiming whole-device recovery or authorizing deletion.
- `0.5.4`: record the multi-assistant coordination decision in one ADR, keep
  its conventions in the authoritative instruction file, and reconcile the
  overlapping planning records without changing runtime behavior.
- `0.5.5`: stop validating a positively identified non-media file as media
  because of its extension, report the naming mismatch as a warning instead,
  and keep an empty media file an error.
- `0.5.6`: report confidence-gated container/extension mismatches while keeping
  historical validation evidence readable, stale, and refreshable.
- `0.5.7`: pluralize the architecture-decision directory and update every
  tracked link and current path reference without changing runtime behavior.
- `0.5.8`: adopt Apache-2.0 and complete a tightly controlled public transition
  with contained event-scoped CI, structured issues, private security guidance,
  and API-verified hosted controls.

## Independent review evidence

- The maintainer explicitly transferred the Claude-authored v0.5.8 branch to
  Codex and directed a review before adoption. At that transfer boundary Codex
  traced the draft's workflow triggers and identified CI-009 plus CI-010; the
  rebased commit `35acf85` preserves the draft's authorship and subject, and the
  later owner commit resolves both findings. This requested transfer-boundary
  review closes the former straggler without leaving separate review debt.
- After rebasing onto released 0.5.7, the candidate passes all 372 tests at 88
  percent subprocess-aware coverage plus Ruff, Black, mypy, pre-commit, build,
  exact Apache-license comparison, and wheel/source license-metadata
  inspection.
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
