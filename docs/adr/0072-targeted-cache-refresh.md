# ADR 0072: Refresh derived evidence by selected family

- Status: Accepted
- Date: 2026-08-23

## Context

Cache warming fills absent evidence and deliberately reuses compatible records.
That is the efficient default for repeat analysis, but it cannot satisfy a user
who explicitly wants to recompute one evidence family after questioning a
runtime, algorithm result, or prior run. Deleting the complete SQLite cache
would force the work but would also discard unrelated, valid, resumable
evidence for other media types, profiles, runtimes, and collection scopes.

Validation has an additional safety distinction. Ordinary validation is always
fresh while `--reuse-validation` is an explicit acceleration mode. A cache
refresh must not quietly consume old health evidence under a command whose
purpose is recomputation.

## Decision

Add `pymo cache refresh` with four explicit targets: `images`, `videos`,
`validation-standard`, and `validation-full`.

Image refresh recomputes every selected exact whole-file hash and displayed-
pixel fingerprint. Video refresh recomputes every selected whole-file hash,
normalized ffprobe structure, and decoded-playback fingerprint. Equivalent
content may share one derived computation within the same run, but no
persistent selected evidence is accepted as a hit. Validation refresh delegates
to the ordinary always-fresh validation path for the named profile.

Publish recomputed values through the existing locked, validated, atomic cache
service. Upsert only the selected keys. Preserve unrelated evidence and never
delete the public cache as part of refresh. Keep image/video layout rules,
external-cache policy, privacy defaults, bounded publication, and normal error
semantics unchanged.

## Consequences

Users can deliberately renew a questioned evidence family without paying to
rebuild everything else. Interrupted work retains earlier completed batches,
and an external cache continues to support read-only media collections.

Refresh is not cache repair or health certification. Structurally unsafe cache
state still fails closed, media that cannot be inspected remains visible, and
final migration sign-off still requires a fresh complete validation and the
directional preservation verifier. `--no-cache` keeps its distinct meaning of
performing no cache reads or writes; it does not mean delete or rebuild.
