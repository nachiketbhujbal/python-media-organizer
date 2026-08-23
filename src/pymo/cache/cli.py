"""Command dispatcher for derived-cache operations."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from pymo.cache import status, warm


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
        subcommands.add_parser(name, add_help=False, help=help_text)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if not arguments or arguments[0] in {"-h", "--help"}:
        build_parser().parse_args(arguments)
        raise AssertionError("argument parsing should exit")
    if arguments[0] == "status":
        return status.main(arguments)
    if arguments[0] == "warm":
        return warm.main(arguments)
    build_parser().error(
        f"argument action: invalid choice: {arguments[0]!r} "
        "(choose from 'status', 'warm')"
    )
