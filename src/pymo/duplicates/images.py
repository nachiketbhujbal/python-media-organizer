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
import csv
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
)
from pymo.logging_config import emit as print
from pymo.organize import Classifier

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:
    print(
        "This script needs Pillow. Install it with:\n"
        "  python3 -m pip install Pillow",
        file=sys.stderr,
    )
    raise SystemExit(2)


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
}

TOOL_NAME = "find_image_duplicates"
PICS_NAME = "pics"
DUPS_NAME = "dups"


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


def is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def discover_images(pics: Path) -> list[Path]:
    result = []
    for path in pics.glob("*"):
        if (
            path.is_symlink()
            or not path.is_file()
            or path.suffix.lower() not in IMAGE_EXTENSIONS
        ):
            continue
        result.append(path.resolve())
    return sorted(result, key=lambda item: str(item).casefold())


def collection_layout_problems(root: Path) -> list[str]:
    """Validate only the image finder's owned source and review locations."""
    pics = root / PICS_NAME
    problems: list[str] = []
    if pics.is_symlink():
        problems.append(f"required folder is a symbolic link: {pics}")
    elif not pics.exists():
        problems.append(f"missing required folder: {pics}")
    elif not pics.is_dir():
        problems.append(f"required folder is not a directory: {pics}")

    dups = root / DUPS_NAME
    if dups.is_symlink():
        problems.append(f"reserved folder is a symbolic link: {dups}")
    elif dups.exists() and not dups.is_dir():
        problems.append(f"reserved path is not a directory: {dups}")
    elif dups.is_dir():
        duplicate_pics = dups / PICS_NAME
        if duplicate_pics.is_symlink():
            problems.append(f"reserved media path is a symbolic link: {duplicate_pics}")
        elif duplicate_pics.exists() and not duplicate_pics.is_dir():
            problems.append(f"reserved media path is not a directory: {duplicate_pics}")

    if problems:
        return problems

    classifier = Classifier()
    for path in pics.iterdir():
        if path.is_symlink():
            problems.append(f"symbolic link cannot be verified: {path}")
        elif path.is_dir():
            problems.append(f"unexpected directory in pics: {path}")
        elif path.is_file():
            kind, _ = classifier.classify(path)
            if kind == "video":
                problems.append(
                    f"misplaced video: {path} "
                    "(expected outside the image finder's pics folder)"
                )
    return problems


def review_directories(root: Path) -> tuple[Path, Path]:
    dups = root / DUPS_NAME
    return dups, dups / PICS_NAME


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


