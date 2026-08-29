# ADR 0082: Correct truthful media extensions reversibly

- Status: Accepted
- Date: 2026-08-29

## Context

Validation can already distinguish a non-media file wearing a media extension
from media whose decoded image format or confidently probed video container
disagrees with its suffix. Reporting that mismatch is necessary but leaves a
false name in place for organization, deterministic renaming, and migration.
Extension correction changes no media bytes, but it is still a filesystem
mutation and therefore needs the same preview, collision, journal, verification,
and undo boundaries as every other pymo operation.

Filename extensions are not one-to-one format identifiers. JPEG and TIFF have
valid synonyms. Several video suffixes intentionally accept one family, and
ffprobe groups materially different containers into shared demuxer families
such as MOV/MP4/3GP and Matroska/WebM. Runtime decoder registries can also vary
by platform. A correction policy inferred from whichever decoder happens to be
installed would therefore be unstable and could replace one truthful name with
an unjustified preference.

## Decision

Add `pymo correct-extensions COLLECTION`. It runs after fresh validation and
before organization or deterministic renaming. It previews by default,
requires `--apply` to rename files, and supports `--undo`, which is also a
preview unless combined with `--apply`.

Discover the complete collection through the shared fail-closed traversal.
Keep packaged ignores active, never inspect or mutate the protected `dups`
tree, never follow symbolic links, and exclude pymo-owned state. Incomplete
enumeration or an uninspectable enumerated entry stops before an action log or
media state is created.

Derive every correction from fresh content reads opened through the stable,
collection-anchored no-follow descriptor boundary. Do not consume cache or a
prior validation result. For images, require a successful Pillow integrity
check and a decoded format present in packaged correction policy. For videos,
require a successful extensionless ffprobe result, at least one video stream,
an integer content-probe score from 50 through 100, a well-formed demuxer
family, and a family present in packaged correction policy. A failure, weak
probe, unsupported format, changing input, or unmapped family remains
untouched.

Store correction policy only in packaged TOML defaults. Each supported image
format or video family lists its canonical extension first followed by accepted
synonyms. Keep an already accepted synonym unchanged. Do not expose these maps
to collection configuration. Omit shared MOV/MP4/3GP and Matroska/WebM
families because ffprobe's family evidence cannot select one truthful canonical
container name from those alternatives. Custom classification extensions do
not gain correction authority.

When evidence is conclusive and the current extension is not accepted, replace
only the final suffix with the packaged canonical extension. Reuse the existing
Finder-style numbered collision planner, then execute each rename through the
descriptor-relative atomic no-replace action-log boundary. Record the run
under a distinct `correct_extensions` tool identifier while retaining the
ordinary `RENAME` action operation. This keeps the operation semantics stable
and lets history distinguish a truth correction from deterministic naming.
Hash the evidenced stable descriptor for the journal identity before any
mutation, verify every applied target, and use the shared dependency-aware undo
planner. A later organization, deterministic rename, or duplicate move touching
the same path or identity blocks correction undo until the later run is undone.

## Consequences

- A confidently identified MPEG transport stream with a false suffix can
  become `.ts`, and a decoded PNG wearing `.jpg` can become `.png`, without
  changing their bytes.
- Valid synonyms such as `.jpeg` and `.tiff` remain stable. Shared or weak video
  evidence, unsupported images, corrupt files, non-media `.ts` files, and
  custom extensions are never guessed into a new suffix.
- Dry runs and failed preflight create no journal or media state. Applied runs
  remain collision-safe, append-only, verifiable, and reversible.
- The command deliberately repeats fresh content inspection even when
  validation cache evidence exists. Migration sign-off remains a separate
  fresh directional verification step.
