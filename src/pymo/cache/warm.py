"""Explicitly populate reusable image and video cache evidence."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import __version__ as PILLOW_VERSION

from pymo.cache.paths import CachePathError, writable_cache_path
from pymo.classification import Classifier
from pymo.config import (
    ConfigError,
    PymoConfig,
    add_config_argument,
    add_show_ignored_argument,
    ignored_messages,
    load_config,
)
from pymo.discovery import DiscoveryError
from pymo.duplicates.common import duplicate_layout, layout_problems
from pymo.duplicates.images import (
    ImageAnalysisCacheError,
    discover_images,
    inspect_image_paths,
)
from pymo.duplicates.videos import (
    VideoCacheError,
    VideoInspectionError,
    derive_candidate_fingerprints,
    discover_videos,
    ffmpeg_version,
    ffprobe_version,
    inspect_video_paths,
    resolve_executable,
)
from pymo.logging_config import emit as print
from pymo.progress import StageTimer, format_bytes


@dataclass(frozen=True)
class WarmResult:
    kind: str
    discovered: int
    inspected: int
    inspected_bytes: int
    represented_hashes: int
    unique_hashes: int
    skipped: tuple[tuple[Path, str], ...]


@dataclass(frozen=True)
class VideoTools:
    ffmpeg: str
    ffprobe: str
    ffmpeg_release: str
    ffprobe_release: str
    decode_timeout: int


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pymo cache",
        description=(
            "Populate reusable derived evidence without duplicate planning or media "
            "mutation."
        ),
    )
    parser.add_argument("action", choices=("warm",))
    parser.add_argument("media", choices=("images", "videos", "all"))
    parser.add_argument(
        "folder",
        type=Path,
        help="organized media-collection root containing selected media folders",
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


MediaKind = Literal["picture", "video"]


def _selected_kinds(media: str) -> tuple[MediaKind, ...]:
    if media == "all":
        return ("picture", "video")
    return ("picture",) if media == "images" else ("video",)


def _layout_ready(
    root: Path,
    config: PymoConfig,
    kinds: tuple[MediaKind, ...],
    *,
    operation: str = "warming",
) -> bool:
    counts = {kind: len(layout_problems(root, config, kind)) for kind in kinds}
    if not any(counts.values()):
        return True
    print(f"Collection is not ready for selected cache {operation}:", file=sys.stderr)
    for kind, count in counts.items():
        if count:
            label = "image" if kind == "picture" else "video"
            print(f"  {label}: {count} layout problem(s).", file=sys.stderr)
    print(
        "Run pymo organize COLLECTION first so media is directly in pics and vids.",
        file=sys.stderr,
    )
    return False


def _discover_selected(
    root: Path,
    config: PymoConfig,
    kinds: tuple[MediaKind, ...],
    timer: StageTimer,
) -> tuple[dict[str, list[Path]], list[Path]]:
    discovered: dict[str, list[Path]] = {}
    ignored: list[Path] = []
    if "picture" in kinds:
        with timer.measure("image discovery"):
            paths, image_ignored = discover_images(
                duplicate_layout(root, "picture").source, root, config
            )
        discovered["picture"] = paths
        ignored.extend(image_ignored)
    if "video" in kinds:
        classifier = Classifier(config.classification)
        with timer.measure("video discovery"):
            paths, video_ignored = discover_videos(
                duplicate_layout(root, "video").source,
                root,
                classifier,
                config,
            )
        discovered["video"] = paths
        ignored.extend(video_ignored)
    return discovered, ignored


def _warm_images(
    root: Path,
    paths: list[Path],
    database: Path,
    config: PymoConfig,
    timer: StageTimer,
    *,
    reuse_evidence: bool = True,
) -> WarmResult:
    with timer.measure("image fingerprinting"):
        records, inspected_bytes, skipped = inspect_image_paths(
            root,
            paths,
            config.performance.progress_interval_seconds,
            database,
            config.performance.cache_publication_batch_size,
            f"Pillow {PILLOW_VERSION}",
            reuse_evidence=reuse_evidence,
        )
    hashes = {record.byte_sha256 for record in records}
    return WarmResult(
        kind="Image",
        discovered=len(paths),
        inspected=len(records),
        inspected_bytes=inspected_bytes,
        represented_hashes=len(hashes),
        unique_hashes=len(hashes),
        skipped=tuple(skipped),
    )


def _warm_videos(
    root: Path,
    paths: list[Path],
    database: Path,
    config: PymoConfig,
    tools: VideoTools,
    timer: StageTimer,
    *,
    reuse_evidence: bool = True,
) -> WarmResult:
    with timer.measure("video probing"):
        records, inspected_bytes, skipped = inspect_video_paths(
            root,
            paths,
            tools.ffprobe,
            config.performance.progress_interval_seconds,
            database,
            config.performance.cache_publication_batch_size,
            tools.ffprobe_release,
            reuse_evidence=reuse_evidence,
        )
    with timer.measure("video fingerprinting"):
        derived, fingerprint_skips = derive_candidate_fingerprints(
            root,
            records,
            database,
            tools.ffmpeg,
            tools.ffmpeg_release,
            tools.decode_timeout,
            config.performance.progress_interval_seconds,
            False,
            True,
            fingerprint_label="video content",
            reuse_evidence=reuse_evidence,
        )
    skipped.extend(fingerprint_skips)
    hashes = {record.byte_sha256 for record in records}
    return WarmResult(
        kind="Video",
        discovered=len(paths),
        inspected=len(records),
        inspected_bytes=inspected_bytes,
        represented_hashes=sum(file_hash in derived for file_hash in hashes),
        unique_hashes=len(hashes),
        skipped=tuple(skipped),
    )


def _prepare_video_tools(args: argparse.Namespace, config: PymoConfig) -> VideoTools:
    ffmpeg = resolve_executable(args.ffmpeg, "ffmpeg")
    ffprobe = resolve_executable(args.ffprobe, "ffprobe")
    return VideoTools(
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        ffmpeg_release=ffmpeg_version(ffmpeg),
        ffprobe_release=ffprobe_version(ffprobe),
        decode_timeout=(
            args.decode_timeout
            if args.decode_timeout is not None
            else config.video_duplicates.decode_timeout_seconds
        ),
    )


def _print_result(
    root: Path,
    result: WarmResult,
    show_files: bool,
    *,
    operation: str = "warm",
) -> None:
    print(f"\n{result.kind} cache {operation} summary:")
    print(f"  Discovered files: {result.discovered}")
    print(f"  Safely inspected files: {result.inspected}")
    print(f"  Inspected storage: {format_bytes(result.inspected_bytes)}")
    print(
        "  Unique byte streams represented: "
        f"{result.represented_hashes}/{result.unique_hashes}"
    )
    print(f"  Uncached or unreadable files: {len(result.skipped)}")
    if show_files and result.skipped:
        print(f"\n{result.kind} files not represented:")
        for path, reason in sorted(
            result.skipped, key=lambda item: str(item[0]).casefold()
        ):
            print(_relative_failure(root, path, reason))


def run_media_population(
    args: argparse.Namespace,
    *,
    reuse_evidence: bool,
    operation: str,
) -> int:
    """Populate selected media evidence with warm or forced-refresh semantics."""

    operation_noun = "warming" if operation == "warm" else "refresh"
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        print("Not a directory: supplied collection path", file=sys.stderr)
        return 2
    if args.decode_timeout is not None and args.decode_timeout <= 0:
        print("--decode-timeout must be a positive number", file=sys.stderr)
        return 2
    if args.media == "images" and any(
        value is not None for value in (args.ffmpeg, args.ffprobe, args.decode_timeout)
    ):
        print(
            f"FFmpeg options are not used by image cache {operation_noun}",
            file=sys.stderr,
        )
        return 2

    try:
        config = load_config(root, args.config)
        database = writable_cache_path(root, args.cache)
        location = "explicit" if args.cache is not None else "collection-local"
    except (CachePathError, ConfigError) as error:
        print(f"Cannot prepare cache {operation_noun}: {error}", file=sys.stderr)
        return 2

    kinds = _selected_kinds(args.media)
    if not _layout_ready(root, config, kinds, operation=operation_noun):
        return 2

    timer = StageTimer(print)
    try:
        discovered, ignored = _discover_selected(root, config, kinds, timer)
    except DiscoveryError:
        print("Media discovery stopped safely.", file=sys.stderr)
        return 1

    total = sum(len(paths) for paths in discovered.values())
    action = "Refreshing" if operation == "refresh" else "Preparing reusable"
    print(f"{action} evidence for {total} media file(s).")
    print(f"Cache location: {location}.")
    for message in ignored_messages(ignored, root, args.show_ignored):
        print(message)
    if total == 0:
        print(f"No selected media content required cache {operation_noun}.")
        print("Cache writes: 0; media writes: 0; action-log writes: 0.")
        return 0

    results: list[WarmResult] = []
    try:
        video_paths = discovered.get("video", [])
        video_tools = _prepare_video_tools(args, config) if video_paths else None
        image_paths = discovered.get("picture", [])
        if image_paths:
            results.append(
                _warm_images(
                    root,
                    image_paths,
                    database,
                    config,
                    timer,
                    reuse_evidence=reuse_evidence,
                )
            )
        if video_paths:
            assert video_tools is not None
            results.append(
                _warm_videos(
                    root,
                    video_paths,
                    database,
                    config,
                    video_tools,
                    timer,
                    reuse_evidence=reuse_evidence,
                )
            )
    except ImageAnalysisCacheError:
        print("Derived image cache cannot be used safely.", file=sys.stderr)
        return 1
    except VideoCacheError:
        print("Derived video cache cannot be used safely.", file=sys.stderr)
        return 1
    except VideoInspectionError:
        print("Native video tools are unavailable.", file=sys.stderr)
        return 2

    for result in results:
        _print_result(root, result, args.show_files, operation=operation)
    print("  Media writes: 0; action-log writes: 0.")
    skipped = sum(len(result.skipped) for result in results)
    if skipped:
        print(
            f"Cache {operation_noun} completed with incomplete media coverage.",
            file=sys.stderr,
        )
        return 1
    print(f"Cache {operation_noun} completed with complete selected-media coverage.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_media_population(parse_args(argv), reuse_evidence=True, operation="warm")


if __name__ == "__main__":
    raise SystemExit(main())
