#!/usr/bin/env python3
"""Find pixel-identical pictures in an organized media collection.

The default is a dry run.  Nothing is moved unless --apply is supplied.
Filenames, file timestamps, EXIF data, and other metadata are intentionally
ignored when comparing images. Moved copies use the retained original's name,
for example ``photo_copy(1).jpg``, and live under ``dups/pics``. The supplied
path is always the collection root, which also owns the shared action log.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pymo.action_log import (
    Action,
    ActionConflict,
    ActionLog,
    ActionLogError,
    NoUndoableRun,
    ToolId,
)
from pymo.collection import CollectionLayout
from pymo.config import (
    ConfigError,
    PymoConfig,
    add_config_argument,
    add_show_ignored_argument,
    ignored_messages,
    load_config,
)
from pymo.logging_config import emit as print
from pymo.organize import Classifier
from pymo.progress import ProgressMeter

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:
    print(
        "This script needs Pillow. Install it with:\n"
        "  python3 -m pip install Pillow",
        file=sys.stderr,
    )
    raise SystemExit(2)


@dataclass(frozen=True)
class ImageRecord:
    path: Path
    pixel_hash: str
    file_size: int
    modified_ns: int


def displayed_pixel_hash(path: Path) -> str:
    """Hash the pixels as displayed, after applying EXIF orientation.

    RGBA conversion makes equivalent RGB/palette/grayscale still images
    comparable. Animated images are skipped because comparing only their first
    frame could incorrectly classify two different animations as duplicates.
    """
    with Image.open(path) as opened:
        if getattr(opened, "n_frames", 1) != 1:
            raise ValueError("animated or multi-page image")

        image = ImageOps.exif_transpose(opened)
        rgba = image.convert("RGBA")

        digest = hashlib.sha256()
        digest.update(rgba.width.to_bytes(8, "big"))
        digest.update(rgba.height.to_bytes(8, "big"))
        digest.update(rgba.tobytes())
        return digest.hexdigest()


def discover_images(
    pics: Path, root: Path, config: PymoConfig
) -> tuple[list[Path], list[Path]]:
    result: list[Path] = []
    ignored: list[Path] = []
    for path in pics.glob("*"):
        if path.is_symlink():
            continue
        if path.is_dir():
            if config.ignores_directory(path, root):
                ignored.append(path)
            continue
        if (
            path.is_file()
            and config.ignores_file(path, root)
        ):
            ignored.append(path)
            continue
        if (
            not path.is_file()
            or path.suffix.lower() not in config.image_duplicates.extensions
        ):
            continue
        result.append(path.resolve())
    return (
        sorted(result, key=lambda item: str(item).casefold()),
        sorted(ignored, key=lambda item: str(item).casefold()),
    )


def collection_layout_problems(root: Path, config: PymoConfig) -> list[str]:
    """Validate only the image finder's owned source and review locations."""
    layout = CollectionLayout(root)
    pics = layout.pics
    problems: list[str] = []
    if pics.is_symlink():
        problems.append(f"required folder is a symbolic link: {pics}")
    elif not pics.exists():
        problems.append(f"missing required folder: {pics}")
    elif not pics.is_dir():
        problems.append(f"required folder is not a directory: {pics}")

    dups = layout.dups
    if dups.is_symlink():
        problems.append(f"reserved folder is a symbolic link: {dups}")
    elif dups.exists() and not dups.is_dir():
        problems.append(f"reserved path is not a directory: {dups}")
    elif dups.is_dir():
        duplicate_pics = layout.duplicate_pics
        if duplicate_pics.is_symlink():
            problems.append(f"reserved media path is a symbolic link: {duplicate_pics}")
        elif duplicate_pics.exists() and not duplicate_pics.is_dir():
            problems.append(f"reserved media path is not a directory: {duplicate_pics}")

    if problems:
        return problems

    classifier = Classifier(config.classification)
    for path in pics.iterdir():
        if path.is_symlink():
            problems.append(f"symbolic link cannot be verified: {path}")
        elif path.is_dir():
            if not config.ignores_directory(path, root):
                problems.append(f"unexpected directory in pics: {path}")
        elif path.is_file():
            if config.ignores_file(path, root):
                continue
            kind, _ = classifier.classify(path)
            if kind == "video":
                problems.append(
                    f"misplaced video: {path} "
                    "(expected outside the image finder's pics folder)"
                )
    return problems


