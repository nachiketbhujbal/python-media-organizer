# ADR 0076: Require fresh layered evidence and final namespace stability for sign-off

- Status: Accepted
- Date: 2026-08-23

## Context

Versions 0.5.0 through 0.5.2 report exact bytes, exact displayed images, and
strict decoded video as separate evidence. Keeping the command status tied to
bytes avoids a premature success claim, but it cannot express the intended
post-transformation case: a metadata-varied image or supported video remux may
be exactly represented even though its original file bytes are absent.

The final decision also cannot rely only on the state observed during initial
hashing. A file, directory, exclusion, or entry category can change while
media decoding is in progress without replacing the collection root inode.
Historical cache evidence cannot prove current readability or stability.

## Decision

Version 0.5.3 defines a `layered-exact-preservation` contract. An in-scope
source byte identity is accounted for by, in descending order, an exact byte
representative, exact displayed-image evidence, or strict decoded-video
evidence. Each unique source identity is counted once while all source copies
remain visible in file accounting. The report continues to expose every layer
separately and never relabels image or video equivalence as byte preservation.

Return `complete` only when every in-scope source identity is accounted for,
both filesystem inventories are complete, all required media formats are
supported and inspectable, and a final fresh re-discovery proves both declared
namespaces and every hashed file state remained unchanged. Return `incomplete`
for definite unaccounted supported content and `unproven` for unreadable,
unstable, unsupported, or otherwise incomplete evidence.

Migration verification reads no cache and writes no derived or authoritative
state. Policy ignores and pymo-owned state remain counted exclusions outside
the named contract. A complete result is eligible for human sign-off; it is
not an automatic deletion instruction and proves only stable namespace-visible
content in the two declared media-collection roots, never orphaned filesystem
allocations or whole-device recovery.

## Consequences

Supported exact image transformations and video remuxes can satisfy the final
preservation contract while their missing source bytes remain explicit in the
byte layer. Unknown non-media content that is definitely absent is incomplete;
recognized media that has no supported exact equivalence path is unproven.

The second namespace pass adds metadata I/O and deliberately rejects changes
during a long comparison. This cost is required for a sign-off claim. Cache
acceleration may be considered later only as a separately named non-sign-off
mode; it cannot weaken the fresh default established here.
