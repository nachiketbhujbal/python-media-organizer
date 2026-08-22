"""Read-only collection inventory, readiness, and duplicate-potential reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pymo.action_log import is_action_log_path
from pymo.collection import CollectionLayout
from pymo.config import (
    ConfigError,
    PymoConfig,
    add_config_argument,
    add_show_ignored_argument,
    load_config,
)
from pymo.logging_config import emit as print
from pymo.organize import Classifier, desired_directory
from pymo.rename import canonical_match, collection_slug


# This identifies the public machine-readable report contract.
SCAN_REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RawEntry:
    path: Path
    size: int
    in_review: bool


@dataclass(frozen=True)
class ScanEntry:
    path: Path
    size: int
    in_review: bool
    kind: str
    mime_type: str


@dataclass(frozen=True)
class WalkResult:
    entries: tuple[RawEntry, ...]
    directory_count: int
    ignored: tuple[Path, ...]
    symlink_count: int
    unreadable_count: int


def format_size(size: int) -> str:
    value = float(size)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def _collect_entries(root: Path, config: PymoConfig) -> WalkResult:
    layout = CollectionLayout(root)
    entries: list[RawEntry] = []
    ignored: list[Path] = []
    directory_count = 0
    symlink_count = 0
    unreadable_count = 0

    for current, directory_names, file_names in os.walk(root, topdown=True):
        current_path = Path(current)
        directory_names.sort(key=str.casefold)
        file_names.sort(key=str.casefold)
        retained_directories: list[str] = []
        for name in directory_names:
            path = current_path / name
            if path.is_symlink():
                symlink_count += 1
            elif config.ignores_directory(path, root):
                ignored.append(path)
            else:
                retained_directories.append(name)
                directory_count += 1
        directory_names[:] = retained_directories

        for name in file_names:
            path = current_path / name
            if path.is_symlink():
                symlink_count += 1
                continue
            if config.ignores_file(path, root):
                ignored.append(path)
                continue
            if is_action_log_path(root, path):
                continue
            try:
                if not path.is_file():
                    unreadable_count += 1
                    continue
                size = path.stat().st_size
            except OSError:
                unreadable_count += 1
                continue
            entries.append(
                RawEntry(
                    path=path.absolute(),
                    size=size,
                    in_review=layout.is_in_duplicates(path),
                )
            )

    return WalkResult(
        entries=tuple(entries),
        directory_count=directory_count,
        ignored=tuple(sorted(ignored, key=lambda path: str(path).casefold())),
        symlink_count=symlink_count,
        unreadable_count=unreadable_count,
    )


def _classify_entry(raw: RawEntry, classifier: Classifier) -> ScanEntry:
    kind, mime_type = classifier.classify(raw.path)
    if mime_type.startswith("audio/"):
        kind = "audio"
    elif kind == "other" and mime_type == "unknown":
        kind = "unknown"
    return ScanEntry(
        path=raw.path,
        size=raw.size,
        in_review=raw.in_review,
        kind=kind,
        mime_type=mime_type,
    )


def _classify_entries(
    entries: tuple[RawEntry, ...],
    classifier: Classifier,
    workers: int,
    show_progress: bool,
) -> tuple[ScanEntry, ...]:
    results: list[ScanEntry] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        classified = executor.map(
            lambda entry: _classify_entry(entry, classifier), entries
        )
        for number, entry in enumerate(classified, start=1):
            results.append(entry)
            if show_progress and number % 200 == 0:
                print(f"  classified {number}/{len(entries)}")
    return tuple(results)


def _folder_status(path: Path) -> str:
    if path.is_symlink():
        return "unsafe symbolic link"
    if not path.exists():
        return "missing"
    if not path.is_dir():
        return "blocked by a file"
    return "ready"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _duplicate_statistics(
    entries: tuple[ScanEntry, ...], checksums: bool, show_progress: bool
) -> dict[str, Any]:
    by_kind_size: dict[tuple[str, int], list[ScanEntry]] = defaultdict(list)
    for entry in entries:
        if not entry.in_review and entry.kind in {"picture", "video"}:
            by_kind_size[(entry.kind, entry.size)].append(entry)
    candidates = {
        key: values for key, values in by_kind_size.items() if len(values) > 1
    }

    by_kind: dict[str, dict[str, int]] = {}
    for kind in ("picture", "video"):
        groups = [
            values
            for (candidate_kind, _), values in candidates.items()
            if candidate_kind == kind
        ]
        by_kind[kind] = {
            "same_size_groups": len(groups),
            "candidate_files": sum(len(group) for group in groups),
            "candidate_bytes": sum(
                entry.size for group in groups for entry in group
            ),
            "potential_reclaimable_bytes_upper_bound": sum(
                group[0].size * (len(group) - 1) for group in groups
            ),
        }

    result: dict[str, Any] = {
        "method": "same-size candidates",
        "pictures": by_kind["picture"],
        "videos": by_kind["video"],
        "exact_bytes": None,
    }
    if not checksums:
        return result

    exact_groups: dict[str, list[ScanEntry]] = defaultdict(list)
    hashed_files = 0
    hashed_bytes = 0
    unreadable = 0
    for values in candidates.values():
        for entry in values:
            try:
                digest = _sha256(entry.path)
            except OSError:
                unreadable += 1
                continue
            exact_groups[f"{entry.kind}:{digest}"].append(entry)
            hashed_files += 1
            hashed_bytes += entry.size
            if show_progress and hashed_files % 100 == 0:
                print(f"  checksummed {hashed_files} candidate file(s)")
    matches = [group for group in exact_groups.values() if len(group) > 1]
    result["exact_bytes"] = {
        "groups": len(matches),
        "extra_copies": sum(len(group) - 1 for group in matches),
        "reclaimable_bytes": sum(
            group[0].size * (len(group) - 1) for group in matches
        ),
        "hashed_files": hashed_files,
        "hashed_bytes": hashed_bytes,
        "unreadable_files": unreadable,
    }
    return result


def _counter_report(
    entries: tuple[ScanEntry, ...], attribute: str
) -> dict[str, dict[str, int]]:
    counts: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    for entry in entries:
        value = str(getattr(entry, attribute))
        counts[value] += 1
        sizes[value] += entry.size
    return {
        value: {"files": counts[value], "bytes": sizes[value]}
        for value in sorted(counts, key=str.casefold)
    }


def _safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def build_report(
    root: Path,
    config: PymoConfig,
    workers: int,
    checksums: bool,
    show_ignored: bool,
    show_progress: bool,
) -> dict[str, Any]:
    layout = CollectionLayout(root)
    walk = _collect_entries(root, config)
    classifier = Classifier(config.classification)
    entries = _classify_entries(walk.entries, classifier, workers, show_progress)

    kind_counts: Counter[str] = Counter()
    kind_sizes: Counter[str] = Counter()
    review_counts: Counter[str] = Counter()
    review_sizes: Counter[str] = Counter()
    extension_counts: Counter[str] = Counter()
    extension_sizes: Counter[str] = Counter()
    organized = 0
    proposed_moves = 0
    proposed_move_bytes = 0
    canonical_names = 0
    rename_candidates = 0
    collection = collection_slug(root.name)

    for entry in entries:
        kind_counts[entry.kind] += 1
        kind_sizes[entry.kind] += entry.size
        extension = entry.path.suffix.casefold() or "(none)"
        extension_counts[extension] += 1
        extension_sizes[extension] += entry.size
        if entry.in_review:
            review_kind = (
                "pictures"
                if entry.path.is_relative_to(layout.duplicate_pics)
                else "videos"
                if entry.path.is_relative_to(layout.duplicate_vids)
                else "other"
            )
            review_counts[review_kind] += 1
            review_sizes[review_kind] += entry.size
            continue

        destination = desired_directory(
            entry.kind, root, layout.pics, layout.vids
        )
        if entry.path.parent == destination:
            organized += 1
        else:
            proposed_moves += 1
            proposed_move_bytes += entry.size
        if entry.kind in {"picture", "video"}:
            output_kind = "image" if entry.kind == "picture" else "video"
            existing = canonical_match(entry.path.stem, collection)
            if existing and existing.group(1).casefold() == output_kind:
                canonical_names += 1
            else:
                rename_candidates += 1

    kinds = {
        kind: {"files": kind_counts[kind], "bytes": kind_sizes[kind]}
        for kind in ("picture", "video", "audio", "other", "unknown")
    }
    extensions = {
        extension: {
            "files": extension_counts[extension],
            "bytes": extension_sizes[extension],
        }
        for extension in sorted(extension_counts, key=str.casefold)
    }
    review = {
        kind: {"files": review_counts[kind], "bytes": review_sizes[kind]}
        for kind in ("pictures", "videos", "other")
    }
    layout_report = {
        "pics": _folder_status(layout.pics),
        "vids": _folder_status(layout.vids),
        "dups": _folder_status(layout.dups),
        "correctly_placed_files": organized,
        "proposed_organizer_moves": proposed_moves,
        "proposed_organizer_move_bytes": proposed_move_bytes,
        "canonical_media_names": canonical_names,
        "proposed_renames": rename_candidates,
    }
    duplicate_report = _duplicate_statistics(entries, checksums, show_progress)
    source_videos = [
        entry for entry in entries if entry.kind == "video" and not entry.in_review
    ]
    recommendations: list[str] = []
    if walk.symlink_count or walk.unreadable_count:
        recommendations.append("Review symbolic links and unreadable entries first.")
    if (
        layout_report["pics"] != "ready"
        or layout_report["vids"] != "ready"
        or proposed_moves
    ):
        recommendations.append("Run pymo organize after reviewing its dry run.")
    elif rename_candidates:
        recommendations.append("Run pymo rename after reviewing its dry run.")
    if kind_counts["picture"] - review_counts["pictures"] > 1:
        recommendations.append("Run pymo find-image-duplicates for exact pixels.")
    if kind_counts["video"] - review_counts["videos"] > 1:
        recommendations.append("Run pymo find-video-duplicates for exact playback.")
    if not recommendations:
        recommendations.append("The collection is ready; no immediate action is required.")

    ignored_paths = (
        [path.relative_to(root).as_posix() for path in walk.ignored]
        if show_ignored
        else []
    )
    warnings: list[str] = []
    if classifier.warning:
        warnings.append(classifier.warning)
    if walk.unreadable_count:
        warnings.append(
            f"{walk.unreadable_count} entry or entries could not be read safely."
        )

    return {
        "schema_version": SCAN_REPORT_SCHEMA_VERSION,
        "profile": "checksums" if checksums else "fast",
        "workers": workers,
        "inventory": {
            "files": len(entries),
            "directories": walk.directory_count,
            "bytes": sum(entry.size for entry in entries),
            "ignored_entry_points": len(walk.ignored),
            "symbolic_links": walk.symlink_count,
            "unreadable_entries": walk.unreadable_count,
            "kinds": kinds,
            "extensions": extensions,
            "mime_types": _counter_report(entries, "mime_type"),
        },
        "review_storage": review,
        "layout": layout_report,
        "duplicate_potential": duplicate_report,
        "estimated_work": {
            "classification_files": len(entries),
            "checksum_candidate_bytes": (
                duplicate_report["pictures"]["candidate_bytes"]
                + duplicate_report["videos"]["candidate_bytes"]
            ),
            "exact_video_source_files": len(source_videos),
            "exact_video_source_bytes_upper_bound": sum(
                entry.size for entry in source_videos
            ),
        },
        "derived_state": {
            "action_log_present": layout.action_log.is_file(),
            "video_cache_present": layout.video_cache.is_file(),
            "video_cache_bytes": (
                _safe_file_size(layout.video_cache)
                if layout.video_cache.is_file() and not layout.video_cache.is_symlink()
                else 0
            ),
            "custom_config_present": config.custom_path is not None,
        },
        "ignored_paths": ignored_paths,
        "warnings": warnings,
        "recommendations": recommendations,
    }


def _print_count_and_size(label: str, values: dict[str, int]) -> None:
    print(f"  {label}: {values['files']} file(s), {format_size(values['bytes'])}")


def _print_breakdown(
    title: str, values: dict[str, dict[str, int]], limit: int = 12
) -> None:
    print(f"\n{title}:")
    ordered = sorted(
        values.items(), key=lambda item: (-item[1]["files"], item[0].casefold())
    )
    for name, statistics in ordered[:limit]:
        _print_count_and_size(name, statistics)
    remaining = len(ordered) - limit
    if remaining > 0:
        print(f"  ... {remaining} additional type(s) in the JSON report")


def print_report(report: dict[str, Any], show_ignored: bool) -> None:
    inventory = report["inventory"]
    print("Collection scan")
    print(f"Profile: {report['profile']} ({report['workers']} classification worker(s))")
    print("\nInventory:")
    print(f"  Files: {inventory['files']}")
    print(f"  Directories: {inventory['directories']}")
    print(f"  Storage: {format_size(inventory['bytes'])}")
    kind_labels = {
        "picture": "Pictures",
        "video": "Videos",
        "audio": "Audio",
        "other": "Other",
        "unknown": "Unknown",
    }
    for kind, label in kind_labels.items():
        _print_count_and_size(label, inventory["kinds"][kind])
    print(f"  Symbolic links skipped: {inventory['symbolic_links']}")
    print(f"  Unreadable entries: {inventory['unreadable_entries']}")
    print(
        "  Ignored by configuration: "
        f"{inventory['ignored_entry_points']} path(s)."
    )
    if show_ignored and report["ignored_paths"]:
        print("  Ignored paths:")
        for path in report["ignored_paths"]:
            print(f"    {path}")
    _print_breakdown("Extensions", inventory["extensions"])
    _print_breakdown("Detected content types", inventory["mime_types"])

    layout = report["layout"]
    print("\nLayout and naming:")
    print(f"  pics: {layout['pics']}")
    print(f"  vids: {layout['vids']}")
    print(f"  dups: {layout['dups']}")
    print(f"  Correctly placed files: {layout['correctly_placed_files']}")
    print(
        f"  Proposed organizer moves: {layout['proposed_organizer_moves']} "
        f"file(s), {format_size(layout['proposed_organizer_move_bytes'])}"
    )
    print(f"  Canonical media names: {layout['canonical_media_names']}")
    print(f"  Proposed renames: {layout['proposed_renames']}")

    review = report["review_storage"]
    print("\nReview storage:")
    for kind in ("pictures", "videos", "other"):
        _print_count_and_size(kind.capitalize(), review[kind])

    duplicates = report["duplicate_potential"]
    print("\nDuplicate potential:")
    for kind in ("pictures", "videos"):
        values = duplicates[kind]
        print(
            f"  {kind.capitalize()}: {values['same_size_groups']} same-size group(s), "
            f"{values['candidate_files']} candidate file(s), "
            f"up to {format_size(values['potential_reclaimable_bytes_upper_bound'])} reclaimable"
        )
    exact = duplicates["exact_bytes"]
    if exact is None:
        print("  Exact-byte checks: not requested (add --checksums)")
    else:
        print(
            f"  Exact-byte matches: {exact['groups']} group(s), "
            f"{exact['extra_copies']} extra copy or copies, "
            f"{format_size(exact['reclaimable_bytes'])} reclaimable"
        )

    work = report["estimated_work"]
    print("\nEstimated expensive work:")
    print(
        "  Exact-byte mode reads up to "
        f"{format_size(work['checksum_candidate_bytes'])} from same-size candidates."
    )
    print(
        "  Exact-video analysis may inspect up to "
        f"{work['exact_video_source_files']} source video(s), "
        f"{format_size(work['exact_video_source_bytes_upper_bound'])}; "
        "ffprobe bucketing and fingerprint-cache hits reduce actual decoding."
    )

    state = report["derived_state"]
    print("\nLocal pymo state:")
    print(f"  Action log: {'present' if state['action_log_present'] else 'not created'}")
    print(
        "  Video fingerprint cache: "
        + (
            f"present, {format_size(state['video_cache_bytes'])}"
            if state["video_cache_present"]
            else "not created"
        )
    )
    if report["warnings"]:
        print("\nWarnings:")
        for warning in report["warnings"]:
            print(f"  - {warning}")
    print("\nRecommended next steps:")
    for recommendation in report["recommendations"]:
        print(f"  - {recommendation}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only collection inventory and readiness report."
    )
    parser.add_argument("folder", type=Path, help="media-collection root to scan")
    parser.add_argument(
        "--checksums",
        action="store_true",
        help="hash same-size media candidates to report exact-byte duplicates",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit one machine-readable JSON report instead of terminal text",
    )
    parser.add_argument(
        "--workers",
        type=int,
        help="bounded classification workers (default: configuration)",
    )
    add_config_argument(parser)
    add_show_ignored_argument(parser)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2
    try:
        config = load_config(root, args.config)
    except ConfigError as error:
        print(f"Cannot use configuration: {error}", file=sys.stderr)
        return 2
    workers = (
        args.workers
        if args.workers is not None
        else config.performance.scan_workers
    )
    if not 1 <= workers <= 32:
        print("--workers must be between 1 and 32", file=sys.stderr)
        return 2

    if not args.json:
        print("Scanning collection inventory...")
    report = build_report(
        root,
        config,
        workers,
        args.checksums,
        args.show_ignored,
        not args.json,
    )
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print_report(report, args.show_ignored)
    return 0
