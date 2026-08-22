# python-media-organizer

`python-media-organizer` is a local-first, reversible toolkit for organizing
personal media collections. Its command is `pymo`.

The project defaults to previews, never deletes media, never overwrites an
existing file, and does not include telemetry, cloud services, hosted AI, or
automatic uploads. Every applied file operation is recorded in the collection
it belongs to.

## Requirements and installation

- Python 3.11 or newer
- Pillow, installed from `pyproject.toml`
- FFmpeg and ffprobe for exact video duplicate detection
- pytest only for development and testing

On macOS, FFmpeg can be installed with Homebrew:

```bash
brew install ffmpeg
```

Create an isolated project environment and install the package:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pymo --version
```

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
  .pymo.sqlite3         disposable video fingerprint cache, after an apply
  other files           non-media files at the collection root
```

The two duplicate finders have strict ownership. The image finder reads only
`pics` and writes only `dups/pics`; it does not require or touch the video
folders. The video finder reads only `vids` and writes only `dups/vids`; it does
not require or touch the picture folders.

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

Legacy `organization_manifest*.csv` files remain usable through `--manifest`.
New operations use the shared action history instead of creating new CSV
manifests.

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
to the collection-named form before the next applied journal write.
Applied operations record planned and completed actions, file identities, run
boundaries, and successful undos. Undo appends new history; it never erases the
audit trail.

Before changing anything, undo verifies all expected paths and identities. A
missing, changed, renamed, or occupied path stops the operation safely. This is
why a rename must be undone before undoing an earlier organizer run that moved
the same files.

## Logging

Normal output uses Python's logging system while remaining friendly in a
terminal:

```bash
pymo --verbose organize "/path/to/media-collection"
pymo --quiet organize "/path/to/media-collection"
pymo --log-file "/path/to/pymo.log" organize "/path/to/media-collection"
```

Persistent logs are opt-in because paths and filenames can be private. No log
file is created by default. Global logging options go before the subcommand.

## Tests

```bash
.venv/bin/python -m pytest
```

The suite uses temporary synthetic collections and tiny locally generated video
fixtures. It covers dry runs, apply, undo, collision refusal, action ordering,
content changes, strict folder ownership, exact image and video matching,
different audio and timing, corrupt/ambiguous media, derived cache behavior,
logging privacy, and the guarantee that video decoding never invokes capture
devices. Private collections and their names are not fixtures or repository
content.

## Roadmap and research

The next major feature is a read-only `pymo scan COLLECTION` report combining
file counts, media types, storage, layout readiness, validation warnings,
duplicate potential, and estimated work. It is not implemented yet.

See `RESEARCH_IMPROVEMENTS.md` for the product research, privacy analysis,
feature ideas, local-AI guardrails, metadata and validation plans, comparison
tools, and longer-term roadmap. See `HANDOFF.md` for current engineering state
and compatibility details.
