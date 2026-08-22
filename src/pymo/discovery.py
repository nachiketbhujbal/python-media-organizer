"""Fail-closed filesystem enumeration for complete plans and verification."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path


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
