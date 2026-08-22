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
    ToolId,
    is_action_log_path,
)
from pymo.collection import CollectionLayout
from pymo.config import (
    ClassificationConfig,
    ConfigError,
    PymoConfig,
    add_config_argument,
    add_show_ignored_argument,
    ignored_messages,
    load_config,
)
from pymo.discovery import DiscoveryError, walk_complete
from pymo.logging_config import emit as print
from pymo.progress import ProgressMeter


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
class OrganizationResult:
    log_path: Path
    removed_directories: int


class Classifier:
    def __init__(self, policy: ClassificationConfig) -> None:
        self.policy = policy
        self.file_command = shutil.which("file")
        self.warning: str | None = None
        if not self.file_command:
            self.warning = (
                "The system 'file' utility was not found; classification will "
                "fall back to filenames and extensions."
            )

    def detect_mime(self, path: Path, descriptor: int | None = None) -> str:
        if self.file_command:
            try:
                command = [self.file_command, "--brief", "--mime-type"]
                stdin: int | None = None
                if descriptor is not None:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    command.append("-")
                    stdin = descriptor
                else:
                    command.extend(("--", str(path)))
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    stdin=stdin,
                )
                detected = result.stdout.strip().split(";", 1)[0].lower()
                if result.returncode == 0 and detected:
                    return detected
            except (OSError, subprocess.SubprocessError):
                pass

        guessed, _ = mimetypes.guess_type(path.name)
        return guessed.lower() if guessed else "unknown"

    def classify(self, path: Path, descriptor: int | None = None) -> tuple[str, str]:
        mime_type = self.detect_mime(path, descriptor)
        if mime_type.startswith("image/"):
            return "picture", mime_type
        if (
            mime_type.startswith("video/")
            or mime_type in self.policy.video_application_mime_types
        ):
            return "video", mime_type

        extension = path.suffix.lower()
        if mime_type in self.policy.generic_mime_types or mime_type == "unknown":
            if extension in self.policy.image_extensions:
                return "picture", mime_type
            if extension in self.policy.video_extensions:
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
    return CollectionLayout(root).is_in_duplicates(path)


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


def discover_files(
    root: Path, config: PymoConfig
) -> tuple[list[Path], list[Path], list[Path]]:
    files: list[Path] = []
    skipped_links: list[Path] = []
    ignored: list[Path] = []
    for current, directory_names, file_names in walk_complete(root):
        current_path = Path(current)
        retained_directories: list[str] = []
        for name in directory_names:
            path = current_path / name
            if path.is_symlink():
                skipped_links.append(path)
            elif is_in_dups(path, root):
                continue
            elif config.ignores_directory(path, root):
                ignored.append(path)
            else:
                retained_directories.append(name)
        directory_names[:] = retained_directories

        for name in file_names:
            path = current_path / name
            if path.is_symlink():
                skipped_links.append(path)
            elif config.ignores_file(path, root):
                ignored.append(path)
            elif path.is_file() and not is_action_log_path(root, path):
                files.append(path.absolute())
    files.sort(key=lambda item: str(item).casefold())
    skipped_links.sort(key=lambda item: str(item).casefold())
    ignored.sort(key=lambda item: str(item).casefold())
    return files, skipped_links, ignored


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
    config: PymoConfig,
) -> tuple[list[MoveRecord], list[FileRecord], list[Path], list[Path]]:
    paths, skipped_links, ignored = discover_files(root, config)
    occupied = {path_key(path) for path in paths}
    plan: list[MoveRecord] = []
    already_correct: list[FileRecord] = []
    progress = ProgressMeter(
        len(paths), None, config.performance.progress_interval_seconds
    )

    print(f"Classifying {len(paths)} file(s) in {root}")
    for path in paths:
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
        progress_message = progress.advance("classified")
        if progress_message:
            print(f"  {progress_message}")

    return plan, already_correct, skipped_links, ignored


def removable_directories(
    root: Path, pics: Path, vids: Path, config: PymoConfig
) -> list[Path]:
    protected = {root, pics, vids}
    directories: list[Path] = []
    for current, directory_names, _ in walk_complete(root):
        current_path = Path(current)
        retained_directories: list[str] = []
        for name in directory_names:
            path = current_path / name
            if (
                path.is_symlink()
                or is_in_dups(path, root)
                or config.ignores_directory(path, root)
            ):
                continue
            directories.append(path)
            retained_directories.append(name)
        directory_names[:] = retained_directories
    directories.sort(key=lambda item: len(item.parts), reverse=True)
    return [
        directory
        for directory in directories
        if directory not in protected and not directory.is_symlink()
    ]


