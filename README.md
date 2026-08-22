# python-media-organizer

`python-media-organizer` is a local-first, reversible toolkit for organizing
personal media collections. Its command is `pymo`.

The project defaults to previews, never deletes media, never overwrites an
existing file, and does not include telemetry, cloud services, hosted AI, or
automatic uploads. Every applied file operation is recorded in the collection
it belongs to.

## Requirements and installation

- Python 3.11 or newer
- uv 0.12 or newer for the reproducible development workflow
- Pillow, installed from `pyproject.toml`
- FFmpeg and ffprobe for exact video duplicate detection
- pytest only for development and testing

On macOS, FFmpeg can be installed with Homebrew:

```bash
brew install ffmpeg
brew install uv
```

Clone the repository, then create the locked development environment and run
the command:

```bash
uv sync --locked
uv run pymo --version
```

uv creates and maintains the project `.venv` automatically. To install a
snapshot of the command outside the development environment, run
`uv tool install .` from the repository. The package is not published to PyPI
yet. Standard tools remain compatible: `python -m pip install .` installs a
local checkout because the build metadata follows PyPA standards.

FFmpeg is intentionally an explicit system dependency. A Python wrapper would
still require a native binary while making its provenance and updates less
clear.

## Collection layout

The current convention uses four-character folder names:

```text
media-collection/
  pics/                 organized pictures
  vids/                 organized videos
  dups/
    pics/               exact picture copies isolated for review
    vids/               exact video copies isolated for review
  media-collection-actions-log.jsonl
                        portable append-only action history, after an apply
  .pymo.toml            optional collection-specific configuration
  .pymo.sqlite3         disposable video fingerprint cache, after an apply
  other files           non-media files at the collection root
```

The two duplicate finders have strict ownership. The image finder reads only
`pics` and writes only `dups/pics`; it does not require or touch the video
folders. The video finder reads only `vids` and writes only `dups/vids`; it does
not require or touch the picture folders.

## Configuration and ignored metadata

Every forward command uses the same local-only TOML configuration system.
Packaged defaults automatically ignore common operating-system and tool state,
including macOS `.DS_Store` and AppleDouble files, Windows thumbnail and
desktop metadata, recycle/index directories, Synology and archive metadata,
version-control directories, the optional pymo config, and pymo's disposable
SQLite cache. These paths are left exactly where they are: they are not moved,
renamed, fingerprinted, deleted, or written to the action log.

The built-in rules are always active and require no file in a collection. To
extend them for one collection, add `.pymo.toml` at its root:

```toml
version = 1

[ignore]
files = ["*.tmp", "incoming/*.sidecar"]
directories = ["archive", "exports"]

[classification]
image_extensions = [".garden"]
video_extensions = [".city"]
video_application_mime_types = ["application/x-city"]
generic_mime_types = ["application/x-generic"]

[rename]
noise_tokens = ["planter"]

[image_duplicates]
extensions = [".flower"]

[video_duplicates]
decode_timeout_seconds = 3600
```

Patterns are case-insensitive and match either a basename or a path relative
to the collection. An ignored directory protects its whole subtree. pymo
reports how many file or directory entry points it ignored without listing
private names by default.

To review exactly which paths were ignored, opt in explicitly:

```bash
pymo --show-ignored organize "/path/to/media-collection"
pymo find-image-duplicates "/path/to/media-collection" --show-ignored
```

The list is deterministic and relative to the media-collection root, so it
does not expose the root's absolute location. `--verbose` alone does not reveal
ignored names. Combining `--show-ignored` with `--log-file` intentionally
records those displayed relative paths in the requested log.

Custom arrays extend rather than replace packaged defaults. Classification
extensions are conservative filename fallbacks when content detection is
generic or unknown. Image-duplicate extensions select files for Pillow to
inspect; unreadable formats are still skipped. Rename noise tokens remove
additional unhelpful filename words. A command-line `--decode-timeout` takes
precedence over the configured video timeout.

An alternate extension file can be selected for one command:

```bash
pymo --config "/path/to/settings.toml" organize "/path/to/media-collection"
```

