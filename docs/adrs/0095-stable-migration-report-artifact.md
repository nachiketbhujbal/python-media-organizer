# ADR 0095: Stable migration report artifact

- Status: Accepted
- Date: 2026-09-11
- Builds on: ADR 0091

## Context

Version 0.6.2 introduced strict private stage outcomes and a concise human
synopsis. Those outcomes are version-bound coordinator bookkeeping rather than
a supported public interface, and human console wording is not a safe machine
contract. Operators and future local interfaces need one deterministic report
without parsing prose or repeating expensive collection analysis.

## Decision

Version 0.6.4 will export schema 1 through explicit `pymo migrate --json` over
an existing private coordinator run. Both the original baseline/working/log
locator and the shorter explicit `--resume PRIVATE_STATE_DIRECTORY` locator are
supported. JSON is written only to standard output; a caller may explicitly
capture it without giving pymo another filesystem-write boundary.

The deterministic, path-private machine report and existing human synopsis
will consume the same projection of validated restart state and typed outcomes.
Report generation will acquire only the existing private coordinator lock,
preflight the complete required history, recheck the state, outcome projection,
and collection identities before emission, perform no media analysis, and
leave collections, caches, action history, coordinator lifecycle, and private
stage outcomes unchanged. It cannot be combined with a workflow action.

The public schema will distinguish workflow progress, preview from apply,
simulated from observed preservation, potential from proven storage recovery,
and unsigned from signed-off completion. It will define compatibility and
safe-output behavior without exposing private roots, filenames, log paths, run
identifiers, or outcome filenames by default. The report grants no mutation,
quarantine, deletion, verification, or sign-off authority.

## Consequences

- Machine consumers receive a documented stable contract rather than private
  coordinator internals or human log text.
- The existing human synopsis and migration selectors remain compatible.
- `docs/MIGRATION_REPORT.md` defines every schema 1 field and allowed state.
  A new schema version is required before changing a field name, type, allowed
  value, or meaning; human wording is outside that compatibility contract.
- Later unattended policy, logging, visibility, duplicate disposition, queue,
  and scheduling releases remain separate decisions.
