# ADR 0085: Use filesystem identity for migration roots

- Status: Accepted
- Date: 2026-09-06

## Context

`pymo verify-migration SOURCE DESTINATION` requires two distinct, non-nested
collection roots because comparing one physical namespace with itself can
produce a vacuous complete result. Version 0.5.11's guided migration
coordinator enforces that boundary with no-follow device-and-inode ancestry,
but the standalone verifier still compares resolved path spellings.

On a case-insensitive or Unicode-normalizing filesystem, two textually
different resolved paths can therefore name the same directory. Case folding
is not a portable correction because the same spellings may identify genuinely
different directories on a case-sensitive filesystem.

## Decision

Version 0.5.12 places directory identity and ancestry comparison in the shared
`pymo.migration.roots` boundary used by both the standalone verifier and the
guided coordinator. Existing collection roots must have stable no-follow
directory identities. The comparison walks existing ancestors and rejects
equal or nested device-and-inode identities regardless of path spelling.

An operating-system error while establishing identity is an invalid setup and
returns status 2 without beginning configuration loading, discovery, hashing,
decoding, reporting, or any write. A missing or non-directory collection root
retains its existing setup error. The coordinator separately retains its
ability to compare a not-yet-created private log-directory leaf through the
same ancestry primitive.

The verifier's report schema, preservation layers, path privacy, and zero-write
contract do not change. Distinct directories remain valid even when their
spellings differ only by case on a case-sensitive filesystem.

## Consequences

- One physical directory cannot serve as both sides of standalone migration
  verification through a case, Unicode, or other filesystem alias.
- Direct verification and guided migration share one identity definition
  instead of maintaining parallel lexical and filesystem-aware checks.
- Device-and-inode identity remains a POSIX filesystem boundary; it does not
  infer equivalence from names and does not follow a symbolic-link identity.
- Focused regressions exercise aliased roots where the filesystem exposes an
  alias, distinct case-sensitive roots elsewhere, existing nesting, fail-closed
  identity errors, privacy, and zero-write behavior.
