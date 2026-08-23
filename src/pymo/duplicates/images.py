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
import warnings
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
from pymo.cache.hashes import HashCacheError, load_cached_hashes, sha256_descriptor
from pymo.cache.images import (
    ImageCacheError,
    load_cached_pixel_hashes,
    publish_image_analysis_batch,
)
from pymo.cache.paths import CachePathError, writable_cache_path
from pymo.config import (
    ConfigError,
    PymoConfig,
    add_config_argument,
    add_show_ignored_argument,
    ignored_messages,
    load_config,
)
from pymo.discovery import (
    DiscoveryError,
    entry_kind_complete,
    list_directory_complete,
)
from pymo.duplicates.common import (
    copy_target,
    describe_undo_action,
    duplicate_layout,
    layout_problems,
)
from pymo.file_safety import FileChangedError, FileState, open_stable_file
from pymo.logging_config import emit as print
from pymo.progress import ProgressMeter, format_bytes

try:
    from PIL import Image, ImageOps, UnidentifiedImageError, __version__
except ImportError as error:
    print(
        "This script needs Pillow. Install it with:\n"
        "  python3 -m pip install Pillow",
        file=sys.stderr,
    )
    raise SystemExit(2) from error


@dataclass(frozen=True)
class ImageRecord:
    path: Path
    byte_sha256: str
    pixel_hash: str
    state: FileState
    byte_sha256_cached: bool = False
    pixel_hash_cached: bool = False

    @property
    def file_size(self) -> int:
        return self.state.size

    @property
    def modified_ns(self) -> int:
        return self.state.modified_ns


ImageMove = tuple[str, ImageRecord, ImageRecord, Path]


def displayed_pixel_hash(descriptor: int) -> str:
    """Hash the pixels as displayed, after applying EXIF orientation.

    RGBA conversion makes equivalent RGB/palette/grayscale still images
    comparable. Animated images are skipped because comparing only their first
    frame could incorrectly classify two different animations as duplicates.
    """
    os.lseek(descriptor, 0, os.SEEK_SET)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            with Image.open(stream) as opened:
                if getattr(opened, "n_frames", 1) != 1:
                    raise ValueError("animated or multi-page image")

                image = ImageOps.exif_transpose(opened)
                rgba = image.convert("RGBA")

                digest = hashlib.sha256()
                digest.update(rgba.width.to_bytes(8, "big"))
                digest.update(rgba.height.to_bytes(8, "big"))
                digest.update(rgba.tobytes())
                return digest.hexdigest()


class ImageAnalysisCacheError(RuntimeError):
    """Image analysis cache state cannot be used safely."""


def inspect_image(
    root: Path,
    path: Path,
    *,
    state: FileState | None = None,
    cached_sha256: str | None = None,
    cached_pixels: dict[str, str] | None = None,
) -> ImageRecord:
    state = state or FileState.capture(path)
    with open_stable_file(root, path, state, "image analysis") as descriptor:
        byte_sha256 = cached_sha256 or sha256_descriptor(descriptor)
        cached_pixel_hash = (cached_pixels or {}).get(byte_sha256)
        pixel_hash = cached_pixel_hash or displayed_pixel_hash(descriptor)
    return ImageRecord(
        path=path,
        byte_sha256=byte_sha256,
        pixel_hash=pixel_hash,
        state=state,
        byte_sha256_cached=cached_sha256 is not None,
        pixel_hash_cached=cached_pixel_hash is not None,
    )


def require_current_image(record: ImageRecord) -> None:
    record.state.require_unchanged(record.path, "duplicate apply preflight")


def recheck_cached_image_hashes(root: Path, records: list[ImageRecord]) -> None:
    """Re-read cached byte identities before permitting any image move."""

    for record in records:
        if not record.byte_sha256_cached:
            continue
        with open_stable_file(
            root, record.path, record.state, "cached image hash recheck"
        ) as descriptor:
            if sha256_descriptor(descriptor) != record.byte_sha256:
                raise FileChangedError(
                    "file content changed during cached image hash recheck: "
                    f"{record.path}"
                )


