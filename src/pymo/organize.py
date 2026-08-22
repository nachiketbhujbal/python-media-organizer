#!/usr/bin/env python3
"""Flatten a directory into pics, vids, and non-media files at its root.

The default is a dry run. Nothing is moved unless --apply is supplied.
Existing files are never overwritten, symbolic links are never followed, and
completed operations are appended to a shared JSONL action log. An organization
run can be safely reversed with --undo, which is also a dry run by default.
The reserved dups review tree is left untouched.
"""

from __future__ import annotations

import argparse
import csv
import mimetypes
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pymo.action_log import (
    Action,
    ActionConflict,
    ActionLog,
    ActionLogError,
    NoUndoableRun,
    action_log_exists,
    is_action_log_path,
)
from pymo.logging_config import emit as print


IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".cr2",
    ".cr3",
    ".dng",
    ".gif",
    ".heic",
    ".heif",
    ".jfif",
    ".jpe",
    ".jpeg",
    ".jpg",
    ".nef",
    ".orf",
    ".png",
    ".raf",
    ".raw",
    ".rw2",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
}

VIDEO_EXTENSIONS = {
    ".3g2",
    ".3gp",
    ".asf",
    ".avi",
    ".divx",
    ".flv",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpe",
    ".mpeg",
    ".mpg",
    ".mts",
    ".ogv",
    ".rm",
    ".rmvb",
    ".ts",
    ".vob",
    ".webm",
    ".wmv",
}

VIDEO_APPLICATION_MIMES = {
    "application/mp4",
    "application/ogg",
    "application/vnd.rn-realmedia",
}

GENERIC_MIMES = {
    "application/octet-stream",
    "inode/x-empty",
}


@dataclass(frozen=True)
class FileRecord:
    path: Path
    kind: str
    mime_type: str


@dataclass(frozen=True)
class MoveRecord:
    source: Path
    target: Path
    kind: str
    mime_type: str


@dataclass(frozen=True)
class UndoRecord:
    current: Path
    original: Path
    kind: str
    mime_type: str