def review_directories(root: Path) -> tuple[Path, Path]:
    layout = CollectionLayout(root)
    return layout.dups, layout.duplicate_pics


def format_size(size: int) -> str:
    value = float(size)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def print_storage_summary(
    duplicate_groups: list[list[ImageRecord]], scanned_bytes: int
) -> None:
    retained_bytes = 0
    duplicate_bytes = 0
    duplicate_count = 0
    for records in duplicate_groups:
        ordered = sorted(records, key=keep_sort_key)
        retained_bytes += ordered[0].file_size
        duplicate_bytes += sum(record.file_size for record in ordered[1:])
        duplicate_count += len(ordered) - 1

    duplicate_set_bytes = retained_bytes + duplicate_bytes
    set_percentage = (
        duplicate_bytes / duplicate_set_bytes * 100 if duplicate_set_bytes else 0.0
    )
    scan_percentage = duplicate_bytes / scanned_bytes * 100 if scanned_bytes else 0.0
    print("\nDuplicate storage summary:")
    print(
        f"  Retained originals: {len(duplicate_groups)} file(s), "
        f"{format_size(retained_bytes)}"
    )
    print(
        f"  Extra duplicate copies: {duplicate_count} file(s), "
        f"{format_size(duplicate_bytes)}"
    )
    print(f"  Duplicate sets combined: {format_size(duplicate_set_bytes)}")
    print(
        "  Potentially reclaimable if extra copies were deleted: "
        f"{format_size(duplicate_bytes)} ({set_percentage:.1f}% of duplicate-set "
        f"storage; {scan_percentage:.1f}% of scanned picture storage)"
    )
    print("  No files are deleted by this tool.")


def copy_target(
    destination: Path,
    kept_path: Path,
    duplicate_path: Path,
    starting_number: int,
    reserved: set[str],
) -> tuple[Path, int]:
    """Choose a flat, readable, collision-safe duplicate filename."""
    number = starting_number
    suffix = duplicate_path.suffix or kept_path.suffix
    while True:
        target = destination / f"{kept_path.stem}_copy({number}){suffix}"
        key = str(target).casefold()
        if key not in reserved and not os.path.lexists(target):
            reserved.add(key)
            return target, number
        number += 1


def describe_undo_action(root: Path, action: Action, apply: bool) -> None:
    verb = action.operation.lower().replace("_", " ")
    prefix = verb if apply else f"would {verb}"
    if action.before and action.after:
        print(f"\n{prefix}: {root / action.before}\n  to: {root / action.after}")
    elif action.after:
        print(f"\n{prefix}: {root / action.after}")
    elif action.before:
        print(f"\n{prefix}: {root / action.before}")


def undo_duplicate_run(root: Path, apply: bool) -> int:
    log = ActionLog(root)
    try:
        plan = log.plan_undo(ToolId.IMAGE_DUPLICATES)
    except NoUndoableRun as error:
        print(str(error), file=sys.stderr)
        return 2
    except (ActionConflict, ActionLogError, OSError) as error:
        print(f"Cannot safely undo duplicate moves: {error}", file=sys.stderr)
        return 1

    print(f"Using action log: {log.path}")
    print(f"Duplicate-finder run: {plan.target.run_id}")
    for action in plan.actions:
        describe_undo_action(root, action, apply)
    if not apply:
        print(f"\nWould reverse {len(plan.actions)} recorded action(s).")
        if plan.actions:
            print("Dry run only. Add --apply after reviewing this list.")
        return 0

    try:
        result = log.apply_undo(ToolId.IMAGE_DUPLICATES)
    except (ActionConflict, ActionLogError, OSError) as error:
        print(f"Duplicate undo failed safely: {error}", file=sys.stderr)
        return 1
    print(f"\nReversed {result.action_count} recorded action(s).")
    print("Verification passed: every recorded duplicate-file action was reversed.")
    return 0


