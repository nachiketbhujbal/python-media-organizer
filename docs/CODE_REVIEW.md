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

## Scan review findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| SCAN-001 | Low | Scan counted non-canonical media names but suppressed rename advice whenever organization was also needed, even though it continued to show later duplicate-finder recommendations. | 0.3.5 | Resolved in ADR 0040 |

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

## Progress and timing review findings

| ID | Severity | Finding | Resolution target | Status |
| --- | --- | --- | --- | --- |
| PROG-001 | Low | Exact-video fingerprinting forces a completed-work progress row after every candidate, producing hundreds of rows on large collections and an immediate extra row after a heartbeat even when the configured interval is not due. | 0.3.13 | Resolved in ADR 0050 |
| PROG-002 | Low | A long-item heartbeat reuses the completed-work formatter, so it repeats stale throughput and a volatile ETA while no additional work has completed; ETA also appears after only one observation. | 0.3.14 | Resolved in ADR 0051 |
| PROG-003 | Low | The CLI reports only whole-command runtime, so an expensive exact-video run does not reveal whether discovery, probing, fingerprinting, planning, mutation, or verification consumed the time. | 0.3.15 | Resolved in ADR 0052 |

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
- `0.3.x`: close any remaining validation safety findings without crossing the
  approved version boundary.

## Independent review evidence

- Baseline: 103 tests passed under the locked Python 3.11 environment.
- Ruff found import, modernization, closure-binding, and unused-import issues;
  its optional complexity pass identified the orchestration hotspots in
  REV-010.
- Independent typing found unsafe object narrowing in action-log deserialization
  and an imprecise selector file-object type.
- A first parent-only coverage run reported a misleading 42 percent. After
  subprocess instrumentation and direct adversarial tests, the current 161
  tests pass and the same suite reports 86 percent across real CLI child
  processes.

No private collection, path, filename, statistic, or media content was used or
recorded during this review.