class Classifier:
    def __init__(self) -> None:
        self.file_command = shutil.which("file")
        self.warning: str | None = None
        if not self.file_command:
            self.warning = (
                "The system 'file' utility was not found; classification will "
                "fall back to filenames and extensions."
            )

    def detect_mime(self, path: Path) -> str:
        if self.file_command:
            try:
                result = subprocess.run(
                    [self.file_command, "--brief", "--mime-type", "--", str(path)],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                detected = result.stdout.strip().split(";", 1)[0].lower()
                if result.returncode == 0 and detected:
                    return detected
            except (OSError, subprocess.SubprocessError):
                pass

        guessed, _ = mimetypes.guess_type(path.name)
        return guessed.lower() if guessed else "unknown"

    def classify(self, path: Path) -> tuple[str, str]:
        mime_type = self.detect_mime(path)
        if mime_type.startswith("image/"):
            return "picture", mime_type
        if mime_type.startswith("video/") or mime_type in VIDEO_APPLICATION_MIMES:
            return "video", mime_type

        extension = path.suffix.lower()
        if mime_type in GENERIC_MIMES or mime_type == "unknown":
            if extension in IMAGE_EXTENSIONS:
                return "picture", mime_type
            if extension in VIDEO_EXTENSIONS:
                return "video", mime_type

        # A meaningful non-media content signature takes precedence over a
        # misleading extension (for example, a text file named fake.jpg).
        return "other", mime_type


def path_key(path: Path) -> str:
    # casefold also prevents planned collisions on case-insensitive filesystems.
    return str(path).casefold()


def path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def is_in_dups(path: Path, root: Path) -> bool:
    """Return whether path is the reserved dups tree or one of its children."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return bool(relative.parts) and relative.parts[0] == "dups"


def available_target(
    desired: Path, occupied: set[str], starting_number: int = 0
) -> Path:
    """Choose a Finder-friendly target name without overwriting anything."""
    number = starting_number
    while True:
        candidate = (
            desired
            if number == 0
            else desired.with_name(f"{desired.stem} ({number}){desired.suffix}")
        )
        if path_key(candidate) not in occupied and not path_exists(candidate):
            occupied.add(path_key(candidate))
            return candidate
        number += 1


def discover_files(root: Path) -> tuple[list[Path], list[Path]]:
    files: list[Path] = []
    skipped_links: list[Path] = []
    for path in root.rglob("*"):
        if is_in_dups(path, root):
            continue
        if path.is_symlink():
            skipped_links.append(path)
        elif path.is_file() and not is_action_log_path(root, path):
            files.append(path.absolute())
    files.sort(key=lambda item: str(item).casefold())
    skipped_links.sort(key=lambda item: str(item).casefold())
    return files, skipped_links


def desired_directory(kind: str, root: Path, pics: Path, vids: Path) -> Path:
    if kind == "picture":
        return pics
    if kind == "video":
        return vids
    return root


def build_plan(
    root: Path,
    pics: Path,
    vids: Path,
    classifier: Classifier,
) -> tuple[list[MoveRecord], list[FileRecord], list[Path]]:
    paths, skipped_links = discover_files(root)
    occupied = {path_key(path) for path in paths}
    plan: list[MoveRecord] = []
    already_correct: list[FileRecord] = []

    print(f"Classifying {len(paths)} file(s) in {root}")
    for number, path in enumerate(paths, start=1):
        kind, mime_type = classifier.classify(path)
        record = FileRecord(path=path, kind=kind, mime_type=mime_type)
        destination = desired_directory(kind, root, pics, vids)
        if path.parent == destination:
            already_correct.append(record)
        else:
            target = available_target(destination / path.name, occupied)
            plan.append(
                MoveRecord(
                    source=path,
                    target=target,
                    kind=kind,
                    mime_type=mime_type,
                )
            )
        if number % 200 == 0:
            print(f"  classified {number}/{len(paths)}")

    return plan, already_correct, skipped_links


def removable_directories(root: Path, pics: Path, vids: Path) -> list[Path]:
    protected = {root, pics, vids}
    directories = [path for path in root.rglob("*") if path.is_dir()]
    directories.sort(key=lambda item: len(item.parts), reverse=True)
    return [
        directory
        for directory in directories
        if directory not in protected
        and not is_in_dups(directory, root)
        and not directory.is_symlink()
    ]


def remaining_directories(root: Path, pics: Path, vids: Path) -> list[Path]:
    dups = root / "dups"
    allowed = {pics, vids, dups, dups / "pics", dups / "vids"}
    return sorted(
        [
            path
            for path in root.rglob("*")
            if path.is_dir() and path not in allowed
        ],
        key=lambda item: str(item).casefold(),
    )


def unique_manifest_path(root: Path) -> Path:
    desired = root / "organization_manifest.csv"
    occupied: set[str] = set()
    return available_target(desired, occupied)


def manifest_path_within_root(value: str, root: Path) -> Path:
    """Resolve a path from a manifest and require it to stay within ROOT."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"path is outside the selected folder: {path}") from error
    return resolved


def latest_organization_manifest(root: Path) -> Path | None:
    manifests = [
        path
        for path in root.glob("organization_manifest*.csv")
        if path.is_file() and not path.is_symlink()
    ]
    if not manifests:
        return None
    return max(
        manifests,
        key=lambda path: (path.stat().st_mtime_ns, str(path).casefold()),
    )


def read_undo_records(manifest_path: Path, root: Path) -> list[UndoRecord]:
    required = {"kind", "mime_type", "moved_from", "moved_to"}
    records: list[UndoRecord] = []
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            missing = sorted(required.difference(reader.fieldnames or []))
            raise ValueError(
                "manifest is missing required column(s): " + ", ".join(missing)
            )

        for row_number, row in enumerate(reader, start=2):
            if not row["moved_from"] or not row["moved_to"]:
                raise ValueError(f"manifest row {row_number} has an empty path")
            original = manifest_path_within_root(row["moved_from"], root)
            current = manifest_path_within_root(row["moved_to"], root)
            if original == current:
                raise ValueError(
                    f"manifest row {row_number} uses the same source and target"
                )
            records.append(
                UndoRecord(
                    current=current,
                    original=original,
                    kind=row["kind"],
                    mime_type=row["mime_type"],
                )
            )

    if not records:
        raise ValueError("manifest contains no completed moves")

    current_keys = [path_key(record.current) for record in records]
    original_keys = [path_key(record.original) for record in records]
    if len(current_keys) != len(set(current_keys)):
        raise ValueError("manifest contains a duplicate organized path")
    if len(original_keys) != len(set(original_keys)):
        raise ValueError("manifest contains a duplicate original path")
    if set(current_keys).intersection(original_keys):
        raise ValueError("manifest contains overlapping move paths")
    return records


def has_symlink_parent(path: Path, root: Path) -> bool:
    """Return whether an existing parent between PATH and ROOT is a symlink."""
    current = path.parent
    while current != root:
        if current.is_symlink():
            return True
        current = current.parent
    return False


def undo_organization(
    root: Path, requested_manifest: Path | None, apply: bool
) -> int:
    if requested_manifest is None:
        manifest_path = latest_organization_manifest(root)
        if manifest_path is None:
            print(f"No organization manifest found in {root}", file=sys.stderr)
            return 2
    else:
        candidate = requested_manifest.expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        manifest_path = candidate.resolve()
        try:
            manifest_path.relative_to(root)
        except ValueError:
            print(
                f"The organization manifest must be inside {root}: {manifest_path}",
                file=sys.stderr,
            )
            return 2
        if manifest_path.is_symlink() or not manifest_path.is_file():
            print(f"Not a regular manifest file: {manifest_path}", file=sys.stderr)
            return 2

    try:
        manifest_stat = manifest_path.stat()
        records = read_undo_records(manifest_path, root)
    except (OSError, csv.Error, ValueError) as error:
        print(f"Cannot use organization manifest {manifest_path}: {error}", file=sys.stderr)
        return 2

    # Reverse the completed moves so the last organization move is undone first.
    records.reverse()
    plan: list[UndoRecord] = []
    already_restored: list[UndoRecord] = []
    preflight_failures: list[tuple[UndoRecord, str]] = []
    for record in records:
        current_exists = path_exists(record.current)
        original_exists = path_exists(record.original)
        if current_exists and original_exists:
            preflight_failures.append(
                (record, "both the organized and original paths already exist")
            )
        elif current_exists:
            if record.current.is_symlink() or not record.current.is_file():
                preflight_failures.append(
                    (record, "organized path is not a regular file")
                )
            elif has_symlink_parent(record.original, root):
                preflight_failures.append(
                    (record, "an original parent directory is a symbolic link")
                )
            else:
                plan.append(record)
        elif original_exists:
            if record.original.is_symlink() or not record.original.is_file():
                preflight_failures.append(
                    (record, "original path is not a regular file")
                )
            else:
                already_restored.append(record)
        else:
            preflight_failures.append(
                (record, "organized file is missing and original path is empty")
            )

    print(f"Using organization manifest: {manifest_path}")
    for record in plan:
        print(
            f"\n{record.kind.upper()} ({record.mime_type})\n"
            f"  {'restore' if apply else 'would restore'}: {record.current}\n"
            f"  to: {record.original}"
        )

    if already_restored:
        print(f"\nAlready restored: {len(already_restored)} file(s).")

    if preflight_failures:
        print(f"\nCannot safely restore {len(preflight_failures)} file(s):")
        for record, reason in preflight_failures:
            print(f"  {record.current}: {reason}")
        if apply:
            print("No files were moved because the undo preflight did not pass.")
        return 1

    if not apply:
        print(f"\nWould restore {len(plan)} file(s).")
        if plan:
            print("Dry run only. Add --apply after reviewing this list.")
        return 0

    failures: list[tuple[UndoRecord, str]] = []
    for record in plan:
        if (
            not record.current.is_file()
            or record.current.is_symlink()
            or path_exists(record.original)
            or has_symlink_parent(record.original, root)
        ):
            failures.append((record, "paths changed after the undo preflight"))
            continue
        try:
            record.original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(record.current), str(record.original))
        except OSError as error:
            failures.append((record, str(error)))

    verification_failures: list[tuple[UndoRecord, str]] = []
    for record in records:
        if not record.original.is_file() or record.original.is_symlink():
            verification_failures.append((record, "original file was not restored"))
        if path_exists(record.current):
            verification_failures.append((record, "organized copy still exists"))

    print(f"\nRestored {len(plan) - len(failures)} file(s).")
    if failures:
        print(f"\nFailed to restore {len(failures)} file(s):")
        for record, reason in failures:
            print(f"  {record.current}: {reason}")

    if not failures and not verification_failures:
        print(
            "\nVerification passed: every file in the organization manifest "
            "is back at its original path."
        )
        try:
            current_manifest_stat = manifest_path.lstat()
            if (
                current_manifest_stat.st_dev != manifest_stat.st_dev
                or current_manifest_stat.st_ino != manifest_stat.st_ino
                or manifest_path.is_symlink()
            ):
                raise OSError("manifest changed during the undo run")
            manifest_path.unlink()
        except OSError as error:
            print(
                f"Could not remove the consumed organization manifest "
                f"{manifest_path}: {error}"
            )
            return 1
        print(f"Removed consumed organization manifest: {manifest_path}")
        for destination in (root / "pics", root / "vids"):
            if destination.is_dir() and not any(destination.iterdir()):
                print(
                    f"Empty directory retained for safety: {destination} "
                    "(the old manifest does not say whether it existed before)."
                )
        return 0

    if verification_failures:
        print("\nUndo verification needs attention:")
        for record, reason in verification_failures:
            print(f"  {record.original}: {reason}")
    return 1


