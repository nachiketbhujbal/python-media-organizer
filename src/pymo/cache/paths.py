"""Writable derived-cache target policy."""

from __future__ import annotations

import os
from pathlib import Path

from pymo.collection import CollectionLayout


class CachePathError(ValueError):
    """A requested writable cache target is unsafe or unavailable."""


def writable_cache_path(root: Path, requested: Path | None) -> Path:
    """Resolve a local or explicit cache target without creating its parent."""

    if requested is None:
        return CollectionLayout(root).derived_cache
    database = Path(os.path.abspath(requested.expanduser()))
    if database.name in {"", ".", ".."}:
        raise CachePathError("invalid explicit SQLite cache path")
    if not database.parent.is_dir() or database.parent.is_symlink():
        raise CachePathError(
            "explicit SQLite cache parent must be an existing regular directory"
        )
    return database
