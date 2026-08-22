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
| REV-008 | Medium | Checksum scan results can combine an old size with new bytes when files change during a run, and disappearing files can remain in inventory totals without a clear changed-file warning. | 0.2.5 | Open |
| REV-009 | Medium | Ctrl-C or an unexpected command failure bypasses the final elapsed-time message; a video run can therefore end with neither a clean status nor its observed runtime. | 0.2.5 | Open |
| REV-010 | Medium | Large command entry points mix discovery, analysis, reporting, cache work, planning, mutation, and verification. This raises change risk and makes safety branches difficult to unit test. Layout checks and size formatting are also duplicated. | 0.2.5 | Open |
| REV-011 | Medium | The repository had no committed lint, format, static-type, or pre-commit gate. Independent Ruff and type-checker runs found real defects plus inconsistent imports and formatting. | 0.2.2 | Resolved |
| REV-012 | Medium | Most CLI behavior tests run child processes, so ordinary coverage reports cannot observe those executed lines. Critical malformed-history, concurrent-change, cache-corruption, and interrupted-command branches were untested. | 0.2.2-0.2.5 | In progress |
| REV-013 | Low | `fcntl` makes action history POSIX-only at import time, but the supported-platform boundary was not documented in package metadata or user documentation. | 0.2.2 | Accepted in ADR 0020 |
| REV-014 | High | A destination created after the last existence check could be overwritten by the underlying rename. Collision refusal needs to be atomic, not only a preflight convention. | 0.2.3 | Resolved in ADR 0021 |

## Release groups

- `0.2.2`: establish ADRs and the locked Ruff, Black, mypy, pre-commit, and
  coverage-aware test-quality baseline; document the actual platform boundary.
- `0.2.3`: harden append-only journal grammar, stable file identity, path
  component checks, and post-operation verification.
- `0.2.4`: make exact-media analysis stable under changes and make corrupt or
  malformed image, video, and cache inputs fail or skip conservatively.
- `0.2.5`: correct changing-file scan reports and interruption behavior, then
  split high-risk orchestration into testable stages without changing commands.
- `0.3.0`: add report-only validation after all preceding findings are closed or
  explicitly accepted in an ADR.
- `0.3.x`: perform the same adversarial pass over validation and release any
  resulting corrections without crossing the approved version boundary.

## Independent review evidence

- Baseline: 103 tests passed under the locked Python 3.11 environment.
- Ruff found import, modernization, closure-binding, and unused-import issues;
  its optional complexity pass identified the orchestration hotspots in
  REV-010.
- Independent typing found unsafe object narrowing in action-log deserialization
  and an imprecise selector file-object type.
- A first coverage run reported only 42 percent because subprocess-executed
  commands are invisible to the parent coverage process. That measurement is
  not used as a quality score; REV-012 addresses the observability gap and the
  missing safety cases directly.

No private collection, path, filename, statistic, or media content was used or
recorded during this review.
