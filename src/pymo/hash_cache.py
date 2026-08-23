"""Stable whole-file SHA observations backed by the disposable cache."""

from __future__ import annotations

import os
import sqlite3
import stat
from collections.abc import Iterable
from pathlib import Path

from pymo import cache as cache_service
from pymo.file_safety import FileState


class HashCacheError(RuntimeError):
    """Whole-file hash observations cannot be used safely."""


def observation_scope(root: Path) -> str:
    """Return a path-private namespace for one current collection directory."""

    try:
        value = os.stat(root, follow_symlinks=False)
    except OSError as error:
        raise HashCacheError("cannot inspect the media-collection root") from error
    if not stat.S_ISDIR(value.st_mode):
        raise HashCacheError("media-collection root is not a directory")
    return f"collection-v1:{value.st_dev}:{value.st_ino}"


def _relative_path(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise HashCacheError("cached file escaped the media collection") from error
    if not relative.parts:
        raise HashCacheError("cannot cache the media-collection root as a file")
    return relative.as_posix()


def _matching_hashes(
    root: Path,
    states: dict[Path, FileState],
    observations: tuple[cache_service.FileObservation, ...],
) -> dict[Path, str]:
    scope = observation_scope(root)
    by_relative = {
        record.relative_path: record
        for record in observations
        if record.scope == scope and record.byte_sha256 is not None
    }
    matches: dict[Path, str] = {}
    for path, state in states.items():
        record = by_relative.get(_relative_path(root, path))
        if record is None:
            continue
        observed_state = (
            record.device,
            record.inode,
            record.size,
            record.modified_ns,
            record.changed_ns,
        )
        if observed_state == (
            state.device,
            state.inode,
            state.size,
            state.modified_ns,
            state.changed_ns,
        ):
            assert record.byte_sha256 is not None
            matches[path] = record.byte_sha256
    return matches


def load_cached_hashes(
    root: Path,
    database: Path,
    states: dict[Path, FileState],
    *,
    coordinated: bool,
) -> dict[Path, str]:
    """Load hashes only for exact current file identities."""

    if not states:
        return {}
    try:
        if coordinated:
            contents = cache_service.read_coordinated_cache(database)
            observations = () if contents is None else contents.observations
        else:
            with cache_service.read_cache_snapshot(database) as snapshot:
                if snapshot is None:
                    observations = ()
                else:
                    observations = cache_service.read_cache_contents(
                        snapshot.connection
                    ).observations
        return _matching_hashes(root, states, observations)
    except (cache_service.CacheError, sqlite3.Error, OSError) as error:
        raise HashCacheError("whole-file hash cache cannot be read safely") from error


def save_cached_hashes(
    root: Path,
    database: Path,
    values: Iterable[tuple[Path, FileState, str]],
) -> None:
    """Publish verified whole-file digests for exact file identities."""

    scope = observation_scope(root)
    observations = tuple(
        cache_service.FileObservation(
            scope=scope,
            relative_path=_relative_path(root, path),
            device=state.device,
            inode=state.inode,
            size=state.size,
            modified_ns=state.modified_ns,
            changed_ns=state.changed_ns,
            byte_sha256=digest,
        )
        for path, state, digest in values
    )
    if not observations:
        return
    try:
        cache_service.publish_cache_update(
            database,
            lambda connection: cache_service.upsert_file_observations(
                connection, observations
            ),
        )
    except cache_service.CacheError as error:
        raise HashCacheError(
            "whole-file hash cache cannot be updated safely"
        ) from error


def save_cached_hash(
    root: Path,
    database: Path,
    path: Path,
    state: FileState,
    digest: str,
) -> None:
    """Publish one verified whole-file digest for an exact file identity."""

    save_cached_hashes(root, database, ((path, state, digest),))
