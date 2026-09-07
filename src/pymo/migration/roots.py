"""Filesystem-identity separation for migration roots and private state."""

from __future__ import annotations

import os
import stat
from pathlib import Path


class DirectoryIdentityError(Exception):
    """Raised when directory identity cannot be established safely."""


def directory_identity(path: Path) -> tuple[int, int] | None:
    """Return a no-follow directory identity, or ``None`` for a missing path."""

    try:
        value = os.stat(path, follow_symlinks=False)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as error:
        raise DirectoryIdentityError(
            "directory identity could not be verified"
        ) from error
    if not stat.S_ISDIR(value.st_mode):
        return None
    return (value.st_dev, value.st_ino)


def path_is_within(child: Path, root: Path) -> bool:
    """Return whether an existing ancestor of ``child`` is ``root`` by identity."""

    root_identity = directory_identity(root)
    if root_identity is None:
        return False
    current = child
    while True:
        if directory_identity(current) == root_identity:
            return True
        if current.parent == current:
            return False
        current = current.parent


def paths_are_disjoint(first: Path, second: Path) -> bool:
    """Compare possibly not-yet-created paths by filesystem ancestry."""

    return not path_is_within(first, second) and not path_is_within(second, first)


def _existing_path_is_within(
    child: Path,
    child_identity: tuple[int, int],
    root_identity: tuple[int, int],
) -> bool:
    """Walk one required root's ancestry without accepting missing observations."""

    current = child
    first_observation = True
    while True:
        current_identity = directory_identity(current)
        if current_identity is None:
            raise DirectoryIdentityError("directory identity could not be verified")
        if first_observation:
            if current_identity != child_identity:
                raise DirectoryIdentityError("directory identity could not be verified")
            first_observation = False
        if current_identity == root_identity:
            return True
        if current.parent == current:
            return False
        current = current.parent


def existing_directories_are_disjoint(first: Path, second: Path) -> bool:
    """Compare two required directory roots by filesystem ancestry."""

    first_identity = directory_identity(first)
    second_identity = directory_identity(second)
    if first_identity is None or second_identity is None:
        raise DirectoryIdentityError("directory identity could not be verified")
    first_within_second = _existing_path_is_within(
        first, first_identity, second_identity
    )
    second_within_first = _existing_path_is_within(
        second, second_identity, first_identity
    )
    final_first_identity = directory_identity(first)
    final_second_identity = directory_identity(second)
    if (
        final_first_identity != first_identity
        or final_second_identity != second_identity
    ):
        raise DirectoryIdentityError("directory identity could not be verified")
    return not first_within_second and not second_within_first