def discover_images(
    pics: Path, root: Path, config: PymoConfig
) -> tuple[list[Path], list[Path]]:
    result: list[Path] = []
    ignored: list[Path] = []
    for path in list_directory_complete(pics):
        entry_kind = entry_kind_complete(path)
        if entry_kind == "symlink":
            continue
        if entry_kind == "directory":
            if config.ignores_directory(path, root):
                ignored.append(path)
            continue
        if entry_kind == "file" and config.ignores_file(path, root):
            ignored.append(path)
            continue
        if (
            entry_kind != "file"
            or path.suffix.lower() not in config.image_duplicates.extensions
        ):
            continue
        result.append(path.absolute())
    return (
        sorted(result, key=lambda item: str(item).casefold()),
        sorted(ignored, key=lambda item: str(item).casefold()),
    )


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
        f"{format_bytes(retained_bytes)}"
    )
    print(
        f"  Extra duplicate copies: {duplicate_count} file(s), "
        f"{format_bytes(duplicate_bytes)}"
    )
    print(f"  Duplicate sets combined: {format_bytes(duplicate_set_bytes)}")
    print(
        "  Potentially reclaimable if extra copies were deleted: "
        f"{format_bytes(duplicate_bytes)} ({set_percentage:.1f}% of duplicate-set "
        f"storage; {scan_percentage:.1f}% of scanned picture storage)"
    )
    print("  No files are deleted by this tool.")


def undo_duplicate_run(root: Path, apply: bool, *, summary: bool = False) -> int:
    log = ActionLog(root)
    try:
        plan = log.plan_undo(ToolId.IMAGE_DUPLICATES)
    except NoUndoableRun as error:
        detail = "No undoable image duplicate run found." if summary else str(error)
        print(detail, file=sys.stderr)
        return 2
    except (ActionConflict, ActionLogError, OSError) as error:
        detail = "rerun without --summary for details" if summary else str(error)
        print(f"Cannot safely undo duplicate moves: {detail}", file=sys.stderr)
        return 1

    if not summary:
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
        detail = "rerun without --summary for details" if summary else str(error)
        print(f"Duplicate undo failed safely: {detail}", file=sys.stderr)
        return 1
    print(f"\nReversed {result.action_count} recorded action(s).")
    print("Verification passed: every recorded duplicate-file action was reversed.")
    return 0


def keep_sort_key(record: ImageRecord) -> tuple[int, int, str]:
    # Prefer the largest file because it may retain more metadata. Then prefer
    # the older file, followed by a stable filename ordering.
    return (-record.file_size, record.modified_ns, str(record.path).casefold())


def inspect_image_paths(
    root: Path,
    paths: list[Path],
    progress_interval_seconds: int,
    database: Path | None,
    publication_batch_size: int,
    pillow_runtime: str,
    *,
    reuse_evidence: bool = True,
) -> tuple[list[ImageRecord], int, list[tuple[Path, str]]]:
    scanned_bytes = 0
    skipped: list[tuple[Path, str]] = []
    states: dict[Path, FileState] = {}
    for path in paths:
        try:
            states[path] = FileState.capture(path)
        except FileChangedError as error:
            skipped.append((path, str(error)))
    try:
        cached_hashes = (
            {}
            if database is None or not reuse_evidence
            else load_cached_hashes(root, database, states, coordinated=True)
        )
        cached_pixels = (
            {}
            if database is None or not reuse_evidence
            else load_cached_pixel_hashes(database, pillow_runtime)
        )
    except (HashCacheError, ImageCacheError) as error:
        raise ImageAnalysisCacheError(
            "Image fingerprint cache cannot be used safely: "
            f"{error}\nThe cache is disposable; move it aside or rerun with --no-cache."
        ) from error
    if database is None:
        print("Image fingerprint cache disabled: no records read or written.")
    else:
        print(
            f"Whole-file hash cache {'lookup' if reuse_evidence else 'refresh'}: "
            f"{len(cached_hashes)} reusable record(s); "
            f"{len(states) - len(cached_hashes)} hash(es) required."
        )
        print(
            f"Displayed-pixel cache {'lookup' if reuse_evidence else 'refresh'}: "
            f"{len(cached_pixels)} compatible record(s) available."
        )
    progress = ProgressMeter(
        len(states),
        sum(state.size for state in states.values()),
        progress_interval_seconds,
    )
    pending_hashes: list[tuple[Path, FileState, str]] = []
    pending_pixels: dict[str, str] = {}
    available_pixels = dict(cached_pixels)
    hashes_persisted = 0
    pixels_persisted: set[str] = set()
    analyzed: list[ImageRecord] = []

    def publish_pending() -> None:
        nonlocal hashes_persisted
        if database is None or (not pending_hashes and not pending_pixels):
            return
        publish_image_analysis_batch(
            root,
            database,
            pillow_runtime,
            pending_hashes,
            pending_pixels,
        )
        hashes_persisted += len(pending_hashes)
        pixels_persisted.update(pending_pixels)
        pending_hashes.clear()
        pending_pixels.clear()

    for path, state in states.items():
        try:
            record = inspect_image(
                root,
                path,
                state=state,
                cached_sha256=cached_hashes.get(path),
                cached_pixels=available_pixels,
            )
            analyzed.append(record)
            # A complete byte hash is a sufficient key for reusing a pixel
            # fingerprint computed earlier in this same run. This avoids
            # decoding byte-identical copies before their bounded batch is
            # published.
            available_pixels.setdefault(record.byte_sha256, record.pixel_hash)
            scanned_bytes += record.file_size
            if database is not None and (
                not record.byte_sha256_cached or not record.pixel_hash_cached
            ):
                if not record.byte_sha256_cached:
                    pending_hashes.append(
                        (record.path, record.state, record.byte_sha256)
                    )
                if not record.pixel_hash_cached:
                    pending_pixels[record.byte_sha256] = record.pixel_hash
                if (
                    max(len(pending_hashes), len(pending_pixels))
                    >= publication_batch_size
                ):
                    publish_pending()
        except (
            FileChangedError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            OSError,
            UnidentifiedImageError,
            ValueError,
        ) as error:
            skipped.append((path, str(error)))
        except (HashCacheError, ImageCacheError) as error:
            raise ImageAnalysisCacheError(
                f"Image fingerprint cache update failed safely: {error}"
            ) from error
        progress_message = progress.advance("processed", byte_count=state.size)
        if progress_message:
            print(f"  {progress_message}")

    try:
        publish_pending()
    except (HashCacheError, ImageCacheError) as error:
        raise ImageAnalysisCacheError(
            f"Image fingerprint cache update failed safely: {error}"
        ) from error
    if database is not None:
        publication_label = "new" if reuse_evidence else "refreshed"
        print(
            f"Whole-file hash cache update: {hashes_persisted} "
            f"{publication_label} record(s) persisted."
        )
        print(
            "Displayed-pixel cache use: "
            f"{sum(record.pixel_hash_cached for record in analyzed)} reused; "
            f"{sum(not record.pixel_hash_cached for record in analyzed)} computed; "
            f"{len(pixels_persisted)} {publication_label} record(s) persisted."
        )

    return analyzed, scanned_bytes, skipped


