# ADR 0054: Offer explicit path-private duplicate summaries

- Status: Accepted
- Date: 2026-08-22

## Context

The duplicate finders intentionally print detailed retained, duplicate, and
destination paths so a normal dry run can be reviewed before apply. That output
is useful interactively but unsuitable for a concise status check or a log that
must not contain collection and filename information. Quiet mode removes all
normal results, while verbose mode adds diagnostics; neither provides an
aggregate middle ground.

The image and video finders share the same group, move, storage, action-log,
undo, and verification concepts. A reporting option should therefore have the
same privacy and safety contract in both commands.

## Decision

Add command-specific `--summary` to both duplicate finders. Preserve aggregate
progress, media and group counts, storage figures, cache activity, stage timing,
final results, dry-run guidance, skip counts, and verification outcomes. Omit
collection paths, filenames, action-log paths, run IDs, group and action
listings, per-video start rows, and individual skip details.

Apply the same privacy boundary to forward dry runs, explicit applies, and undo
previews or applies. Hide path-bearing error details behind guidance to rerun
without summary when diagnosis is required. Reject `--summary` together with
`--show-ignored`, because the latter explicitly requests collection-relative
path disclosure.

Do not alter analysis, keeper selection, move planning, collision checks,
cache behavior, action history, verification, exit status, or dry-run default.
`--apply` remains independently explicit.

## Consequences

Users can capture useful duplicate statistics and outcomes without disclosing
their collection structure or filenames. A standard dry run remains the best
way to review exact planned paths before applying, while an explicit summary
apply is available when aggregate output is preferred.

Summary mode is a human-readable privacy boundary, not a machine-readable
schema. Stable automation should wait for a separately designed structured
result contract rather than parse console wording.
