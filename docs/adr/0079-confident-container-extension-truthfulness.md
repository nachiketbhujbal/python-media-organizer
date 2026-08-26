# ADR 0079: Report confident container and extension mismatches

- Status: Proposed
- Date: 2026-08-26

## Context

Validation can establish that a file contains real video while still overlooking
that its filename extension names a different container family. This is distinct
from `extension_content_mismatch`, which means a meaningful local content
signature established that the file is not media at all.

ffprobe already identifies the selected demuxer while performing standard video
validation. Reusing that observation can make misleading video names visible at
no additional probe cost. Exact string equality is not truthful, however:
ffprobe intentionally reports shared demuxer families such as
`mov,mp4,m4a,3gp,3g2,mj2` and `matroska,webm`, and weak probes of elementary or
ambiguous streams may select a demuxer without enough evidence to accuse the
filename.

Validation evidence is disposable and algorithm-versioned. Changing the
meaning of a persisted result must not make an older record structurally
invalid, because cache status and deliberate refresh need to remain the safe
recovery path rather than forcing a user to move a valid historical cache aside.

## Decision

Standard and full validation will report a distinct warning-severity
`container_extension_mismatch` finding only when all of these conditions hold:

- ffprobe completed successfully and returned a non-empty demuxer family;
- ffprobe reported an integer probe score of 100;
- the configured video extension has an explicit packaged container-family
  policy; and
- the returned demuxer family is outside that extension's accepted family.

Shared demuxer families are treated as one accepted family. Missing, malformed,
or weaker probe scores, missing family data, and unmapped extensions produce no
container accusation. The policy is packaged validation behavior, not a
collection override: custom configuration remains unable to redefine it. The
packaged policy must cover every packaged video extension exactly.

The finding is recorded before optional full decoding, so a later decode error
does not discard truthful probe or stream findings. It does not change the
validation report schema because finding codes are data rather than an
enumerated schema field.

Persisted validation algorithms advance from version 1 to version 2 for both
profiles. Version-1 validation payloads remain structurally recognized and are
reported as stale, but they are never reusable under version-2 semantics.
Targeted validation refresh accepts a structurally valid version-1 cache,
recomputes the selected profile, publishes version-2 evidence, and preserves
unrelated records. Unknown or malformed algorithms continue to fail closed.

## Consequences

Validation can distinguish a real but misleadingly named video container from a
non-media file wearing a media extension. Warning severity keeps the collection
health exit status successful while preserving actionable naming evidence.

The confidence boundary deliberately misses some real mismatches. In
particular, low-confidence raw or program-stream MPEG observations are not
accused, and shared demuxer pairs such as MOV/MP4 and Matroska/WebM cannot always
be distinguished by ffprobe's family alone. Avoiding a false claim is preferred
to exhaustive naming enforcement.

Existing validation cache data becomes stale rather than corrupt. Ordinary
validation remains fresh by default, explicit reuse misses safely, cache status
can explain the stale records, and targeted refresh provides the supported
in-place upgrade without weakening fail-closed cache validation.