def group_image_duplicates(records: list[ImageRecord]) -> list[list[ImageRecord]]:
    """Group inspected images by exact displayed pixels."""

    groups: dict[str, list[ImageRecord]] = defaultdict(list)
    for record in records:
        groups[record.pixel_hash].append(record)
    duplicate_groups = [items for items in groups.values() if len(items) > 1]
    duplicate_groups.sort(key=lambda items: str(min(r.path for r in items)).casefold())
    return duplicate_groups


def analyze_images(
    root: Path,
    paths: list[Path],
    progress_interval_seconds: int,
    database: Path | None,
    publication_batch_size: int,
    pillow_runtime: str,
) -> tuple[list[list[ImageRecord]], int, list[tuple[Path, str]]]:
    records, scanned_bytes, skipped = inspect_image_paths(
        root,
        paths,
        progress_interval_seconds,
        database,
        publication_batch_size,
        pillow_runtime,
    )
    return group_image_duplicates(records), scanned_bytes, skipped


def plan_image_moves(
    duplicate_groups: list[list[ImageRecord]],
    destination: Path,
    apply: bool,
    *,
    summary: bool = False,
) -> list[ImageMove]:
    move_plan: list[ImageMove] = []
    reserved_targets: set[str] = set()
    for group_number, records in enumerate(duplicate_groups, start=1):
        ordered = sorted(records, key=keep_sort_key)
        kept = ordered[0]
        group_name = f"set_{group_number:04d}"
        if not summary:
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
            if not summary:
                print(f"  duplicate: {duplicate.path}")
                print(f"  {'move to' if apply else 'would move to'}: {target}")
    return move_plan


def apply_image_moves(
    root: Path,
    duplicate_groups: list[list[ImageRecord]],
    move_plan: list[ImageMove],
) -> Path:
    layout = duplicate_layout(root, "picture")
    current_records = {
        record.path: record for records in duplicate_groups for record in records
    }
    recheck_cached_image_hashes(root, list(current_records.values()))
    keepers = {kept.path: kept for _, kept, _, _ in move_plan}
    for record in current_records.values():
        require_current_image(record)
    actions: list[Action] = []
    for _, _, duplicate, target in move_plan:
        action = Action.for_file(root, duplicate.path, target, "MOVE")
        require_current_image(duplicate)
        actions.append(action)
    for record in current_records.values():
        require_current_image(record)

    log = ActionLog(root)
    with log.transaction(ToolId.IMAGE_DUPLICATES) as transaction:
        for record in current_records.values():
            require_current_image(record)
        for directory in (layout.review_root, layout.destination):
            if not directory.exists():
                transaction.perform(Action.create_directory(root, directory))
        for action, (_, kept, _, _) in zip(actions, move_plan, strict=True):
            require_current_image(kept)
            transaction.perform(action)
        for record in keepers.values():
            require_current_image(record)
        transaction.commit()
    return log.path


