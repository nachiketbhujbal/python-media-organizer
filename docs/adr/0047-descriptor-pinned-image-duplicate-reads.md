# ADR 0047: Pin exact-image duplicate reads to descriptors

- Status: Accepted
- Date: 2026-08-22

## Context

Exact-image analysis captured file state before a pathname-based Pillow open
and checked the pathname again after decoding. Those checks rejected a changed
result, but they could not prevent a concurrent pathname or parent-directory
swap from redirecting the transient Pillow read to unrelated local content.

Displayed-pixel equivalence, EXIF-orientation handling, animation rejection,
and deterministic keeper selection are established behavior and must not
change as part of this safety correction.

## Decision

Capture the expected regular-file state, then open each image relative to
no-follow directory descriptors anchored at the resolved collection root.
Give Pillow a non-owning binary stream over that stable descriptor, perform the
complete EXIF transpose, RGBA conversion, dimension hashing, and pixel hashing
while it remains open, then revalidate both descriptor and pathname state.

Keep discovery extension-based and preserve all existing image equivalence,
skip, keeper, reporting, move, and undo semantics. Retain candidate paths
lexically beneath the collection rather than resolving them through a
potentially transient symbolic link.

## Consequences

A concurrent link or directory swap cannot redirect exact-image pixel reads.
If the pathname changes during analysis, the original pinned content may be
decoded but the candidate is rejected and never grouped or moved. The caller
retains ownership of the stable descriptor, so Pillow cannot close the safety
handle before its final state checks.