def _contains_only_ignored_entries(
    directory: Path, root: Path, config: PymoConfig
) -> bool:
    found_ignored = False
    for current, directory_names, file_names in walk_complete(directory):
        current_path = Path(current)
        retained_directories: list[str] = []
        for name in directory_names:
            path = current_path / name
            if path.is_symlink():
                return False
            if config.ignores_directory(path, root):
                found_ignored = True
            else:
                retained_directories.append(name)
        directory_names[:] = retained_directories
        for name in file_names:
            path = current_path / name
            if path.is_symlink() or not config.ignores_file(path, root):
                return False
            found_ignored = True
    return found_ignored


def remaining_directories(
    root: Path, pics: Path, vids: Path, config: PymoConfig
) -> list[Path]:
    layout = CollectionLayout(root)
    allowed = {
        pics,
        vids,
        layout.dups,
        layout.duplicate_pics,
        layout.duplicate_vids,
    }
    directories: list[Path] = []
    for current, directory_names, _ in walk_complete(root):
        current_path = Path(current)
        retained_directories: list[str] = []
        for name in directory_names:
            path = current_path / name
            if (
                path.is_symlink()
                or is_in_dups(path, root)
                or config.ignores_directory(path, root)
            ):
                continue
            directories.append(path)
            retained_directories.append(name)
        directory_names[:] = retained_directories
    return sorted(
        [
            path
            for path in directories
            if path not in allowed
            and not _contains_only_ignored_entries(path, root, config)
        ],
        key=lambda item: str(item).casefold(),
    )


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
        plan = log.plan_undo(ToolId.ORGANIZE)
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
        result = log.apply_undo(ToolId.ORGANIZE)
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
    config: PymoConfig,
) -> tuple[list[tuple[Path, Path, str]], list[Path], list[Path]]:
    files, links, _ = discover_files(root, config)
    misplaced: list[tuple[Path, Path, str]] = []
    for path in files:
        kind, _ = classifier.classify(path)
        expected = desired_directory(kind, root, pics, vids)
        if path.parent != expected:
            misplaced.append((path, expected, kind))
    return misplaced, remaining_directories(root, pics, vids, config), links


def collection_destination_problem(layout: CollectionLayout) -> str | None:
    for destination in (layout.pics, layout.vids):
        if destination.is_symlink():
            return f"Refusing to use a symbolic link as a destination: {destination}"
        if destination.exists() and not destination.is_dir():
            return f"A file is blocking the required directory: {destination}"
    if layout.dups.is_symlink():
        return (
            "Refusing to use a symbolic link as the reserved directory: "
            f"{layout.dups}"
        )
    if layout.dups.exists() and not layout.dups.is_dir():
        return f"A file is blocking the reserved directory: {layout.dups}"
    return None


def apply_organization_plan(
    root: Path,
    missing_destinations: list[Path],
    plan: list[MoveRecord],
    source_directories: list[Path],
) -> OrganizationResult:
    file_actions = [
        Action.for_file(root, move.source, move.target, "MOVE") for move in plan
    ]
    removed_count = 0
    log = ActionLog(root)
    with log.transaction(ToolId.ORGANIZE) as transaction:
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
    return OrganizationResult(log.path, removed_count)


def report_layout_verification(
    root: Path,
    pics: Path,
    vids: Path,
    classifier: Classifier,
    config: PymoConfig,
) -> int:
    misplaced, extra_directories, remaining_links = verify_layout(
        root, pics, vids, classifier, config
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
        return undo_logged_organization(root, args.apply)

    try:
        config = load_config(root, args.config)
    except ConfigError as error:
        print(f"Cannot use configuration: {error}", file=sys.stderr)
        return 2

    layout = CollectionLayout(root)
    pics = layout.pics
    vids = layout.vids
    destination_problem = collection_destination_problem(layout)
    if destination_problem:
        print(destination_problem)
        return 2

    classifier = Classifier(config.classification)
    if classifier.warning:
        print(f"Warning: {classifier.warning}")

    try:
        plan, already_correct, skipped_links, ignored = build_plan(
            root, pics, vids, classifier, config
        )
        source_directories = removable_directories(root, pics, vids, config)
    except DiscoveryError as error:
        print(f"Organization cannot safely continue: {error}", file=sys.stderr)
        return 1
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
    removed_count = 0
    log_path: Path | None = None
    if args.apply and (missing_destinations or plan or source_directories):
        try:
            result = apply_organization_plan(
                root, missing_destinations, plan, source_directories
            )
            removed_count = result.removed_directories
            log_path = result.log_path
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
    for message in ignored_messages(ignored, root, args.show_ignored):
        print(message)
    if not args.apply and (plan or missing_destinations or source_directories):
        print("Dry run only. Add --apply after reviewing this list.")
    if log_path:
        print(f"Action log: {log_path}")

    if skipped_links:
        print(f"\nSkipped {len(skipped_links)} symbolic link(s):")
        for path in skipped_links:
            print(f"  {path}")

    if args.apply:
        try:
            return report_layout_verification(root, pics, vids, classifier, config)
        except DiscoveryError as error:
            print(f"Verification could not inspect the complete layout: {error}")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
