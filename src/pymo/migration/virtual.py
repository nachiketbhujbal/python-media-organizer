"""Immutable virtual paths over stable, unchanged collection bytes."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from PIL import Image, UnidentifiedImageError

from pymo.cache.hashes import sha256_descriptor
from pymo.classification import Classifier
from pymo.collection import CollectionLayout
from pymo.config import PymoConfig
from pymo.file_safety import open_stable_file
from pymo.migration.inventory import (
    HashedEntry,
    TreeInventory,
    discover_tree,
    hash_tree,
    revalidate_tree,
)


class PolicyPlanningError(RuntimeError):
    """The complete target-local plan cannot be proven."""


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def inventory(root: Path, config: PymoConfig) -> TreeInventory:
    result = hash_tree(
        discover_tree(root, config),
        config.performance.progress_interval_seconds,
        show_progress=False,
    )
    if not result.evidence_complete or not revalidate_tree(result, config).complete:
        raise PolicyPlanningError("collection evidence is incomplete or changing")
    return result


def namespace_digest(tree: TreeInventory, *, initial: bool = False) -> str:
    """Bind logical paths, original objects and bytes, never predicted ctimes.

    ctime and directory inode are additionally bound at initial review/acceptance;
    renames change ctime and later directories do not exist at planning time.
    """
    files: list[dict[str, Any]] = []
    for entry in tree.files:
        item: dict[str, Any] = {
            "path": entry.path.relative_to(tree.root).as_posix(),
            "size": entry.size,
            "sha256": entry.sha256,
            "device": entry.state.device,
            "inode": entry.state.inode,
            "mtime_ns": entry.state.modified_ns,
        }
        if initial:
            item["ctime_ns"] = entry.state.changed_ns
        files.append(item)
    excluded = []
    for path in tree.ignored:
        state = path.lstat()
        excluded.append(
            [
                path.relative_to(tree.root).as_posix(),
                state.st_dev,
                state.st_ino,
                state.st_mode,
                state.st_size,
                state.st_mtime_ns,
                state.st_ctime_ns,
            ]
        )
    directories: list[Any] = []
    for path in tree.directories:
        relative = path.relative_to(tree.root).as_posix()
        if initial:
            state = path.lstat()
            directories.append([relative, state.st_dev, state.st_ino])
        else:
            directories.append(relative)
    files.sort(key=lambda entry: entry["path"])
    return digest(
        {
            "root": str(tree.root),
            "root_identity": tree.root_identity,
            "files": files,
            "directories": sorted(directories),
            "excluded": sorted(excluded),
        }
    )


@dataclass(frozen=True)
class VirtualCollection:
    physical: TreeInventory
    tree: TreeInventory
    config: PymoConfig
    entries: Mapping[Path, HashedEntry] = field(init=False, repr=False, compare=False)
    occupied: frozenset[str] = field(init=False, repr=False, compare=False)
    occupied_paths: frozenset[Path] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "entries", MappingProxyType({e.path: e for e in self.tree.files})
        )
        object.__setattr__(
            self,
            "occupied_paths",
            frozenset(
                (
                    self.tree.root,
                    *self.tree.directories,
                    *self.tree.ignored,
                    *self.tree.tool_state,
                    *self.entries,
                )
            ),
        )
        object.__setattr__(
            self, "occupied", frozenset(str(p).casefold() for p in self.occupied_paths)
        )

    @property
    def layout(self) -> CollectionLayout:
        return CollectionLayout(self.tree.root)

    @classmethod
    def capture(cls, root: Path, config: PymoConfig) -> VirtualCollection:
        tree = inventory(root, config)
        for path in (
            *tree.directories,
            *tree.ignored,
            *(entry.path for entry in tree.files),
        ):
            if (
                path.parent == root
                and path.name.casefold() in {"pics", "vids", "dups"}
                and path.name != path.name.casefold()
            ):
                raise PolicyPlanningError("noncanonical reserved directory spelling")
        names = [
            p.relative_to(root).as_posix().casefold()
            for p in (*tree.directories, *tree.ignored, *(f.path for f in tree.files))
        ]
        if len(names) != len(set(names)):
            raise PolicyPlanningError("ambiguous case-folded namespace")
        # Discovery protects ignored trees; no file inside them is read.
        if any(
            CollectionLayout(root).dups == p or CollectionLayout(root).dups in p.parents
            for p in tree.ignored
        ):
            raise PolicyPlanningError("ignored review-tree entries cannot be modeled")
        return cls(tree, tree, config)

    def paths(self) -> list[Path]:
        return sorted(
            (
                e.path
                for e in self.tree.files
                if not self.layout.is_in_duplicates(e.path)
            ),
            key=lambda p: str(p).casefold(),
        )

    def entry(self, path: Path) -> HashedEntry:
        try:
            return self.entries[path]
        except KeyError as error:
            raise PolicyPlanningError("virtual source is absent") from error

    def exists(self, path: Path) -> bool:
        occupied = str(path).casefold() in self.occupied
        if occupied and path not in self.occupied_paths:
            raise PolicyPlanningError(
                "planned target has ambiguous case-folded occupancy"
            )
        return occupied

    def classify(self, path: Path, classifier: Classifier) -> tuple[str, str]:
        entry = self.entry(path)
        with open_stable_file(
            self.tree.root, entry.read_path, entry.state, "virtual classification"
        ) as fd:
            return classifier.classify(path, fd)

    def timestamp(self, path: Path) -> str | None:
        entry = self.entry(path)
        with open_stable_file(
            self.tree.root, entry.read_path, entry.state, "virtual timestamp"
        ) as fd:
            try:
                with os.fdopen(os.dup(fd), "rb") as handle:
                    with Image.open(handle) as image:
                        exif = image.getexif()
                        value = exif.get(36867) or exif.get(306)
                return (
                    datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S").strftime(
                        "%Y-%m-%d_%H-%M-%S"
                    )
                    if value
                    else None
                )
            except (OSError, ValueError, UnidentifiedImageError):
                return None

    def move(
        self,
        pairs: list[tuple[Path, Path]],
        *,
        create: tuple[Path, ...] = (),
        remove: tuple[Path, ...] = (),
    ) -> VirtualCollection:
        entries = {entry.path: entry for entry in self.tree.files}
        directories = set(self.tree.directories)
        occupied = {
            str(p).casefold()
            for p in (*entries, *directories, *self.tree.ignored, *self.tree.tool_state)
        }
        for path in create:
            if str(path).casefold() in occupied:
                raise PolicyPlanningError("planned directory is occupied")
            if path.parent != self.tree.root and path.parent not in directories:
                raise PolicyPlanningError("planned directory parent is absent")
            directories.add(path)
            occupied.add(str(path).casefold())
        for source, target in pairs:
            if str(
                target
            ).casefold() in occupied or target.parent not in directories | {
                self.tree.root
            }:
                raise PolicyPlanningError("planned target is occupied or unsafe")
            if self.config.ignores_file(target, self.tree.root):
                raise PolicyPlanningError(
                    "planned target would leave the declared scope"
                )
            entry = entries.pop(source)
            entries[target] = replace(entry, path=target, source_path=entry.read_path)
            occupied.remove(str(source).casefold())
            occupied.add(str(target).casefold())
        for path in remove:
            # Organizer retains directories containing protected entries.
            if not any(
                path in p.parents
                for p in (*entries, *directories - {path}, *self.tree.ignored)
            ):
                directories.remove(path)
        return replace(
            self,
            tree=replace(
                self.tree,
                files=tuple(
                    sorted(entries.values(), key=lambda e: str(e.path).casefold())
                ),
                directories=tuple(sorted(directories, key=lambda p: str(p).casefold())),
            ),
        )

    def require_current(self) -> None:
        if not revalidate_tree(self.physical, self.config).complete:
            raise PolicyPlanningError("collection changed during planning")
        for entry in self.physical.files:
            with open_stable_file(
                self.tree.root, entry.path, entry.state, "policy final byte check"
            ) as fd:
                if sha256_descriptor(fd) != entry.sha256:
                    raise PolicyPlanningError(
                        "collection bytes changed during planning"
                    )
