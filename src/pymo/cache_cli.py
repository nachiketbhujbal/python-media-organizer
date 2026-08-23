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
    parser.add_argument("action", choices=("status", "warm"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    parsed = build_parser().parse_args(arguments)
    if parsed.action == "status":
        return cache_status.main([parsed.action, *parsed.arguments])
    return cache_warm.main([parsed.action, *parsed.arguments])