def describe_logged_action(root: Path, action: Action, apply: bool) -> None:
    verb = action.operation.lower().replace("_", " ")
    prefix = verb if apply else f"would {verb}"
    if action.before and action.after:
        print(f"\n{prefix}: {root / action.before}\n  to: {root / action.after}")
    elif action.after:
        print(f"\n{prefix}: {root / action.after}")
    elif action.before:
        print(f"\n{prefix}: {root / action.before}")


def undo_logged_organization(root: Path, apply: bool) -> int:
    log = ActionLog(root)
    try:
        plan = log.plan_undo("organize_media")
    except NoUndoableRun as error:
        print(str(error), file=sys.stderr)
        return 2
    except (ActionConflict, ActionLogError, OSError) as error:
        print(f"Cannot safely undo organization: {error}", file=sys.stderr)
        return 1

    print(f"Using action log: {log.path}")
    print(f"Organization run: {plan.target.run_id}")
    for action in plan.actions:
        describe_logged_action(root, action, apply)

    if not apply:
        print(f"\nWould reverse {len(plan.actions)} recorded action(s).")
        if plan.actions:
            print("Dry run only. Add --apply after reviewing this list.")
        return 0

    try:
        result = log.apply_undo("organize_media")
    except (ActionConflict, ActionLogError, OSError) as error:
        print(f"Undo failed safely: {error}", file=sys.stderr)
        return 1

    print(f"\nReversed {result.action_count} recorded action(s).")
    print(
        "Verification passed: every recorded organization action was reversed "
        "and the append-only action log was retained."
    )
    return 0


