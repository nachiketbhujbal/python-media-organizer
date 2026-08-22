"""Shared filesystem policy for exact-media duplicate commands."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pymo.action_log import Action
from pymo.collection import CollectionLayout
from pymo.config import PymoConfig
from pymo.discovery import DiscoveryError, list_directory_complete
from pymo.logging_config import emit as print
from pymo.organize import Classifier


@dataclass(frozen=True)
class DuplicateLayout:
    source: Path
    review_root: Path
    destination: Path


def duplicate_layout(
    root: Path, media_kind: Literal["picture", "video"]
) -> DuplicateLayout:
    layout = CollectionLayout(root)
    if media_kind == "picture":
        return DuplicateLayout(layout.pics, layout.dups, layout.duplicate_pics)
    return DuplicateLayout(layout.vids, layout.dups, layout.duplicate_vids)


def layout_problems(
    root: Path,
    config: PymoConfig,
    media_kind: Literal["picture", "video"],
) -> list[str]:
    """Validate only one duplicate finder's source and review locations."""
    layout = duplicate_layout(root, media_kind)
    problems: list[str] = []
    if layout.source.is_symlink():
        problems.append(f"required folder is a symbolic link: {layout.source}")
    elif not layout.source.exists():
        problems.append(f"missing required folder: {layout.source}")
    elif not layout.source.is_dir():
        problems.append(f"required folder is not a directory: {layout.source}")

    if layout.review_root.is_symlink():
        problems.append(f"reserved folder is a symbolic link: {layout.review_root}")
    elif layout.review_root.exists() and not layout.review_root.is_dir():
        problems.append(f"reserved path is not a directory: {layout.review_root}")
    elif layout.review_root.is_dir():
        if layout.destination.is_symlink():
            problems.append(
                f"reserved media path is a symbolic link: {layout.destination}"
            )
        elif layout.destination.exists() and not layout.destination.is_dir():
            problems.append(
                f"reserved media path is not a directory: {layout.destination}"
            )

    if problems:
        return problems

    classifier = Classifier(config.classification)
    wrong_kind = "video" if media_kind == "picture" else "picture"
    owner_name = "image" if media_kind == "picture" else "video"
    try:
        source_entries = list_directory_complete(layout.source)
    except DiscoveryError:
        problems.append("required media folder could not be read completely")
        return problems
    for path in source_entries:
        if path.is_symlink():
            problems.append(f"symbolic link cannot be verified: {path}")
        elif path.is_dir():
            if not config.ignores_directory(path, root):
                problems.append(f"unexpected directory in {layout.source.name}: {path}")
        elif path.is_file():
            if config.ignores_file(path, root):
                continue
            kind, _ = classifier.classify(path)
            if kind == wrong_kind:
                problems.append(
                    f"misplaced {wrong_kind}: {path} "
                    f"(expected outside the {owner_name} finder's "
                    f"{layout.source.name} folder)"
                )
    return problems


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
