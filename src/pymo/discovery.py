"""Fail-closed filesystem enumeration for complete plans and verification."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

EntryKind = Literal["symlink", "directory", "file", "other"]


class DiscoveryError(OSError):
    """A filesystem namespace could not be enumerated completely."""


def _error_message(count: int) -> str:
    noun = "location" if count == 1 else "locations"
    return f"filesystem discovery was incomplete: {count} {noun} could not be read"


def walk_complete(
    root: Path, *, topdown: bool = True
) -> Iterator[tuple[str, list[str], list[str]]]:
    """Yield an ``os.walk`` traversal and fail after any traversal error."""
    errors: list[OSError] = []
    yield from os.walk(root, topdown=topdown, onerror=errors.append)
    if errors:
        raise DiscoveryError(_error_message(len(errors))) from errors[0]


def list_directory_complete(directory: Path) -> tuple[Path, ...]:
    """Return every immediate entry or fail without supplying a partial list."""
    try:
        with os.scandir(directory) as entries:
            return tuple(directory / entry.name for entry in entries)
    except OSError as error:
        raise DiscoveryError(_error_message(1)) from error


def entry_kind_complete(path: Path) -> EntryKind:
    """Classify one enumerated entry or fail when it cannot be inspected."""
    try:
        mode = os.lstat(path).st_mode
    except OSError as error:
        raise DiscoveryError(_error_message(1)) from error
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    return "other"


def walk_entry_kind_complete(path: Path, *, listed_as_directory: bool) -> EntryKind:
    """Classify an ``os.walk`` entry and reject a changed entry category."""
    kind = entry_kind_complete(path)
    if listed_as_directory and kind not in {"directory", "symlink"}:
        raise DiscoveryError(
            "filesystem discovery changed while it was being inspected"
        )
    if not listed_as_directory and kind == "directory":
        raise DiscoveryError(
            "filesystem discovery changed while it was being inspected"
        )
    return kind
