# ADR 0066: Cache normalized video probes by content and runtime

- Status: Accepted
- Date: 2026-08-22

## Context

Stable whole-file observations avoid rereading unchanged videos solely to
recover their content hashes, but every exact-video rerun still invokes
ffprobe. Probe output determines dimensions, supported stream shape,
orientation, timing, audio layout, and candidate buckets. These facts are
expensive enough to reuse, but raw ffprobe JSON is broader and less stable than
the normalized facts pymo actually trusts.

A path and timestamp are not sufficient derived-evidence keys. Different
ffprobe builds can interpret media differently, a newly added path may contain
already known bytes, and malformed cached structure must never enter exact
grouping.

## Decision

Persist only pymo's normalized `ProbeInfo` facts as the `video-probe` evidence
type. Key reuse through the shared derived-evidence identity: complete-file
SHA-256, `ffprobe-structure-v1` algorithm, and the exact first-line ffprobe
runtime identifier. A new path may reuse evidence only after its bytes are
freshly hashed to the same content identity. A changed algorithm or runtime is
a cache miss.

Decode compatible payloads through an exact field schema. Require positive
dimensions and duration, integer timing, a boolean audio marker, and a
self-consistent all-null or fully valid audio shape. Malformed selected
evidence fails closed; cache status validates every known probe payload but
does not invoke ffprobe to claim runtime compatibility.

Publish each bounded inspection batch's new file observations and normalized
probes in one locked, staged, validated, atomic cache update. Report loaded
compatible records before work and actual reuse, computation, and publication
after work so newly hashed copies do not make the estimate misleading.

## Consequences

Repeated video scans and explicit warms avoid redundant ffprobe processes for
unchanged content while retaining runtime invalidation. Collection growth is
incremental: new bytes are probed once, while a new copy of known bytes can
reuse normalized structure after hashing.

The cache remains disposable acceleration. Exact-video apply still freshly
recomputes every reused whole-file hash that contributes to a move, so cached
probe evidence cannot independently authorize mutation. `--no-cache` disables
hash, probe, and fingerprint cache reads and writes together.
