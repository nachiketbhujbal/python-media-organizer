"""Explicitly populate reusable exact-video cache evidence."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pymo.config import (
    ConfigError,
    add_config_argument,
    add_show_ignored_argument,
    ignored_messages,
    load_config,
)
from pymo.discovery import DiscoveryError
from pymo.duplicates.common import duplicate_layout, layout_problems
from pymo.duplicates.videos import (
    VideoCacheError,
    VideoInspectionError,
    derive_candidate_fingerprints,
    discover_videos,
    ffmpeg_version,
    inspect_video_paths,
    resolve_executable,
    writable_cache_path,
)
from pymo.logging_config import emit as print
from pymo.organize import Classifier
from pymo.progress import StageTimer, format_bytes


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pymo cache",
        description=(
            "Populate reusable derived evidence without duplicate planning or media "
            "mutation."
        ),
    )
    parser.add_argument("action", choices=("warm",))
    parser.add_argument("media", choices=("videos",))
    parser.add_argument(
        "folder", type=Path, help="organized media-collection root containing vids"
    )
    parser.add_argument(
        "--cache",
        type=Path,
        help=(
            "write this cache file instead of the collection-local default; its "
            "parent directory must already exist"
        ),
    )
    parser.add_argument("--ffmpeg", type=Path, help="explicit ffmpeg executable path")
    parser.add_argument("--ffprobe", type=Path, help="explicit ffprobe executable path")
    parser.add_argument(
        "--decode-timeout",
        type=int,
        help=(
            "maximum seconds allowed for each FFmpeg decode "
            "(default: configured video_duplicates.decode_timeout_seconds)"
        ),
    )
    parser.add_argument(
        "--show-files",
        action="store_true",
        help="show collection-relative paths for media that could not be cached",
    )
    add_config_argument(parser)
    add_show_ignored_argument(parser)
    return parser.parse_args(argv)


def _relative_failure(root: Path, path: Path, reason: str) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = Path("unavailable")
    return f"  {relative}: {reason}"


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        print("Not a directory: supplied collection path", file=sys.stderr)
        return 2
    if args.decode_timeout is not None and args.decode_timeout <= 0:
        print("--decode-timeout must be a positive number", file=sys.stderr)
        return 2

    try:
        config = load_config(root, args.config)
        database = writable_cache_path(root, args.cache)
        location = "explicit" if args.cache is not None else "collection-local"
    except (ConfigError, VideoInspectionError) as error:
        print(f"Cannot prepare cache warming: {error}", file=sys.stderr)
        return 2

    problems = layout_problems(root, config, "video")
    if problems:
        print("Collection is not ready for video cache warming:", file=sys.stderr)
        print(f"  {len(problems)} layout problem(s).", file=sys.stderr)
        print(
            "Run pymo organize COLLECTION first so videos are directly in vids.",
            file=sys.stderr,
        )
        return 2

    vids = duplicate_layout(root, "video").source
    classifier = Classifier(config.classification)
    timer = StageTimer(print)
    try:
        with timer.measure("discovery"):
            paths, ignored = discover_videos(vids, root, classifier, config)
    except DiscoveryError:
        print("Video discovery stopped safely.", file=sys.stderr)
        return 1

    print(f"Preparing exact-video evidence for {len(paths)} video(s).")
    print(f"Cache location: {location}.")
    for message in ignored_messages(ignored, root, args.show_ignored):
        print(message)
    if not paths:
        print("No video content required cache warming.")
        print("Cache writes: 0; media writes: 0; action-log writes: 0.")
        return 0

    try:
        ffmpeg = resolve_executable(args.ffmpeg, "ffmpeg")
        ffprobe = resolve_executable(args.ffprobe, "ffprobe")
        ffmpeg_release = ffmpeg_version(ffmpeg)
    except VideoInspectionError:
        print("Native video tools are unavailable.", file=sys.stderr)
        return 2
    decode_timeout = (
        args.decode_timeout
        if args.decode_timeout is not None
        else config.video_duplicates.decode_timeout_seconds
    )

    try:
        with timer.measure("probing"):
            records, scanned_bytes, skipped = inspect_video_paths(
                root,
                paths,
                ffprobe,
                config.performance.progress_interval_seconds,
                database,
                config.performance.cache_publication_batch_size,
            )
    except VideoCacheError:
        print("Derived cache cannot be used safely.", file=sys.stderr)
        return 1
    try:
        with timer.measure("fingerprinting"):
            derived, fingerprint_skips = derive_candidate_fingerprints(
                root,
                records,
                database,
                ffmpeg,
                ffmpeg_release,
                decode_timeout,
                config.performance.progress_interval_seconds,
                False,
                True,
                fingerprint_label="video content",
            )
    except VideoCacheError:
        print("Derived cache cannot be used safely.", file=sys.stderr)
        return 1
    skipped.extend(fingerprint_skips)
    unique_hashes = {record.byte_sha256 for record in records}
    represented = sum(file_hash in derived for file_hash in unique_hashes)

    print("\nVideo cache warm summary:")
    print(f"  Discovered videos: {len(paths)}")
    print(f"  Safely inspected videos: {len(records)}")
    print(f"  Inspected storage: {format_bytes(scanned_bytes)}")
    print(f"  Unique byte streams represented: {represented}/{len(unique_hashes)}")
    print(f"  Uncached or unreadable files: {len(skipped)}")
    print("  Media writes: 0; action-log writes: 0.")
    if args.show_files and skipped:
        print("\nFiles not represented:")
        for path, reason in sorted(skipped, key=lambda item: str(item[0]).casefold()):
            print(_relative_failure(root, path, reason))
    if skipped:
        print(
            "Cache warming completed with incomplete media coverage.", file=sys.stderr
        )
        return 1
    print("Cache warming completed with complete discovered-video coverage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
