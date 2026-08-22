"""Unified ``pymo`` command-line entry point."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from pymo import __version__
from pymo import organize, rename
from pymo.duplicates import images, videos
from pymo.logging_config import configure_logging


def _commands():
    """Build the small dispatch table without mutable module-level state."""
    return {
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
    parser.add_argument(
        "--config",
        type=Path,
        help="use an alternate TOML configuration for this command",
    )
    parser.add_argument("command", choices=tuple(_commands()))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(
        verbose=args.verbose,
        quiet=args.quiet,
        log_file=args.log_file,
    )
    logging.getLogger("pymo").debug("Dispatching pymo command: %s", args.command)
    commands = _commands()
    command_arguments = list(args.arguments)
    if args.config is not None:
        command_arguments[0:0] = ["--config", str(args.config)]
    return commands[args.command](command_arguments)
