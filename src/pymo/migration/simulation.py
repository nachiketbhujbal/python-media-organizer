"""Counterfactual destination evidence without the duplicate review tree."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, replace
from pathlib import Path

from pymo.collection import CollectionLayout
from pymo.migration.inventory import HashedEntry, InventoryIssue, TreeInventory


@dataclass(frozen=True)
class ReviewTreeInventory:
    root: Path
    present: bool
    files: tuple[HashedEntry, ...]
    directories: tuple[Path, ...]
    ignored: tuple[Path, ...]
    tool_state: tuple[Path, ...]
    symbolic_links: tuple[Path, ...]
    non_regular: tuple[Path, ...]
    unreadable: tuple[InventoryIssue, ...]
    changed: tuple[InventoryIssue, ...]


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _review_paths(paths: tuple[Path, ...], root: Path) -> tuple[Path, ...]:
    return tuple(path for path in paths if _within(path, root))


def _review_issues(
    issues: tuple[InventoryIssue, ...], root: Path
) -> tuple[InventoryIssue, ...]:
    return tuple(issue for issue in issues if _within(issue.path, root))


def _directory_identity(path: Path) -> tuple[int, int] | None:
    try:
        value = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    if not stat.S_ISDIR(value.st_mode):
        return None
    return (value.st_dev, value.st_ino)


def _resolved_review_root(inventory: TreeInventory) -> Path:
    """Return the discovered spelling of the canonical review directory."""

    canonical = CollectionLayout(inventory.root).dups
    identity = _directory_identity(canonical)
    if identity is None:
        return canonical
    recorded_paths = (
        inventory.directories
        + inventory.ignored
        + inventory.symbolic_links
        + inventory.non_regular
        + tuple(issue.path for issue in inventory.unreadable)
        + tuple(issue.path for issue in inventory.changed)
    )
    for path in recorded_paths:
        if path.parent == inventory.root and _directory_identity(path) == identity:
            return path
    return canonical


def without_duplicate_review_tree(
    inventory: TreeInventory,
) -> tuple[TreeInventory, ReviewTreeInventory]:
    """Return comparison evidence excluding ``dups`` plus its physical inventory."""

    review_root = _resolved_review_root(inventory)
    review_directory_present = review_root in inventory.directories
    review_files = tuple(
        entry
        for entry in inventory.files
        if review_directory_present and review_root in entry.path.parents
    )
    review_directories = _review_paths(inventory.directories, review_root)
    review_ignored = _review_paths(inventory.ignored, review_root)
    review_tool_state = _review_paths(inventory.tool_state, review_root)
    review_symbolic_links = _review_paths(inventory.symbolic_links, review_root)
    review_non_regular = _review_paths(inventory.non_regular, review_root)
    review_unreadable = _review_issues(inventory.unreadable, review_root)
    review_changed = _review_issues(inventory.changed, review_root)
    review = ReviewTreeInventory(
        root=review_root,
        present=bool(
            review_files
            or review_directories
            or review_ignored
            or review_tool_state
            or review_symbolic_links
            or review_non_regular
            or review_unreadable
            or review_changed
        ),
        files=review_files,
        directories=review_directories,
        ignored=review_ignored,
        tool_state=review_tool_state,
        symbolic_links=review_symbolic_links,
        non_regular=review_non_regular,
        unreadable=review_unreadable,
        changed=review_changed,
    )
    comparison = replace(
        inventory,
        files=tuple(
            entry
            for entry in inventory.files
            if not (review_directory_present and review_root in entry.path.parents)
        ),
        directories=tuple(
            path for path in inventory.directories if not _within(path, review_root)
        ),
    )
    return comparison, review
