"""Explicitly recompute selected disposable cache evidence."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pymo import validate
from pymo.cache.warm import run_media_population
from pymo.config import add_config_argument, add_show_ignored_argument
from pymo.logging_config import emit as print


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pymo cache",
        description=(
            "Recompute selected derived evidence without deleting unrelated cache "
            "records or changing media."
        ),
    )
    parser.add_argument("action", choices=("refresh",))
    parser.add_argument(
        "target",
        choices=("images", "videos", "validation-standard", "validation-full"),
    )
    parser.add_argument("folder", type=Path, help="media-collection root")
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
        "--workers",
        type=int,
        help="bounded validation workers (validation targets only)",
    )
    parser.add_argument(
        "--show-files",
        action="store_true",
        help="show collection-relative paths for evidence that could not be refreshed",
    )
    add_config_argument(parser)
    add_show_ignored_argument(parser)
    return parser.parse_args(argv)


def _validation_arguments(args: argparse.Namespace) -> list[str]:
    arguments = [str(args.folder)]
    if args.target == "validation-full":
        arguments.append("--full")
    if args.cache is not None:
        arguments.extend(("--cache", str(args.cache)))
    if args.workers is not None:
        arguments.extend(("--workers", str(args.workers)))
    if args.show_files:
        arguments.append("--show-files")
    if args.config is not None:
        arguments.extend(("--config", str(args.config)))
    if args.show_ignored:
        arguments.append("--show-ignored")
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    validation_target = args.target.startswith("validation-")
    video_options = (args.ffmpeg, args.ffprobe, args.decode_timeout)
    if validation_target:
        if any(value is not None for value in video_options):
            print(
                "FFmpeg overrides are not used by validation cache refresh",
                file=sys.stderr,
            )
            return 2
        return validate.main(_validation_arguments(args))
    if args.workers is not None:
        print("--workers is used only by validation cache refresh", file=sys.stderr)
        return 2

    args.media = args.target
    return run_media_population(
        args,
        reuse_evidence=False,
        operation="refresh",
    )


if __name__ == "__main__":
    raise SystemExit(main())
