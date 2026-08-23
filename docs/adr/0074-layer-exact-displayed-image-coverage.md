# ADR 0074: Layer exact displayed-image coverage over missing bytes

- Status: Accepted
- Date: 2026-08-23

## Context

An image can retain exactly the same displayed pixels after metadata changes or
lossless re-encoding while its complete file bytes change. Version 0.5.0's byte
contract correctly reports that source byte stream as absent, but migration
evidence also needs to say when pymo's existing conservative image-content
definition is represented.

Migration comparison is a second consumer of displayed-pixel normalization.
Leaving that algorithm inside duplicate-move coordination would create an
incorrect dependency between two product domains and risk semantic drift.

## Decision

Move the shared descriptor-to-displayed-pixel digest into
`src/pymo/image_content.py`. The definition remains EXIF-transposed, single-
image RGBA dimensions plus exact pixel bytes under the versioned
`displayed-pixels-rgba-v1` algorithm. Duplicate analysis, cache evidence, and
migration coverage use that same invariant while retaining separate discovery,
cache, reporting, and mutation policy.

Version 0.5.1 freshly decodes only source byte identities that lack an exact
destination byte representative and have a configured exact-image extension.
It compares them against one freshly decoded representative of every eligible
destination byte identity. Byte-identical destination content is still a valid
pixel representative for another metadata-varied source identity. Animated,
multi-page, unsafe, unreadable, changing, or unsupported candidates do not
receive an exact-image claim.

Report exact-image coverage as a separate schema-2 layer. It must not rewrite
the byte verdict or describe source metadata, encoding, container structure, or
file bytes as preserved. Keep command exit status tied to the version 0.5.0 byte
verdict until version 0.5.3 defines the combined final-sign-off policy.

## Consequences

A metadata-varied or losslessly re-encoded still image can be accounted for by
exact displayed content without hiding its absent source bytes. Different or
merely similar pixels remain missing. A source decode failure makes the image
layer unproven; a destination decode failure makes an otherwise missing pixel
identity unproven because it could hide a representative.

The comparison remains fresh, local, no-follow, path-private, and zero-write.
It can be expensive because every eligible destination byte identity may need
one Pillow decode. Cache acceleration remains deferred until evidence reuse can
be proven without weakening preservation sign-off.