def keep_sort_key(record: ImageRecord) -> tuple[int, int, str]:
    # Prefer the largest file because it may retain more metadata. Then prefer
    # the older file, followed by a stable filename ordering.
    return (-record.file_size, record.modified_ns, str(record.path).casefold())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find images with exactly the same displayed pixels. By default, "
            "only report what would happen."
        )
    )
    parser.add_argument(
        "folder", type=Path, help="organized collection root containing pics"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the moves (without this option, the script is a dry run)",
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help=(
            "reverse the newest active duplicate-finder run in the action log; "
            "this is also a dry run unless --apply is supplied"
        ),
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
    if args.undo:
        return undo_duplicate_run(root, args.apply)

    try:
        config = load_config(root, args.config)
    except ConfigError as error:
        print(f"Cannot use configuration: {error}", file=sys.stderr)
        return 2

    _, destination = review_directories(root)

    problems = collection_layout_problems(root, config)
    if problems:
        print("Collection is not ready for duplicate scanning:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            f'Run pymo organize "{root}" first so pictures are directly in pics.',
            file=sys.stderr,
        )
        return 2

    pics = CollectionLayout(root).pics
    paths, ignored = discover_images(pics, root, config)
    print(f"Scanning {len(paths)} image(s) in {pics}")
    for message in ignored_messages(ignored, root, args.show_ignored):
        print(message)

    groups: dict[str, list[ImageRecord]] = defaultdict(list)
    scanned_bytes = 0
    skipped: list[tuple[Path, str]] = []
    path_sizes: dict[Path, int] = {}
    for path in paths:
        try:
            path_sizes[path] = path.stat().st_size
        except OSError:
            path_sizes[path] = 0
    progress = ProgressMeter(
        len(paths),
        sum(path_sizes.values()),
        config.performance.progress_interval_seconds,
    )
    for path in paths:
        try:
            stat = path.stat()
            record = ImageRecord(
                path=path,
                pixel_hash=displayed_pixel_hash(path),
                file_size=stat.st_size,
                modified_ns=stat.st_mtime_ns,
            )
            groups[record.pixel_hash].append(record)
            scanned_bytes += record.file_size
        except (OSError, ValueError, UnidentifiedImageError) as error:
            skipped.append((path, str(error)))
        progress_message = progress.advance(
            "processed", byte_count=path_sizes[path]
        )
        if progress_message:
            print(f"  {progress_message}")

    duplicate_groups = [items for items in groups.values() if len(items) > 1]
    duplicate_groups.sort(key=lambda items: str(min(r.path for r in items)).casefold())

    move_plan: list[tuple[str, ImageRecord, ImageRecord, Path]] = []
    reserved_targets: set[str] = set()
    for group_number, records in enumerate(duplicate_groups, start=1):
        ordered = sorted(records, key=keep_sort_key)
        kept = ordered[0]
        group_name = f"set_{group_number:04d}"
        print(f"\nGroup {group_number}: keep {kept.path}")

        next_number = 1
        for duplicate in ordered[1:]:
            target, used_number = copy_target(
                destination,
                kept.path,
                duplicate.path,
                next_number,
                reserved_targets,
            )
            next_number = used_number + 1
            move_plan.append((group_name, kept, duplicate, target))
            print(f"  duplicate: {duplicate.path}")
            print(f"  {'move to' if args.apply else 'would move to'}: {target}")

    if args.apply and move_plan:
        try:
            actions = [
                Action.for_file(root, duplicate.path, target, "MOVE")
                for _, _, duplicate, target in move_plan
            ]
            log = ActionLog(root)
            with log.transaction(ToolId.IMAGE_DUPLICATES) as transaction:
                for directory in review_directories(root):
                    if not directory.exists():
                        transaction.perform(Action.create_directory(root, directory))
                for action in actions:
                    transaction.perform(action)
                transaction.commit()
            print(f"\nAction log: {log.path}")
        except (ActionConflict, ActionLogError, OSError) as error:
            print(f"Duplicate moves stopped safely: {error}", file=sys.stderr)
            return 1

        verification_failures = [
            (duplicate.path, target)
            for _, _, duplicate, target in move_plan
            if os.path.lexists(duplicate.path)
            or target.is_symlink()
            or not target.is_file()
        ]
        if verification_failures:
            print("\nVerification needs attention:", file=sys.stderr)
            for source, target in verification_failures:
                print(f"  {source} -> {target}", file=sys.stderr)
            return 1

    duplicate_count = len(move_plan)
    verb = "Moved" if args.apply else "Would move"
    print(
        f"\n{verb} {duplicate_count} duplicate(s) from "
        f"{len(duplicate_groups)} group(s)."
    )
    print_storage_summary(duplicate_groups, scanned_bytes)
    if not args.apply and duplicate_count:
        print("Dry run only. Add --apply after reviewing this list.")

    if skipped:
        print(f"\nSkipped {len(skipped)} file(s):")
        for path, reason in skipped:
            print(f"  {path}: {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
