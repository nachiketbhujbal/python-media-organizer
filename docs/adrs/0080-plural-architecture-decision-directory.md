# ADR 0080: Use a plural architecture-decision directory

- Status: Accepted
- Date: 2026-08-26

## Context

The documentation tree stores an indexed set of architecture decision records,
but its directory was named `docs/adr/` in the singular. The singular name is
understandable for one record, while the directory itself represents the plural
collection and is referenced throughout repository instructions and
documentation.

## Decision

Store the complete indexed decision set under `docs/adrs/`. Preserve every
existing numbered filename and record while updating all tracked links and
current path references to the plural directory.

This supersedes only the directory-location wording in earlier records. Their
substantive decisions and append-only history remain accepted and unchanged.

## Consequences

- The directory name now describes the plural set it contains.
- Current repository links, instructions, and coordination rules use one path.
- Historical commit paths and external bookmarks to `docs/adr/` do not resolve
  in the current tree; Git history still preserves the prior location.
- Runtime behavior, package APIs, configuration, tests, and media safety are
  unchanged.
