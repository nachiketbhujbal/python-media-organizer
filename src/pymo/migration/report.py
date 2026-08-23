"""Path-private reports for directional migration byte coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pymo.logging_config import emit as print
from pymo.migration.coverage import ByteCoverage
from pymo.migration.images import ImageContentCoverage, ImageInspectionIssue
from pymo.migration.inventory import TreeInventory
from pymo.progress import format_bytes

# This value identifies the current layered migration-verification report.
MIGRATION_REPORT_SCHEMA_VERSION = 2


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return "unavailable"


def _problem_paths(inventory: TreeInventory) -> list[dict[str, str]]:
    values = [
        {"path": _relative(inventory.root, path), "category": "symbolic-link"}
        for path in inventory.symbolic_links
    ]
    values.extend(
        {"path": _relative(inventory.root, path), "category": "non-regular"}
        for path in inventory.non_regular
    )
    values.extend(
        {"path": _relative(inventory.root, issue.path), "category": issue.category}
        for issue in (*inventory.unreadable, *inventory.changed)
    )
    return sorted(values, key=lambda item: (item["path"].casefold(), item["category"]))


def _image_problem_paths(
    root: Path, issues: tuple[ImageInspectionIssue, ...]
) -> list[dict[str, str]]:
    return sorted(
        [
            {"path": _relative(root, issue.path), "category": issue.category}
            for issue in issues
        ],
        key=lambda item: (item["path"].casefold(), item["category"]),
    )


def _inventory_report(
    inventory: TreeInventory,
    *,
    show_files: bool,
    show_ignored: bool,
) -> dict[str, Any]:
    identities: dict[tuple[int, str], int] = {}
    for entry in inventory.files:
        identities[entry.identity] = identities.get(entry.identity, 0) + 1
    duplicate_copies = sum(count - 1 for count in identities.values())
    return {
        "hashed_files": len(inventory.files),
        "hashed_bytes": sum(entry.size for entry in inventory.files),
        "unique_byte_streams": len(identities),
        "unique_bytes": sum(identity[0] for identity in identities),
        "duplicate_copies": duplicate_copies,
        "duplicate_bytes": sum(
            identity[0] * (count - 1) for identity, count in identities.items()
        ),
        "directories": inventory.directories,
        "ignored_entry_points": len(inventory.ignored),
        "tool_state_entries": len(inventory.tool_state),
        "symbolic_links": len(inventory.symbolic_links),
        "non_regular_entries": len(inventory.non_regular),
        "unreadable_entries": len(inventory.unreadable),
        "changed_entries": len(inventory.changed),
        "traversal_errors": inventory.traversal_errors,
        "root_changed": inventory.root_changed,
        "evidence_complete": inventory.evidence_complete,
        "ignored_paths": (
            [_relative(inventory.root, path) for path in inventory.ignored]
            if show_ignored
            else []
        ),
        "problem_paths": _problem_paths(inventory) if show_files else [],
    }


def build_report(
    source: TreeInventory,
    destination: TreeInventory,
    coverage: ByteCoverage,
    image_content: ImageContentCoverage,
    *,
    show_files: bool,
    show_ignored: bool,
) -> dict[str, Any]:
    source_stream_percentage = (
        coverage.represented_unique_streams / coverage.source_unique_streams * 100
        if coverage.source_unique_streams
        else 100.0
    )
    source_byte_percentage = (
        coverage.represented_unique_bytes / coverage.source_unique_bytes * 100
        if coverage.source_unique_bytes
        else 100.0
    )
    return {
        "schema_version": MIGRATION_REPORT_SCHEMA_VERSION,
        "direction": "source-to-destination",
        "contract": "unique-byte-stream",
        "scope": {
            "regular_files_only": True,
            "symbolic_links_followed": False,
            "policy_ignored_content_proven": False,
            "tool_state_included": False,
            "image_candidates": "configured-exact-image-extensions",
            "image_equivalence_preserves_source_bytes": False,
            "filesystem_boundary": "stable-namespace-visible-content",
        },
        "source": _inventory_report(
            source, show_files=show_files, show_ignored=show_ignored
        ),
        "destination": _inventory_report(
            destination, show_files=show_files, show_ignored=show_ignored
        ),
        "coverage": {
            "verdict": coverage.verdict,
            "reasons": list(coverage.reasons),
            "source_unique_streams": coverage.source_unique_streams,
            "represented_unique_streams": coverage.represented_unique_streams,
            "missing_unique_streams": coverage.missing_unique_streams,
            "stream_coverage_percent": round(source_stream_percentage, 6),
            "source_unique_bytes": coverage.source_unique_bytes,
            "represented_unique_bytes": coverage.represented_unique_bytes,
            "missing_unique_bytes": coverage.missing_unique_bytes,
            "byte_coverage_percent": round(source_byte_percentage, 6),
            "source_files": coverage.source_files,
            "represented_source_files": coverage.represented_source_files,
            "missing_source_files": len(coverage.missing_source_files),
            "missing_source_paths": (
                [_relative(source.root, path) for path in coverage.missing_source_files]
                if show_files
                else []
            ),
        },
        "multiplicity": {
            "source_duplicate_copies": coverage.source_duplicate_copies,
            "source_duplicate_bytes": coverage.source_duplicate_bytes,
            "destination_duplicate_copies": coverage.destination_duplicate_copies,
            "destination_duplicate_bytes": coverage.destination_duplicate_bytes,
            "reduced_copies": coverage.reduced_copies,
            "reduced_copy_bytes": coverage.reduced_copy_bytes,
            "added_copies": coverage.added_copies,
            "added_copy_bytes": coverage.added_copy_bytes,
        },
        "image_content": {
            "verdict": image_content.verdict,
            "reasons": list(image_content.reasons),
            "algorithm": image_content.algorithm,
            "runtime": image_content.runtime,
            "eligible_source_unique_streams": (
                image_content.eligible_source_unique_streams
            ),
            "eligible_source_files": image_content.eligible_source_files,
            "represented_unique_streams": image_content.represented_unique_streams,
            "represented_source_files": len(image_content.represented_source_files),
            "missing_unique_streams": image_content.missing_unique_streams,
            "missing_source_files": len(image_content.missing_source_files),
            "missing_source_paths": (
                [
                    _relative(source.root, path)
                    for path in image_content.missing_source_files
                ]
                if show_files
                else []
            ),
            "uninspectable_source_unique_streams": (
                image_content.uninspectable_source_unique_streams
            ),
            "source_problem_paths": (
                _image_problem_paths(source.root, image_content.source_issues)
                if show_files
                else []
            ),
            "destination_candidate_unique_streams": (
                image_content.destination_candidate_unique_streams
            ),
            "destination_uninspectable_unique_streams": (
                image_content.uninspectable_destination_unique_streams
            ),
            "destination_problem_paths": (
                _image_problem_paths(destination.root, image_content.destination_issues)
                if show_files
                else []
            ),
        },
        "destination_only": {
            "unique_streams": coverage.destination_only_unique_streams,
            "files": len(coverage.destination_only_files),
            "bytes": coverage.destination_only_bytes,
            "paths": (
                [
                    _relative(destination.root, path)
                    for path in coverage.destination_only_files
                ]
                if show_files
                else []
            ),
        },
        "writes_performed": False,
    }


def _print_inventory(label: str, values: dict[str, Any]) -> None:
    print(f"\n{label} inventory:")
    print(
        f"  Hashed: {values['hashed_files']} file(s), "
        f"{format_bytes(values['hashed_bytes'])}"
    )
    print(
        f"  Unique byte streams: {values['unique_byte_streams']}, "
        f"{format_bytes(values['unique_bytes'])}"
    )
    print(
        f"  Exact duplicate copies: {values['duplicate_copies']}, "
        f"{format_bytes(values['duplicate_bytes'])}"
    )
    print(f"  Directories: {values['directories']}")
    print(f"  Ignored entry points: {values['ignored_entry_points']}")
    print(f"  Excluded pymo state entries: {values['tool_state_entries']}")
    print(f"  Symbolic links not followed: {values['symbolic_links']}")
    print(f"  Non-regular entries: {values['non_regular_entries']}")
    print(f"  Unreadable entries: {values['unreadable_entries']}")
    print(f"  Changed entries: {values['changed_entries']}")
    print(f"  Traversal errors: {values['traversal_errors']}")
    print(f"  Root changed: {'yes' if values['root_changed'] else 'no'}")
    if values["ignored_paths"]:
        print("  Ignored paths:")
        for path in values["ignored_paths"]:
            print(f"    {path}")
    if values["problem_paths"]:
        print("  Problem paths:")
        for issue in values["problem_paths"]:
            print(f"    {issue['path']}: {issue['category']}")


def print_report(report: dict[str, Any]) -> None:
    print("Directional migration verification")
    print("Contract: exact unique byte-stream coverage (source to destination)")
    print("Scope: stable namespace-visible regular files; links are not followed.")
    _print_inventory("Source", report["source"])
    _print_inventory("Destination", report["destination"])

    coverage = report["coverage"]
    print("\nCoverage:")
    print(
        f"  Unique streams represented: {coverage['represented_unique_streams']}/"
        f"{coverage['source_unique_streams']} "
        f"({coverage['stream_coverage_percent']:.1f}%)"
    )
    print(
        f"  Unique bytes represented: "
        f"{format_bytes(coverage['represented_unique_bytes'])}/"
        f"{format_bytes(coverage['source_unique_bytes'])} "
        f"({coverage['byte_coverage_percent']:.1f}%)"
    )
    print(
        f"  Missing: {coverage['missing_unique_streams']} unique stream(s), "
        f"{coverage['missing_source_files']} source file(s), "
        f"{format_bytes(coverage['missing_unique_bytes'])}"
    )
    if coverage["missing_source_paths"]:
        print("  Missing source paths:")
        for path in coverage["missing_source_paths"]:
            print(f"    {path}")

    multiplicity = report["multiplicity"]
    print("\nMultiplicity changes among represented content:")
    print(
        f"  Copies reduced: {multiplicity['reduced_copies']}, "
        f"{format_bytes(multiplicity['reduced_copy_bytes'])}"
    )
    print(
        f"  Copies added: {multiplicity['added_copies']}, "
        f"{format_bytes(multiplicity['added_copy_bytes'])}"
    )
    destination_only = report["destination_only"]
    print(
        "  Destination-only content: "
        f"{destination_only['unique_streams']} unique stream(s), "
        f"{destination_only['files']} file(s), "
        f"{format_bytes(destination_only['bytes'])}"
    )
    if destination_only["paths"]:
        print("  Destination-only paths:")
        for path in destination_only["paths"]:
            print(f"    {path}")

    images = report["image_content"]
    print("\nExact displayed-image coverage for byte-missing source content:")
    print(f"  Algorithm: {images['algorithm']} ({images['runtime']})")
    print(
        f"  Eligible source streams: {images['eligible_source_unique_streams']} "
        f"across {images['eligible_source_files']} file(s)"
    )
    print(
        f"  Represented by exact displayed pixels: "
        f"{images['represented_unique_streams']} stream(s), "
        f"{images['represented_source_files']} source file(s)"
    )
    print(
        f"  Missing displayed content: {images['missing_unique_streams']} "
        f"stream(s), {images['missing_source_files']} source file(s)"
    )
    print(
        f"  Uninspectable source streams: "
        f"{images['uninspectable_source_unique_streams']}"
    )
    print(
        f"  Uninspectable destination candidate streams: "
        f"{images['destination_uninspectable_unique_streams']}"
    )
    print(f"  Layer verdict: {images['verdict'].upper()}")
    if images["missing_source_paths"]:
        print("  Missing image-content paths:")
        for path in images["missing_source_paths"]:
            print(f"    {path}")
    for label, key in (
        ("Source image problems", "source_problem_paths"),
        ("Destination image problems", "destination_problem_paths"),
    ):
        if images[key]:
            print(f"  {label}:")
            for issue in images[key]:
                print(f"    {issue['path']}: {issue['category']}")

    verdict = coverage["verdict"]
    print("\nVerdict:")
    if verdict == "complete":
        print("  COMPLETE: every in-scope unique source byte stream is represented.")
    elif verdict == "incomplete":
        print("  INCOMPLETE: readable source byte streams are missing.")
    else:
        print("  UNPROVEN: incomplete filesystem evidence prevents a safe verdict.")
    print(
        "The image-content layer is separate evidence and does not replace the "
        "byte verdict in version 0.5.1."
    )
    print("Verification wrote no media, cache, configuration, or action history.")