`--config` replaces the collection's optional `.pymo.toml` for that command;
both choices extend the packaged safety defaults rather than disabling them.
Invalid or unsafe configuration stops the command before mutation. Undo uses
the recorded action history and does not reinterpret older actions through the
current ignore rules.

The fixed `pics`, `vids`, and `dups` ownership structure, action-log naming,
config filename, and cache filename are deliberately not configurable. They
are centralized package invariants so every command and existing action log
agrees on the same collection layout.

## Commands

Every mutating command is a dry run unless `--apply` is present. Review the
preview before applying the same command.

### Organize a collection

```bash
pymo organize "/path/to/media-collection"
pymo organize "/path/to/media-collection" --apply
pymo organize "/path/to/media-collection" --undo
pymo organize "/path/to/media-collection" --undo --apply
```

`organize` recursively flattens pictures into `pics`, videos into `vids`, and
other files into the collection root. It detects supported content signatures,
fixes media already in the wrong destination, resolves name collisions, removes
only source directories that became empty, protects the entire `dups` review
tree, and verifies the resulting layout.

Legacy `organization_manifest*.csv` files remain usable through `--manifest`
in v0.1, but using this path emits a deprecation warning. It will be removed in
v0.2.0. New operations use the shared action history instead of creating new
CSV manifests.

### Rename media predictably

```bash
pymo rename "/path/to/media-collection"
pymo rename "/path/to/media-collection" --apply
pymo rename "/path/to/media-collection" --undo
pymo rename "/path/to/media-collection" --undo --apply
```

`rename` creates deterministic names from the collection name, media kind, a
stable sequence, a trustworthy embedded or filename timestamp when available,
and useful filename words. It uses `undated` rather than inventing dates,
leaves non-media and already canonical names alone, and excludes `dups`.

It does not claim to understand the visual content. Local AI-assisted naming is
a possible future, opt-in feature.

### Find exact image duplicates

```bash
pymo find-image-duplicates "/path/to/media-collection"
pymo find-image-duplicates "/path/to/media-collection" --apply
pymo find-image-duplicates "/path/to/media-collection" --undo
pymo find-image-duplicates "/path/to/media-collection" --undo --apply
```

The image finder applies EXIF orientation, decodes to RGBA, and matches exact
displayed pixels while ignoring filenames and metadata. It keeps one original
using deterministic rules and moves extra copies into flat `dups/pics` names
such as `original_copy(1).jpg`. Animated, multi-page, unreadable, and unsafe
inputs are skipped conservatively.

Legacy `group_*` duplicate output can be previewed and migrated with
`--reorganize-existing`; `--duplicates-dir` selects that legacy source only.
Both options, the old `duplicates/` tree, and its `move_manifest*.csv` inputs
are deprecated and will be removed in v0.2.0.

### Find exact video duplicates

```bash
pymo find-video-duplicates "/path/to/media-collection"
pymo find-video-duplicates "/path/to/media-collection" --apply
pymo find-video-duplicates "/path/to/media-collection" --undo
pymo find-video-duplicates "/path/to/media-collection" --undo --apply
```

The video finder first hashes complete files, then uses ffprobe and streamed
FFmpeg decoding for plausible candidates. A strict duplicate must have the same
displayed frames, normalized frame timing, orientation, decoded audio, audio
timing, and supported stream structure. A remux can match; different audio,
different playback timing, recompression, cropping, shortening, and watermarks
do not.

Ambiguous or insufficiently tested inputs are reported and left untouched,
including corrupt files, multiple video or audio streams, attachments,
subtitles/data streams, and HDR or high-bit-depth video. Decode commands are
restricted to local file inputs and streamed output; they do not request a
camera, screen, microphone, or network source.

Applied scans may update `.pymo.sqlite3`, a disposable collection-local cache
keyed by content, fingerprint algorithm, and FFmpeg version. Dry runs may read
an existing cache but never create or change it.

Both duplicate finders report retained storage, extra-copy storage, and the
space potentially reclaimable if the isolated copies are later deleted
manually. `pymo` itself never deletes them.

## Recommended workflow

For a mixed collection, preview and then apply:

