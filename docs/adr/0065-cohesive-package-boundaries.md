# ADR 0065: Organize packages around cohesive subsystem ownership

- Status: Accepted
- Date: 2026-08-22

## Context

The shared cache grew from one video-specific implementation into schema,
safe-storage, status, warming, and whole-file observation modules at the package
root. Planned probe, image-fingerprint, validation, and targeted-refresh
producers would increase that surface further. Root-level filenames no longer
made the cache lifecycle or its public boundary clear.

Other large modules also merited review. Splitting every long file, however,
would create extra interfaces without necessarily improving ownership. Exact
image and video equivalence remain distinct policies, command modules map
directly to CLI verbs, and the action journal's parsing, locking, lifecycle, and
execution invariants form one authoritative unit.

## Decision

Create `pymo.cache` as the cohesive disposable-derived-state subsystem. Keep a
curated package facade for supported storage types and operations, and place
schema/publication, hash-observation policy, read-only status, deliberate
warming, and nested command dispatch in focused internal modules.

Move local content-signature and extension fallback classification into a
shared foundation module. Organization is only one consumer of this policy;
cache warming, scanning, validation, renaming, and duplicate analysis must not
import a command coordinator merely to classify media.

Retain the existing `pymo.duplicates` boundary and its image/video separation.
Keep user-facing command coordinators and shared foundation modules at the
package root. Keep the authoritative action journal outside the disposable
cache boundary and do not split it until independently owned implementations or
lifecycles justify new interfaces.

Document the intended dependency direction and judge future moves by cohesive
ownership, invariant locality, independent testing, and replacement safety—not
by line count or aesthetic symmetry.

## Consequences

Future cache producers have one discoverable home and can reuse a stable facade
without making every storage detail package-wide API. Cache commands can evolve
together while the mutation journal remains visibly distinct from disposable
acceleration state.

The refactor intentionally changes no command, configuration, schema, action
history, cache filename, or media behavior. Some large modules remain large;
that is accepted until a concrete boundary can reduce coupling rather than move
it around.
