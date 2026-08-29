# ADR 0005: Package under `src` with one `pymo` CLI

- Status: Accepted
- Date: 2026-08-21

## Context

Independent scripts had duplicated setup and were harder to install reliably.

## Decision

Use the `src/pymo` package layout and expose all tools through the `pymo`
console command with explicit subcommands.

## Consequences

Imports test the installed package structure, shared policy has one home, and a
single tool installation provides every command.
