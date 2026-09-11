# ADR 0093: Resume migration from an explicit private state directory

- Status: Accepted
- Date: 2026-09-11
- Extends: ADR 0084

## Context

Migration restart state already records the canonical baseline and working
roots, exact pymo version, common coordinator options, ordered attempts,
current checkpoint, and creation identity inside the explicitly selected
private log directory. Resuming nevertheless requires the operator to repeat
both long collection paths, the log directory, and any saved options on every
invocation. That repetition is tedious and creates opportunities for harmless
typing failures without adding evidence or safety.

Automatically searching for state would be ambiguous and could disclose or
select the wrong collection. Allowing resume-time overrides would weaken the
exact invocation binding that makes the coordinator fail closed.

## Decision

Add `pymo migrate --resume PRIVATE_STATE_DIRECTORY` as an alternative to the
existing baseline, working, and `--log-dir` locator form. The explicit resume
directory identifies one already-created coordinator state file; pymo never
searches parent, collection, current-working, or default directories for it.

Resume may be combined with the existing status, `--run-next`, `--run`,
`--interactive`, `--accept-status`, `--confirm-quarantine`, and reviewed
`--run-next --apply` actions. It may not initialize state or combine with
positional roots or `--log-dir`. Common options are recovered from state;
explicit repetitions are accepted only when they exactly match the recorded
values, preserving the existing mismatch boundary.

Before an action, pymo validates the private directory, lock and state file,
strict schema and lifecycle, exact tool version, recorded collection roots,
root/log separation, current collection identities, option matches, and every
required typed outcome. Invalid or ambiguous input returns path-private setup
status 2 before child dispatch or mutation.

## Consequences

- A normal initial command still explicitly names both collections and a
  private log directory; persistent state remains opt-in.
- Later commands can name only that private directory and the desired existing
  coordinator action.
- Restart state remains private bookkeeping, not preservation evidence, action
  history, sign-off, or deletion authority.
- The original two-root interface remains compatible.
- Machine-readable report artifacts and unattended checkpoint policy remain
  separate later releases.