def verify_image_moves(move_plan: list[ImageMove]) -> list[tuple[Path, Path]]:
    return [
        (duplicate.path, target)
        for _, _, duplicate, target in move_plan
        if os.path.lexists(duplicate.path)
        or target.is_symlink()
        or not target.is_file()
    ]


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
    parser.add_argument(
        "--summary",
        action="store_true",
        help="show aggregate path-private results without file or group details",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        help=(
            "read and update this cache file instead of the collection-local "
            "default; its parent directory must already exist"
        ),
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="do not read or write hash or displayed-pixel cache records",
    )
    add_config_argument(parser)
    add_show_ignored_argument(parser)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        message = "supplied collection path" if args.summary else str(root)
        print(f"Not a directory: {message}", file=sys.stderr)
        return 2
    if args.summary and args.show_ignored:
        print(
            "--summary cannot be combined with --show-ignored because summary "
            "output is path-private",
            file=sys.stderr,
        )
        return 2
    if args.no_cache and args.cache is not None:
        print("--no-cache cannot be combined with --cache", file=sys.stderr)
        return 2
    if args.undo:
        return undo_duplicate_run(root, args.apply, summary=args.summary)

    try:
        config = load_config(root, args.config)
        database = writable_cache_path(root, args.cache)
    except (CachePathError, ConfigError) as error:
        detail = "rerun without --summary for details" if args.summary else str(error)
        print(f"Cannot use configuration: {detail}", file=sys.stderr)
        return 2

    layout = duplicate_layout(root, "picture")
    destination = layout.destination

    problems = layout_problems(root, config, "picture")
    if problems:
        print("Collection is not ready for duplicate scanning:", file=sys.stderr)
        if args.summary:
            print(f"  {len(problems)} layout problem(s).", file=sys.stderr)
            print(
                "Run pymo organize COLLECTION first so pictures are directly in pics.",
                file=sys.stderr,
            )
        else:
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            print(
                f'Run pymo organize "{root}" first so pictures are directly in pics.',
                file=sys.stderr,
            )
        return 2

    pics = layout.source
    try:
        paths, ignored = discover_images(pics, root, config)
    except DiscoveryError as error:
        detail = "rerun without --summary for details" if args.summary else str(error)
        print(f"Image discovery stopped safely: {detail}", file=sys.stderr)
        return 1
    location = "" if args.summary else f" in {pics}"
    print(f"Scanning {len(paths)} image(s){location}")
    for message in ignored_messages(ignored, root, args.show_ignored):
        print(message)

    if not paths:
        print("No image content required duplicate analysis.")
        verb = "Moved" if args.apply else "Would move"
        print(f"\n{verb} 0 duplicate(s) from 0 group(s).")
        print_storage_summary([], 0)
        return 0

    try:
        duplicate_groups, scanned_bytes, skipped = analyze_images(
            root,
            paths,
            config.performance.progress_interval_seconds,
            None if args.no_cache else database,
            config.performance.cache_publication_batch_size,
            f"Pillow {__version__}",
        )
    except ImageAnalysisCacheError as error:
        detail = (
            "Image fingerprint cache cannot be used safely; rerun without "
            "--summary for details."
            if args.summary
            else str(error)
        )
        print(detail, file=sys.stderr)
        return 1
    move_plan = plan_image_moves(
        duplicate_groups, destination, args.apply, summary=args.summary
    )

    if args.apply and move_plan:
        try:
            log_path = apply_image_moves(root, duplicate_groups, move_plan)
            print(
                "\nAction log updated." if args.summary else f"\nAction log: {log_path}"
            )
        except (ActionConflict, ActionLogError, FileChangedError, OSError) as error:
            detail = (
                "rerun without --summary for details" if args.summary else str(error)
            )
            print(f"Duplicate moves stopped safely: {detail}", file=sys.stderr)
            return 1

        verification_failures = verify_image_moves(move_plan)
        if verification_failures:
            print("\nVerification needs attention:", file=sys.stderr)
            if args.summary:
                print(
                    f"  {len(verification_failures)} move(s) failed verification.",
                    file=sys.stderr,
                )
            else:
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
        suffix = "." if args.summary else ":"
        print(f"\nSkipped {len(skipped)} file(s){suffix}")
        if not args.summary:
            for path, reason in skipped:
                print(f"  {path}: {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
