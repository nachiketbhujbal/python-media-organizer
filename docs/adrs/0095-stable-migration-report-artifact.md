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

Version 0.6.4 will export one explicit schema-versioned, deterministic,
path-private machine-readable migration report from the same validated restart
state and typed outcomes as the human synopsis. Report generation will
preflight the complete required history, perform no media analysis, and leave
collections, caches, action history, coordinator lifecycle, and private stage
outcomes unchanged.

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
- Later unattended policy, logging, visibility, duplicate disposition, queue,
  and scheduling releases remain separate decisions.
