"""Stable, path-private byte inventory for one media-collection tree."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from pymo.cache.hashes import sha256_descriptor
from pymo.collection import CollectionLayout
from pymo.config import PymoConfig
from pymo.file_safety import FileChangedError, FileState, open_stable_file
from pymo.logging_config import emit as print
from pymo.progress import ProgressMeter


@dataclass(frozen=True)
class InventoryEntry:
    path: Path
    state: FileState

    @property
    def size(self) -> int:
        return self.state.size


@dataclass(frozen=True)
class InventoryIssue:
    path: Path
    category: str


@dataclass(frozen=True)
class TreeDiscovery:
    root: Path
    root_identity: tuple[int, int]
    entries: tuple[InventoryEntry, ...]
    directories: tuple[Path, ...]
    ignored: tuple[Path, ...]
    tool_state: tuple[Path, ...]
    symbolic_links: tuple[Path, ...]
    non_regular: tuple[Path, ...]
    unreadable: tuple[InventoryIssue, ...]
    changed: tuple[InventoryIssue, ...]
    traversal_errors: int


@dataclass(frozen=True)
class HashedEntry:
    path: Path
    size: int
    sha256: str
    state: FileState

    @property
    def identity(self) -> tuple[int, str]:
        return (self.size, self.sha256)


@dataclass(frozen=True)
class TreeInventory:
    root: Path
    root_identity: tuple[int, int]
    files: tuple[HashedEntry, ...]
    directories: tuple[Path, ...]
    ignored: tuple[Path, ...]
    tool_state: tuple[Path, ...]
    symbolic_links: tuple[Path, ...]
    non_regular: tuple[Path, ...]
    unreadable: tuple[InventoryIssue, ...]
    changed: tuple[InventoryIssue, ...]
    traversal_errors: int
    root_changed: bool

    @property
    def evidence_complete(self) -> bool:
        return not any(
            (
                self.symbolic_links,
                self.non_regular,
                self.unreadable,
                self.changed,
                self.traversal_errors,
                self.root_changed,
            )
        )


def _path_key(path: Path) -> str:
    return str(path).casefold()


def _entry_key(entry: InventoryEntry) -> str:
    return _path_key(entry.path)


def _issue_key(issue: InventoryIssue) -> str:
    return _path_key(issue.path)


def _root_identity(root: Path) -> tuple[int, int]:
    value = os.stat(root, follow_symlinks=False)
    if not stat.S_ISDIR(value.st_mode):
        raise NotADirectoryError("media-collection root is not a directory")
    return (value.st_dev, value.st_ino)


def _is_tool_state(root: Path, path: Path) -> bool:
    layout = CollectionLayout(root)
    if path in {
        layout.config,
        layout.derived_cache,
        layout.derived_cache_lock,
        layout.action_log,
    }:
        return True
    return path.parent == root and path.name.startswith(".pymo.sqlite3")


def discover_tree(root: Path, config: PymoConfig) -> TreeDiscovery:
    """Enumerate one tree without following links or hiding entry failures."""

    entries: list[InventoryEntry] = []
    ignored: list[Path] = []
    tool_state: list[Path] = []
    symbolic_links: list[Path] = []
    non_regular: list[Path] = []
    unreadable: list[InventoryIssue] = []
    changed: list[InventoryIssue] = []
    directories: list[Path] = []
    walk_errors: list[OSError] = []
    identity = _root_identity(root)

    for current, directory_names, file_names in os.walk(
        root, topdown=True, onerror=walk_errors.append
    ):
        current_path = Path(current)
        directory_names.sort(key=str.casefold)
        file_names.sort(key=str.casefold)
        retained_directories: list[str] = []
        for name in directory_names:
            path = current_path / name
            try:
                mode = os.lstat(path).st_mode
            except OSError:
                unreadable.append(InventoryIssue(path, "unreadable-directory-entry"))
                continue
            if stat.S_ISLNK(mode):
                symbolic_links.append(path)
            elif not stat.S_ISDIR(mode):
                changed.append(InventoryIssue(path, "changed-directory-entry"))
            elif config.ignores_directory(path, root):
                ignored.append(path)
            else:
                retained_directories.append(name)
                directories.append(path)
        directory_names[:] = retained_directories

        for name in file_names:
            path = current_path / name
            try:
                mode = os.lstat(path).st_mode
            except OSError:
                unreadable.append(InventoryIssue(path, "unreadable-file-entry"))
                continue
            if stat.S_ISLNK(mode):
                symbolic_links.append(path)
                continue
            if stat.S_ISDIR(mode):
                changed.append(InventoryIssue(path, "changed-file-entry"))
                continue
            if not stat.S_ISREG(mode):
                non_regular.append(path)
                continue
            if _is_tool_state(root, path):
                tool_state.append(path)
                continue
            if config.ignores_file(path, root):
                ignored.append(path)
                continue
            try:
                state = FileState.capture(path)
            except FileChangedError:
                unreadable.append(InventoryIssue(path, "unreadable-file-state"))
                continue
            entries.append(InventoryEntry(path, state))

    return TreeDiscovery(
        root=root,
        root_identity=identity,
        entries=tuple(sorted(entries, key=_entry_key)),
        directories=tuple(sorted(directories, key=_path_key)),
        ignored=tuple(sorted(ignored, key=_path_key)),
        tool_state=tuple(sorted(tool_state, key=_path_key)),
        symbolic_links=tuple(sorted(symbolic_links, key=_path_key)),
        non_regular=tuple(sorted(non_regular, key=_path_key)),
        unreadable=tuple(sorted(unreadable, key=_issue_key)),
        changed=tuple(sorted(changed, key=_issue_key)),
        traversal_errors=len(walk_errors),
    )


def hash_tree(
    discovery: TreeDiscovery,
    progress_interval_seconds: int,
    *,
    show_progress: bool,
) -> TreeInventory:
    """Hash every discovered file from a stable descriptor and retain failures."""

    files: list[HashedEntry] = []
    unreadable = list(discovery.unreadable)
    changed = list(discovery.changed)
    progress = ProgressMeter(
        len(discovery.entries),
        sum(entry.size for entry in discovery.entries),
        progress_interval_seconds,
    )
    for entry in discovery.entries:
        hashed_bytes = 0
        try:
            with open_stable_file(
                discovery.root,
                entry.path,
                entry.state,
                "migration byte inventory",
            ) as descriptor:
                digest = sha256_descriptor(descriptor)
        except FileChangedError:
            changed.append(InventoryIssue(entry.path, "changed-during-hash"))
        except OSError:
            unreadable.append(InventoryIssue(entry.path, "unreadable-during-hash"))
        else:
            files.append(HashedEntry(entry.path, entry.size, digest, entry.state))
            hashed_bytes = entry.size
        message = progress.advance("hashed", byte_count=hashed_bytes)
        if show_progress and message:
            print(f"  {message}")

    try:
        root_changed = _root_identity(discovery.root) != discovery.root_identity
    except OSError:
        root_changed = True
    return TreeInventory(
        root=discovery.root,
        root_identity=discovery.root_identity,
        files=tuple(files),
        directories=discovery.directories,
        ignored=discovery.ignored,
        tool_state=discovery.tool_state,
        symbolic_links=discovery.symbolic_links,
        non_regular=discovery.non_regular,
        unreadable=tuple(sorted(unreadable, key=_issue_key)),
        changed=tuple(sorted(changed, key=_issue_key)),
        traversal_errors=discovery.traversal_errors,
        root_changed=root_changed,
    )


@dataclass(frozen=True)
class StabilityEvidence:
    changed: tuple[InventoryIssue, ...]
    root_changed: bool
    traversal_errors: int
    ignored_entry_points: int
    tool_state_entries: int

    @property
    def complete(self) -> bool:
        return not self.changed and not self.root_changed and not self.traversal_errors


def revalidate_tree(inventory: TreeInventory, config: PymoConfig) -> StabilityEvidence:
    """Require the declared namespace and every hashed path to remain unchanged."""

    changed: list[InventoryIssue] = []
    try:
        current = discover_tree(inventory.root, config)
    except OSError:
        return StabilityEvidence(
            changed=(),
            root_changed=True,
            traversal_errors=1,
            ignored_entry_points=len(inventory.ignored),
            tool_state_entries=len(inventory.tool_state),
        )
    original_files = {entry.path: entry for entry in inventory.files}
    current_files = {entry.path: entry for entry in current.entries}
    for path in sorted(set(original_files) | set(current_files), key=_path_key):
        original = original_files.get(path)
        refreshed = current_files.get(path)
        if original is None:
            changed.append(InventoryIssue(path, "appeared-after-analysis"))
        elif refreshed is None:
            changed.append(InventoryIssue(path, "missing-after-analysis"))
        elif original.state != refreshed.state:
            changed.append(InventoryIssue(path, "changed-after-analysis"))

    original_categories = {
        **{path: "symbolic-link" for path in inventory.symbolic_links},
        **{path: "non-regular" for path in inventory.non_regular},
        **{issue.path: issue.category for issue in inventory.unreadable},
        **{issue.path: issue.category for issue in inventory.changed},
    }
    current_categories = {
        **{path: "symbolic-link" for path in current.symbolic_links},
        **{path: "non-regular" for path in current.non_regular},
        **{issue.path: issue.category for issue in current.unreadable},
        **{issue.path: issue.category for issue in current.changed},
    }
    for path in sorted(
        {
            path
            for path in set(original_categories) | set(current_categories)
            if original_categories.get(path) != current_categories.get(path)
        },
        key=_path_key,
    ):
        changed.append(InventoryIssue(path, "entry-category-changed-after-analysis"))

    for path in sorted(
        set(inventory.directories) ^ set(current.directories), key=_path_key
    ):
        changed.append(
            InventoryIssue(path, "directory-namespace-changed-after-analysis")
        )

    for entry in inventory.files:
        if entry.path not in current_files:
            continue
        try:
            with open_stable_file(
                inventory.root,
                entry.path,
                entry.state,
                "migration final stability check",
            ):
                pass
        except (FileChangedError, OSError):
            changed.append(InventoryIssue(entry.path, "changed-after-analysis"))
    try:
        root_changed = _root_identity(inventory.root) != inventory.root_identity
    except OSError:
        root_changed = True
    return StabilityEvidence(
        changed=tuple(
            sorted(
                {(issue.path, issue.category): issue for issue in changed}.values(),
                key=lambda issue: (_issue_key(issue), issue.category),
            )
        ),
        root_changed=root_changed,
        traversal_errors=current.traversal_errors,
        ignored_entry_points=len(current.ignored),
        tool_state_entries=len(current.tool_state),
    )
