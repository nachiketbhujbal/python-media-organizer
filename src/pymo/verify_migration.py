"""Verify directional exact-byte coverage between two media collections."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pymo.config import (
    ConfigError,
    add_config_argument,
    add_show_ignored_argument,
    load_config,
)
from pymo.logging_config import emit as print
from pymo.migration.coverage import compare_byte_inventories
from pymo.migration.images import compare_image_content
from pymo.migration.inventory import discover_tree, hash_tree
from pymo.migration.report import build_report, print_report
from pymo.progress import StageTimer


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prove directional exact-byte coverage without relying on names or layout."
        )
    )
    parser.add_argument("source", type=Path, help="baseline media-collection root")
    parser.add_argument("destination", type=Path, help="migrated media-collection root")
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit one machine-readable JSON report instead of terminal text",
    )
    parser.add_argument(
        "--show-files",
        action="store_true",
        help="include collection-relative missing and problem paths",
    )
    add_config_argument(parser)
    add_show_ignored_argument(parser)
    return parser.parse_args(argv)


def _roots_are_disjoint(source: Path, destination: Path) -> bool:
    return (
        source != destination
        and source not in destination.parents
        and destination not in source.parents
    )


def _discard_message(_message: str) -> None:
    pass


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    source = args.source.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if not source.is_dir():
        print("Source is not a readable directory.", file=sys.stderr)
        return 2
    if not destination.is_dir():
        print("Destination is not a readable directory.", file=sys.stderr)
        return 2
    if not _roots_are_disjoint(source, destination):
        print(
            "Source and destination must be distinct, non-nested directories.",
            file=sys.stderr,
        )
        return 2
    try:
        source_config = load_config(source, args.config)
        destination_config = load_config(destination, args.config)
    except ConfigError:
        print(
            "Source or destination configuration cannot be used safely.",
            file=sys.stderr,
        )
        return 2

    timer = StageTimer(_discard_message if args.json else print)
    try:
        if not args.json:
            print("Discovering source namespace...")
        with timer.measure("source discovery"):
            source_discovery = discover_tree(source, source_config)
        if not args.json:
            print("Discovering destination namespace...")
        with timer.measure("destination discovery"):
            destination_discovery = discover_tree(destination, destination_config)

        if not args.json:
            print(
                f"Hashing {len(source_discovery.entries)} source file(s) from "
                "fresh reads..."
            )
        with timer.measure("source hashing"):
            source_inventory = hash_tree(
                source_discovery,
                source_config.performance.progress_interval_seconds,
                show_progress=not args.json,
            )
        if not args.json:
            print(
                f"Hashing {len(destination_discovery.entries)} destination file(s) "
                "from fresh reads..."
            )
        with timer.measure("destination hashing"):
            destination_inventory = hash_tree(
                destination_discovery,
                destination_config.performance.progress_interval_seconds,
                show_progress=not args.json,
            )
    except OSError:
        print(
            "Migration verification could not read a collection root safely.",
            file=sys.stderr,
        )
        return 1

    coverage = compare_byte_inventories(source_inventory, destination_inventory)
    image_extensions = (
        source_config.image_duplicates.extensions
        | destination_config.image_duplicates.extensions
    )
    if not args.json:
        print("Inspecting exact displayed-image coverage for byte-missing content...")
    with timer.measure("image-content comparison"):
        image_content = compare_image_content(
            source_inventory,
            destination_inventory,
            image_extensions,
            min(
                source_config.performance.progress_interval_seconds,
                destination_config.performance.progress_interval_seconds,
            ),
            show_progress=not args.json,
        )
    report = build_report(
        source_inventory,
        destination_inventory,
        coverage,
        image_content,
        show_files=args.show_files,
        show_ignored=args.show_ignored,
    )
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print_report(report)
    return 0 if coverage.verdict == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