```bash
pymo organize "/path/to/media-collection" --apply
pymo rename "/path/to/media-collection" --apply
pymo find-image-duplicates "/path/to/media-collection" --apply
pymo find-video-duplicates "/path/to/media-collection" --apply
```

Image and video duplicate scans are independent and may run in either order.
Undo dependent changes in reverse order. The action log refuses an earlier undo
when a later active operation touched the same files or paths.

## Action history and undo

Each media-collection owns one append-only
`{collection-name}-actions-log.jsonl`. Records use paths relative to the
media-collection so it and its history can move together. A legacy
`media_actions.jsonl` is read without modification during previews and migrated
to the collection-named form before the next applied journal write. Its fixed
filename is deprecated and will no longer be detected in v0.2.0.
Applied operations record planned and completed actions, file identities, run
boundaries, and successful undos. Undo appends new history; it never erases the
audit trail.

Before changing anything, undo verifies all expected paths and identities. A
missing, changed, renamed, or occupied path stops the operation safely. This is
why a rename must be undone before undoing an earlier organizer run that moved
the same files.

## Deprecated compatibility

Version 0.1.5 warns when any compatibility-only interface is used. Warnings go
to stderr and remain visible under `--quiet`; the operation still behaves as it
did before. No compatibility was removed in this patch release.

| Deprecated v0.1 surface | Current architecture | v0.2.0 transition |
| --- | --- | --- |
| `organization_manifest*.csv` undo and `--manifest` | Collection-named JSONL action history | Perform any needed CSV-based undo before upgrading. |
| `duplicates/group_*`, `move_manifest*.csv`, `--reorganize-existing`, and `--duplicates-dir` | Flat `dups/pics` plus JSONL actions | Run the legacy reorganization on v0.1.5 if those results need migration. |
| Image finder `--recursive` | The finder always scans files directly inside `pics` | Stop passing the option; it is already a no-op. |
| Fixed `media_actions.jsonl` | `{collection-name}-actions-log.jsonl` | Allow an applied journal operation on v0.1.5 to migrate it before upgrading. |

Current collection-named action logs, their schema, and persisted tool/action
identifiers are not deprecated. Duplicate reports may still label matching
sets as “Group”; that display term is unrelated to the removed `group_*`
directory structure.

## Logging

Normal output uses Python's logging system while remaining friendly in a
terminal:

```bash
pymo --verbose organize "/path/to/media-collection"
pymo --quiet organize "/path/to/media-collection"
pymo --log-file "/path/to/pymo.log" organize "/path/to/media-collection"
pymo --show-ignored organize "/path/to/media-collection"
```

Persistent logs are opt-in because paths and filenames can be private. No log
file is created by default. Global logging options go before the subcommand.
`--show-ignored` is a separate privacy opt-in and may appear globally or after
the subcommand's collection argument.

## Tests

```bash
uv run --locked pytest
uv build
```

The suite uses temporary synthetic collections and tiny locally generated video
fixtures. It covers dry runs, apply, undo, collision refusal, action ordering,
content changes, strict folder ownership, exact image and video matching,
different audio and timing, corrupt/ambiguous media, derived cache behavior,
shared built-in and custom policy, malformed-config refusal, centralized
collection paths, default ignored-name privacy, explicit relative ignored-path
output, logging privacy, and the guarantee that video decoding never invokes
capture devices. Private collections and their names are not fixtures or
repository content.

## Versions and releases

Git tags are the authoritative release version. Hatchling builds the package,
and hatch-vcs derives the Python package version from tags such as `v0.1.4`;
there is no second version string to update by hand. Untagged development
commits receive a PEP 440 development version containing their Git revision.
uv manages the environment and `uv.lock`, while ordinary standards-compatible
installers can still build and install the package.

## Roadmap and research

The next major feature is a read-only `pymo scan COLLECTION` report combining
file counts, media types, storage, layout readiness, validation warnings,
duplicate potential, and estimated work. It is not implemented yet.

See `RESEARCH_IMPROVEMENTS.md` for the product research, privacy analysis,
feature ideas, local-AI guardrails, metadata and validation plans, comparison
tools, and longer-term roadmap. See `HANDOFF.md` for current engineering state
and compatibility details.
