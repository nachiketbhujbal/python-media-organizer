# ADR 0058: Keep corruption findings separate from ignore policy

- Status: Accepted
- Date: 2026-08-22

## Context

A collection may contain empty, truncated, undecodable, unreadable, changing,
unsupported, or extension-mismatched media. A first-pass command must continue
past an individual damaged file and report the incomplete evidence. Adding the
path to `.pymo.toml` would instead suppress future classification, validation,
hashing, duplicate analysis, and migration verification.

EXIF or other metadata can contribute useful provenance facts, but metadata
presence does not prove that image pixels or complete video/audio streams are
decodable. Valid media may also contain no EXIF data at all.

## Decision

Treat ignore configuration as user-authored processing policy, never as an
automatic corruption ledger. pymo does not add corrupt or unsupported paths to
`.pymo.toml` and does not recommend doing so as a recovery workflow.

`scan` remains a fast inventory and readiness pass. It reports every directory
traversal or safe-read failure it observes, does not silently describe an
incomplete tree as complete, and recommends report-only validation before
mutation. `validate` performs the integrity work: known per-file decoder
failures become aggregate findings, optional collection-relative paths remain
explicit, and processing continues for the rest of the collection. Unsupported
formats remain warnings rather than false healthy or corrupt conclusions.

Any future accepted-exception or waiver mechanism must remain visible in health
and migration reports, preserve the original finding, and require an explicit
user decision. It must not reuse ignore semantics.

## Consequences

A bad file cannot make the rest of a normal validation run disappear, and it
cannot be hidden automatically to obtain a successful report. Full validation
uses actual image-frame and video/audio decoding where supported; metadata
inspection may supplement but never replace that evidence.

Version 0.4.0 hardens scan discovery reporting, ordered validation guidance,
and corrupt-media acceptance coverage. The shared cache sequence begins at
0.4.1. Migration verification treats corrupt, unreadable, changing, and
unsupported source entries as unproven until explicitly resolved or accepted
under a future visible exception design.
