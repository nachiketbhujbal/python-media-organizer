#!/usr/bin/env python3
"""Rename media predictably without guessing what its contents depict.

Names use the collection directory, media kind, a stable sequence number, an
available source or embedded timestamp, and an optional cleaned descriptor.
The default is a dry run. Applied renames use the shared append-only action log
and can be reversed with --undo.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from pymo.action_log import (
    Action,
    ActionConflict,
    ActionLog,
    ActionLogError,
    NoUndoableRun,
    ToolId,
    action_log_path,
)
from pymo.config import (
    ConfigError,
    PymoConfig,
    add_config_argument,
    add_show_ignored_argument,
    ignored_messages,
    load_config,
)
from pymo.logging_config import emit as print
from pymo.organize import Classifier, discover_files, path_key
from pymo.progress import ProgressMeter


@dataclass(frozen=True)
class RenameRecord:
    source: Path
    target: Path
    kind: str
    timestamp: str | None
    descriptor: str | None


def _valid_timestamp(value: str, milliseconds: str | None = None) -> str | None:
    try:
        parsed = datetime.strptime(value, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    result = parsed.strftime("%Y-%m-%d_%H-%M-%S")
    return f"{result}-{milliseconds}" if milliseconds else result


def _timestamp_patterns() -> tuple[str, ...]:
    """Return implementation-owned parsing rules without mutable globals."""
    return (
        r"(?i)(?:IMG|VID)_(?P<date>\d{8})_(?P<time>\d{6})"
        r"(?:_(?P<millis>\d{3}))?(?:_\d+)?",
        r"(?i)(?:photo|video)_(?P<date>\d{4}-\d{2}-\d{2})_"
        r"(?P<time>\d{2}-\d{2}-\d{2})",
        r"(?P<date>\d{4}-\d{2}-\d{2})[ _]"
        r"(?P<hour>\d{2})[.:-](?P<minute>\d{2})[.:-](?P<second>\d{2})"
        r"(?:[_-](?P<millis>\d{3}))?",
        r"(?P<year>\d{4})_(?P<month>\d{2})_(?P<day>\d{2})_"
        r"(?P<hour>\d{2})_(?P<minute>\d{2})_(?P<second>\d{2})",
        r"(?<!\d)(?P<date>\d{4}-\d{2}-\d{2})(?![-\d])",
    )


def timestamp_from_name(name: str) -> str | None:
    compact, labeled, spaced, underscore, date_only = _timestamp_patterns()
    match = re.search(compact, name)
    if match:
        return _valid_timestamp(
            match.group("date") + match.group("time"), match.group("millis")
        )

    match = re.search(labeled, name)
    if match:
        value = match.group("date").replace("-", "") + match.group("time").replace(
            "-", ""
        )
        return _valid_timestamp(value)

    match = re.search(spaced, name)
    if match:
        value = match.group("date").replace("-", "") + "".join(
            match.group(part) for part in ("hour", "minute", "second")
        )
        return _valid_timestamp(value, match.group("millis"))

    match = re.search(underscore, name)
    if match:
        value = "".join(
            match.group(part)
            for part in ("year", "month", "day", "hour", "minute", "second")
        )
        return _valid_timestamp(value)

    match = re.search(date_only, name)
    if match:
        try:
            return datetime.strptime(match.group("date"), "%Y-%m-%d").strftime(
                "%Y-%m-%d"
            )
        except ValueError:
            return None
    return None


def embedded_image_timestamp(path: Path) -> str | None:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            value = exif.get(36867) or exif.get(306)
    except (OSError, ValueError, UnidentifiedImageError):
        return None
    if not value:
        return None
    try:
        parsed = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.strftime("%Y-%m-%d_%H-%M-%S")


def collection_slug(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    return slug or "collection"


def clean_descriptor(
    stem: str, collection: str, noise_tokens: frozenset[str]
) -> str | None:
    cleaned = stem
    for pattern in _timestamp_patterns():
        cleaned = re.sub(pattern, " ", cleaned)
    cleaned = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", cleaned.lower())
    collection_tokens = set(collection_slug(collection).split("_"))
    compact_collection = "".join(collection_slug(collection).split("_"))
    result: list[str] = []
    for token in tokens:
        if token.startswith(compact_collection) and len(token) > len(compact_collection):
            token = token[len(compact_collection) :]
        for collection_token in sorted(collection_tokens, key=len, reverse=True):
            if token.startswith(collection_token) and len(token) > len(collection_token) + 2:
                token = token[len(collection_token) :]
                break
        if not token or token in collection_tokens or token in noise_tokens:
            continue
        if re.fullmatch(r"\d+", token) or re.fullmatch(r"\d+x\d+", token):
            continue
        if re.fullmatch(r"(?:360|480|540|720|1080|1440|2160)p", token):
            continue
        if re.fullmatch(r"[0-9a-f]{8,}", token):
            continue
        if any(character.isdigit() for character in token) and any(
            character.isalpha() for character in token
        ):
            continue
        if len(token) < 2:
            continue
        result.append(token)
        if len(result) == 6:
            break
    return "_".join(result) if result else None


def canonical_match(name: str, collection: str) -> re.Match[str] | None:
    return re.match(
        rf"^{re.escape(collection)}__(image|video)_(\d{{4,}})__",
        name,
        flags=re.IGNORECASE,
    )


def build_rename_plan(
    root: Path, classifier: Classifier, config: PymoConfig
) -> tuple[list[RenameRecord], int, list[Path], list[Path]]:
    paths, skipped_links, ignored = discover_files(root, config)
    collection = collection_slug(root.name)
    candidates: dict[str, list[tuple[Path, str | None, str | None]]] = {
        "image": [],
        "video": [],
    }
    next_numbers = {"image": 1, "video": 1}
    already_named = 0
    progress = ProgressMeter(
        len(paths), None, config.performance.progress_interval_seconds
    )

    print(f"Classifying {len(paths)} file(s) in {root}")
    for path in paths:
        kind, _ = classifier.classify(path)
        if kind in {"picture", "video"}:
            output_kind = "image" if kind == "picture" else "video"
            existing = canonical_match(path.stem, collection)
            if existing and existing.group(1).lower() == output_kind:
                next_numbers[output_kind] = max(
                    next_numbers[output_kind], int(existing.group(2)) + 1
                )
                already_named += 1
            else:
                timestamp = (
                    embedded_image_timestamp(path)
                    if output_kind == "image"
                    else None
                ) or timestamp_from_name(path.name)
                descriptor = clean_descriptor(
                    path.stem, collection, config.rename.noise_tokens
                )
                candidates[output_kind].append((path, timestamp, descriptor))
        progress_message = progress.advance("classified")
        if progress_message:
            print(f"  {progress_message}")

    occupied = {path_key(path) for path in paths}
    plan: list[RenameRecord] = []
    for kind in ("image", "video"):
        ordered = sorted(
            candidates[kind],
            key=lambda item: (
                item[1] is None,
                item[1] or "",
                str(item[0]).casefold(),
            ),
        )
        sequence = next_numbers[kind]
        for source, timestamp, descriptor in ordered:
            while True:
                parts = [
                    f"{collection}__{kind}_{sequence:04d}",
                    timestamp or "undated",
                ]
                if descriptor:
                    parts.append(descriptor)
                target = source.with_name("__".join(parts) + source.suffix)
                if path_key(target) not in occupied and not os.path.lexists(target):
                    occupied.add(path_key(target))
                    break
                sequence += 1
            plan.append(
                RenameRecord(
                    source=source,
                    target=target,
                    kind=kind,
                    timestamp=timestamp,
                    descriptor=descriptor,
                )
            )
            sequence += 1

    plan.sort(key=lambda record: str(record.source).casefold())
    return plan, already_named, skipped_links, ignored


def describe_action(root: Path, action: Action, apply: bool) -> None:
    assert action.before and action.after
    verb = "rename" if apply else "would rename"
    print(f"\n{verb}: {root / action.before}\n  to: {root / action.after}")


def undo_renames(root: Path, apply: bool) -> int:
    log = ActionLog(root)
    try:
        plan = log.plan_undo(ToolId.RENAME)
    except NoUndoableRun as error:
        print(str(error), file=sys.stderr)
        return 2
    except (ActionConflict, ActionLogError, OSError) as error:
        print(f"Cannot safely undo renaming: {error}", file=sys.stderr)
        return 1

    print(f"Using action log: {log.path}")
    print(f"Rename run: {plan.target.run_id}")
    for action in plan.actions:
        describe_action(root, action, apply)
    if not apply:
        print(f"\nWould reverse {len(plan.actions)} rename(s).")
        if plan.actions:
            print("Dry run only. Add --apply after reviewing this list.")
        return 0

    try:
        result = log.apply_undo(ToolId.RENAME)
    except (ActionConflict, ActionLogError, OSError) as error:
        print(f"Rename undo failed safely: {error}", file=sys.stderr)
        return 1
    print(f"\nReversed {result.action_count} rename(s).")
    print("Verification passed: every recorded rename was reversed.")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Give media deterministic, readable, reversible names."
    )
    parser.add_argument("folder", type=Path, help="collection directory to rename")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform renames (without this option, the script is a dry run)",
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help=(
            "reverse the newest active rename run in the action log; this is "
            "also a dry run unless --apply is supplied"
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
        return undo_renames(root, args.apply)

    try:
        config = load_config(root, args.config)
    except ConfigError as error:
        print(f"Cannot use configuration: {error}", file=sys.stderr)
        return 2

    classifier = Classifier(config.classification)
    if classifier.warning:
        print(f"Warning: {classifier.warning}")
    plan, already_named, skipped_links, ignored = build_rename_plan(
        root, classifier, config
    )
    for record in plan:
        print(
            f"\n{record.kind.upper()}\n"
            f"  {'rename' if args.apply else 'would rename'}: {record.source}\n"
            f"  to: {record.target}"
        )

    if skipped_links:
        print(f"\nSkipped {len(skipped_links)} symbolic link(s):")
        for path in skipped_links:
            print(f"  {path}")

    messages = ignored_messages(ignored, root, args.show_ignored)
    for number, message in enumerate(messages):
        print(f"\n{message}" if number == 0 else message)

    if not args.apply:
        print(f"\nWould rename {len(plan)} media file(s).")
        print(f"Already using this naming scheme: {already_named} file(s).")
        if plan:
            print("Dry run only. Add --apply after reviewing this list.")
        return 0

    if not plan:
        print("\nRenamed 0 media file(s).")
        print(f"Already using this naming scheme: {already_named} file(s).")
        return 0

    try:
        actions = [
            Action.for_file(root, record.source, record.target, "RENAME")
            for record in plan
        ]
        log = ActionLog(root)
        with log.transaction(ToolId.RENAME) as transaction:
            for action in actions:
                transaction.perform(action)
            transaction.commit()
    except (ActionConflict, ActionLogError, OSError) as error:
        print(f"\nRenaming stopped safely: {error}", file=sys.stderr)
        print(
            "Any completed renames remain recorded and can be inspected with --undo.",
            file=sys.stderr,
        )
        return 1

    verification_failures = [
        record
        for record in plan
        if os.path.lexists(record.source)
        or record.target.is_symlink()
        or not record.target.is_file()
    ]
    print(f"\nRenamed {len(plan)} media file(s).")
    print(f"Already using this naming scheme: {already_named} file(s).")
    print(f"Action log: {action_log_path(root)}")
    if verification_failures:
        print("\nRename verification needs attention:")
        for record in verification_failures:
            print(f"  {record.source} -> {record.target}")
        return 1
    print("Verification passed: every planned media rename was completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
