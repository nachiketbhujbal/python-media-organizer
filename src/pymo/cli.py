"""Unified ``pymo`` command-line entry point."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from pymo import __version__, cache_cli, organize, rename, scan, validate
from pymo.config import add_show_ignored_argument
from pymo.duplicates import images, videos
from pymo.logging_config import configure_logging
from pymo.progress import format_duration


def _commands() -> dict[str, Callable[[Sequence[str] | None], int]]:
    """Build the small dispatch table without mutable module-level state."""
    return {
        "scan": scan.main,
        "cache": cache_cli.main,
        "validate": validate.main,
        "organize": organize.main,
        "rename": rename.main,
        "find-image-duplicates": images.main,
        "find-video-duplicates": videos.main,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pymo",
        description="Safe, local-first tools for organizing media collections.",
    )
    parser.add_argument("--version", action="version", version=f"pymo {__version__}")
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--verbose", action="store_true", help="show diagnostic logging"
    )
    output.add_argument(
        "--quiet", action="store_true", help="show only warnings and errors"
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="also write detailed logs to this explicit local path",
    )
    timestamp_output = parser.add_mutually_exclusive_group()
    timestamp_output.add_argument(
        "--timestamps",
        dest="timestamps",
        action="store_true",
        help=(
            "prefix each human-readable console line with an ISO timestamp " "(default)"
        ),
    )
    timestamp_output.add_argument(
        "--no-timestamps",
        dest="timestamps",
        action="store_false",
        help="omit timestamps from human-readable console output",
    )
    parser.set_defaults(timestamps=True)
    parser.add_argument(
        "--config",
        type=Path,
        help="use an alternate TOML configuration for this command",
    )
    add_show_ignored_argument(parser)
    parser.add_argument("command", choices=tuple(_commands()))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    started_at = time.monotonic()
    structured_json = (
        args.command in {"scan", "validate", "cache"} and "--json" in args.arguments
    )
    configure_logging(
        verbose=args.verbose and not structured_json,
        quiet=args.quiet and not structured_json,
        log_file=args.log_file,
        timestamps=args.timestamps and not structured_json,
    )
    if not structured_json:
        logging.getLogger("pymo").debug("Dispatching pymo command: %s", args.command)
    commands = _commands()
    command_arguments = list(args.arguments)
    cache_action = (
        args.arguments[0] if args.command == "cache" and args.arguments else None
    )
    if (
        args.command == "cache"
        and cache_action == "status"
        and (args.config is not None or args.show_ignored)
    ):
        parser.error("--config and --show-ignored are not used by cache status")
    forwarded_options: list[str] = []
    if args.show_ignored:
        forwarded_options.append("--show-ignored")
    if args.config is not None:
        forwarded_options.extend(("--config", str(args.config)))
    insertion = 1 if args.command == "cache" and cache_action == "warm" else 0
    command_arguments[insertion:insertion] = forwarded_options
    return_code: int | None = None
    interrupted = False
    parser_exit = False
    try:
        return_code = commands[args.command](command_arguments)
        return return_code
    except SystemExit:
        parser_exit = True
        raise
    except KeyboardInterrupt:
        interrupted = True
        return_code = 130
        if not structured_json:
            logging.getLogger("pymo").error("Interrupted by user.")
        return return_code
    finally:
        if not structured_json and not parser_exit:
            outcome = (
                "Interrupted"
                if interrupted
                else "Completed" if return_code is not None else "Stopped"
            )
            logging.getLogger("pymo").info(
                "%s %s in %s%s.",
                outcome,
                args.command,
                format_duration(time.monotonic() - started_at),
                f" (exit {return_code})" if return_code is not None else "",
            )