def reorganize_existing(
    root: Path, legacy_source: Path, destination: Path, apply: bool
) -> int:
    """Flatten group_* results created by older versions using their manifests."""
    if not legacy_source.is_dir():
        print(f"No legacy duplicates directory found: {legacy_source}", file=sys.stderr)
        return 2

    manifest_paths = sorted(legacy_source.glob("move_manifest*.csv"))
    if not manifest_paths:
        print(f"No move manifests found in {legacy_source}", file=sys.stderr)
        return 2

    source_rows: list[tuple[Path, Path]] = []
    seen_sources: set[str] = set()
    skipped: list[tuple[str, str]] = []
    for manifest_path in manifest_paths:
        try:
            with manifest_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    if not row.get("moved_to") or not row.get("kept_file"):
                        continue
                    source = Path(row["moved_to"]).expanduser()
                    kept = Path(row["kept_file"]).expanduser()
                    key = str(source).casefold()
                    if key in seen_sources:
                        continue
                    seen_sources.add(key)

                    if not source.exists():
                        continue
                    if source.is_symlink() or not source.is_file():
                        skipped.append((str(source), "not a regular file"))
                        continue
                    source = source.resolve()
                    if not is_within(source, legacy_source):
                        skipped.append((str(source), "outside the duplicates directory"))
                        continue
                    relative = source.relative_to(legacy_source)
                    if len(relative.parts) < 2 or not relative.parts[0].startswith(
                        "group_"
                    ):
                        # Already flat, or not an old group layout.
                        continue
                    source_rows.append((source, kept))
        except (OSError, csv.Error) as error:
            skipped.append((str(manifest_path), str(error)))

    reserved: set[str] = set()
    next_numbers: dict[str, int] = defaultdict(lambda: 1)
    plan: list[tuple[Path, Path, Path]] = []
    for source, kept in sorted(source_rows, key=lambda item: str(item[0]).casefold()):
        kept_key = str(kept).casefold()
        target, used_number = copy_target(
            destination,
            kept,
            source,
            next_numbers[kept_key],
            reserved,
        )
        next_numbers[kept_key] = used_number + 1
        plan.append((kept, source, target))
        print(f"Kept original: {kept}")
        print(f"  {'move' if apply else 'would move'}: {source}")
        print(f"  to: {target}\n")

    if apply and plan:
        directories = {
            directory
            for _, source, _ in plan
            for directory in source.parents
            if directory != legacy_source and is_within(directory, legacy_source)
        }
        try:
            actions = [
                Action.for_file(root, source, target, "MOVE")
                for _, source, target in plan
            ]
            log = ActionLog(root)
            with log.transaction(TOOL_NAME) as transaction:
                for directory in review_directories(root):
                    if not directory.exists():
                        transaction.perform(Action.create_directory(root, directory))
                for action in actions:
                    transaction.perform(action)
                for directory in sorted(
                    directories, key=lambda path: len(path.parts), reverse=True
                ):
                    if directory.is_dir() and not any(directory.iterdir()):
                        transaction.perform(Action.remove_directory(root, directory))
                transaction.commit()
            print(f"Action log: {log.path}")
        except (ActionConflict, ActionLogError, OSError) as error:
            print(f"Reorganization stopped safely: {error}", file=sys.stderr)
            return 1

    verb = "Reorganized" if apply else "Would reorganize"
    print(f"{verb} {len(plan)} duplicate file(s) into {destination}")
    if not apply and plan:
        print("Dry run only. Add --apply after reviewing this list.")
    if skipped:
        print(f"\nSkipped {len(skipped)} item(s):")
        for path, reason in skipped:
            print(f"  {path}: {reason}")
    return 0


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
        plan = log.plan_undo(TOOL_NAME)
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
        result = log.apply_undo(TOOL_NAME)
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
        "--recursive",
        action="store_true",
        help="deprecated compatibility option; organized pics are always scanned",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the moves (without this option, the script is a dry run)",
    )
    parser.add_argument(
        "--duplicates-dir",
        type=Path,
        help=(
            "legacy duplicates source used only with --reorganize-existing "
            "(default: COLLECTION/duplicates)"
        ),
    )
    parser.add_argument(
        "--reorganize-existing",
        action="store_true",
        help=(
            "flatten legacy group_* directories using prior move manifests; "
            "this is also a dry run unless --apply is supplied"
        ),
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help=(
            "reverse the newest active duplicate-finder run in the action log; "
            "this is also a dry run unless --apply is supplied"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    if args.undo and args.reorganize_existing:
        print("--undo cannot be combined with --reorganize-existing", file=sys.stderr)
        return 2
    if args.undo:
        return undo_duplicate_run(root, args.apply)

    _, destination = review_directories(root)

    if args.reorganize_existing:
        legacy_source = (
            args.duplicates_dir.expanduser().resolve()
            if args.duplicates_dir
            else root / "duplicates"
        )
        if not is_within(legacy_source, root):
            print("The legacy duplicates source must be inside the collection.", file=sys.stderr)
            return 2
        return reorganize_existing(root, legacy_source, destination, args.apply)

    if args.duplicates_dir:
        print("--duplicates-dir can only be used with --reorganize-existing", file=sys.stderr)
        return 2
    if args.recursive:
        print("Note: --recursive is no longer needed; scanning organized pics only.")

    problems = collection_layout_problems(root)
    if problems:
        print("Collection is not ready for duplicate scanning:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            f'Run pymo organize "{root}" first so pictures are directly in pics.',
            file=sys.stderr,
        )
        return 2

    pics = root / PICS_NAME
    paths = discover_images(pics)
    print(f"Scanning {len(paths)} image(s) in {pics}")

    groups: dict[str, list[ImageRecord]] = defaultdict(list)
    scanned_bytes = 0
    skipped: list[tuple[Path, str]] = []
    for number, path in enumerate(paths, start=1):
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
        if number % 100 == 0:
            print(f"  processed {number}/{len(paths)}")

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
            with log.transaction(TOOL_NAME) as transaction:
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
