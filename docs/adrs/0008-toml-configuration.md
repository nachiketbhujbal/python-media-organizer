# ADR 0008: Use validated additive TOML configuration

- Status: Accepted
- Date: 2026-08-21

## Context

Ignore rules and classification policy need customization without scattered
globals, environment variables, or unsafe executable configuration.

## Decision

Ship validated defaults in `default_config.toml`. An optional collection
`.pymo.toml` or explicit file may extend list policy and override constrained
scalar settings. Unknown or malformed keys fail before mutation.

## Consequences

Built-in safety rules cannot be disabled accidentally. Schema changes require a
versioned compatibility decision.
