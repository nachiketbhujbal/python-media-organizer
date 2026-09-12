# ADR 0101: Define visibility and privacy profiles

- Status: Accepted
- Date: 2026-09-12
- Applies: ADR 0087, ADR 0099

## Context

Pymo exposes console severity and path disclosure through separate global and
command-local flags. The controls are individually conservative, but an
operator must remember several spellings to request a coherent rich, private,
or quiet view. Logging thresholds also do not by themselves grant filename or
ignored-path disclosure, as required by ADR 0099.

Version 0.6.7 owns one compatibility-preserving profile layer over those
controls. It must not make path-bearing console output or persistent
diagnostics the default.

## Decision

Add the global selector `--visibility {full,private,quiet}`. Omitting it keeps
the existing path-private behavior. Each explicit profile resolves to the
following existing controls:

| Profile | Console threshold | Ignored paths | Affected file paths |
| --- | --- | --- | --- |
| `full` | `DEBUG` | shown | shown where the command already supports `--show-files` |
| `private` | `INFO` | hidden | hidden |
| `quiet` | `WARNING` | hidden | hidden |

The full profile adds `--show-ignored` to applicable collection commands. It
also adds `--show-files` only to validation, migration verification, migration
coordination, and cache warm or refresh, whose public parsers already own that
option. Other commands retain their existing operation-preview output rather
than receiving a new disclosure interface.

Profiles control the ephemeral console and existing disclosure switches only.
They neither create a diagnostic file nor alter its independently selected
threshold. `--log-file`, `--file-log-level`, timestamp selection, explicit
configuration, cache policy, and native-tool choices remain independent.

An explicit profile is mutually exclusive with `--verbose`, `--quiet`, and
`--console-log-level`, including the migration coordinator's command-local
forms. It is also mutually exclusive with an explicit `--show-files` or
`--show-ignored`; one invocation must use either the coherent profile or the
individual compatibility controls. These conflicts fail in the unified parser
before logging setup, collection work, or persistent state creation.

The full profile is rejected for `cache status`, whose read-only report owns no
path-disclosure switches, and with duplicate-finder `--summary`, whose explicit
contract is aggregate and path-private. Migration-report schema 1 remains
always path-private, so `--visibility full migrate ... --json` is rejected.
Private and quiet profiles remain compatible with structured output; as before,
human logging is suppressed so the selected JSON schema stays clean. Other
structured commands may honor the full profile only through their already
documented disclosure fields.

Migration coordination stores the resolved controls rather than the profile
spelling: console `DEBUG`, `INFO`, or `WARNING`, plus the two disclosure
booleans. Existing private restart-state schema 3 already represents those
values, so no schema change is required. Resume without repeating the profile
recovers them for workflow actions; repeating the same profile resolves
identically, while any different explicit workflow override fails the existing
exact-option check. A read-only migration JSON projection retains its existing
compatibility with global private or quiet output selection without treating
that selection as a saved workflow-option override.

Do not add a `--debug` alias. `--verbose`, `--console-log-level DEBUG`, and the
new full profile have deliberately different disclosure semantics; another
name would obscure rather than simplify that distinction.

## Consequences

- The default remains console `INFO` with filenames and ignored paths hidden.
- Operators can request one rich or quiet view without reconstructing several
  flags, while every legacy selector remains supported on its own.
- Full visibility is an explicit privacy decision for that invocation. It does
  not weaken path-private summary or migration-report contracts.
- No profile creates or persists ordinary diagnostics, changes an action,
  checkpoint, evidence layer, report schema, or cache guarantee, or grants
  mutation, quarantine, sign-off, or deletion authority.
- Automatic diagnostics, duplicate disposition, queueing, scheduling,
  quarantine movement, deletion, and exact-media changes remain outside
  version 0.6.7.
