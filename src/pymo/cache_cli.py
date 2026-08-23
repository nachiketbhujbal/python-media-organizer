"""Command dispatcher for derived-cache operations."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from pymo import cache_status, cache_warm


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pymo cache",
        description="Inspect or deliberately populate disposable derived cache state.",
    )
    subcommands = parser.add_subparsers(dest="action", required=True)
    for name, help_text in (
        ("status", "inspect cache health without writing state"),
        ("warm", "deliberately populate reusable cache evidence"),
    ):
        subcommand = subcommands.add_parser(name, add_help=False, help=help_text)
        subcommand.add_argument(
            "arguments", nargs=argparse.REMAINDER, help=argparse.SUPPRESS
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    parsed = build_parser().parse_args(arguments)
    if parsed.action == "status":
        return cache_status.main([parsed.action, *parsed.arguments])
    return cache_warm.main([parsed.action, *parsed.arguments])