def verify_layout(
    root: Path,
    pics: Path,
    vids: Path,
    classifier: Classifier,
) -> tuple[list[tuple[Path, Path, str]], list[Path], list[Path]]:
    files, links = discover_files(root)
    misplaced: list[tuple[Path, Path, str]] = []
    for path in files:
        kind, _ = classifier.classify(path)
        expected = desired_directory(kind, root, pics, vids)
        if path.parent != expected:
            misplaced.append((path, expected, kind))
    return misplaced, remaining_directories(root, pics, vids), links


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Flatten a parent directory so pictures are in pics, videos are in "
            "vids, and all other files are at the parent directory's root."
        )
    )
    parser.add_argument("folder", type=Path, help="parent directory to organize")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the moves (without this option, the script is a dry run)",
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help=(
            "reverse the newest active organization run in the action log; "
            "this is also a dry run unless --apply is supplied"
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="specific legacy CSV organization manifest to use with --undo",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    if args.manifest and not args.undo:
        print("--manifest can only be used with --undo", file=sys.stderr)
        return 2
    if args.undo:
        if not args.manifest and action_log_exists(root):
            return undo_logged_organization(root, args.apply)
        return undo_organization(root, args.manifest, args.apply)

    pics = root / "pics"
    vids = root / "vids"
    for destination in (pics, vids):
        if destination.is_symlink():
            print(f"Refusing to use a symbolic link as a destination: {destination}")
            return 2
        if destination.exists() and not destination.is_dir():
            print(f"A file is blocking the required directory: {destination}")
            return 2

    dups = root / "dups"
    if dups.is_symlink():
        print(f"Refusing to use a symbolic link as the reserved directory: {dups}")
        return 2
    if dups.exists() and not dups.is_dir():
        print(f"A file is blocking the reserved directory: {dups}")
        return 2

    classifier = Classifier()
    if classifier.warning:
        print(f"Warning: {classifier.warning}")

    plan, already_correct, skipped_links = build_plan(root, pics, vids, classifier)
    for move in plan:
        print(
            f"\n{move.kind.upper()} ({move.mime_type})\n"
            f"  {'move' if args.apply else 'would move'}: {move.source}\n"
            f"  to: {move.target}"
        )

    counts = {"picture": 0, "video": 0, "other": 0}
    for move in plan:
        counts[move.kind] += 1

    missing_destinations = [path for path in (pics, vids) if not path.exists()]
    source_directories = removable_directories(root, pics, vids)
    removed_count = 0
    log_path: Path | None = None
    if args.apply and (missing_destinations or plan or source_directories):
        try:
            file_actions = [
                Action.for_file(root, move.source, move.target, "MOVE")
                for move in plan
            ]
            log = ActionLog(root)
            with log.transaction("organize_media") as transaction:
                for destination in missing_destinations:
                    transaction.perform(Action.create_directory(root, destination))
                for file_action in file_actions:
                    transaction.perform(file_action)
                for directory in source_directories:
                    if (
                        directory.is_dir()
                        and not directory.is_symlink()
                        and not any(directory.iterdir())
                    ):
                        transaction.perform(Action.remove_directory(root, directory))
                        removed_count += 1
                transaction.commit()
            log_path = log.path
        except (ActionConflict, ActionLogError, OSError) as error:
            print(f"\nOrganization stopped safely: {error}", file=sys.stderr)
            print(
                "Any completed actions remain recorded and can be inspected "
                "with --undo.",
                file=sys.stderr,
            )
            return 1
    elif not args.apply:
        for destination in missing_destinations:
            print(f"\nWould create directory: {destination}")

    if args.apply:
        print(f"\nRemoved {removed_count} empty source directories.")

    action = "Moved" if args.apply else "Would move"
    print(
        f"\n{action} {len(plan)} file(s): "
        f"{counts['picture']} picture(s), {counts['video']} video(s), "
        f"and {counts['other']} other file(s)."
    )
    print(f"Already correctly placed: {len(already_correct)} file(s).")
    if not args.apply and (plan or missing_destinations or source_directories):
        print("Dry run only. Add --apply after reviewing this list.")
    if log_path:
        print(f"Action log: {log_path}")

    if skipped_links:
        print(f"\nSkipped {len(skipped_links)} symbolic link(s):")
        for path in skipped_links:
            print(f"  {path}")

    if args.apply:
        misplaced, extra_directories, remaining_links = verify_layout(
            root, pics, vids, classifier
        )
        if not misplaced and not extra_directories and not remaining_links:
            print(
                "\nVerification passed: pics contains only pictures, vids "
                "contains only videos, dups remains isolated, and all other "
                "files are at the root."
            )
            return 0

        print("\nVerification needs attention:")
        for path, expected, kind in misplaced:
            print(f"  misplaced {kind}: {path} (expected directly in {expected})")
        for directory in extra_directories:
            print(f"  remaining directory: {directory}")
        for link in remaining_links:
            print(f"  unverified symbolic link: {link}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
