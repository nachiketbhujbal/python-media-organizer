"""Create-once owner-private policy artifacts, separate from collection state."""

from __future__ import annotations

import os
import stat
import uuid
from pathlib import Path

from pymo.managed_quarantine import _atomic_rename_without_replace
from pymo.migration.outcome import (
    _file_identity_from_stat,
    _pinned_outcome_parent,
    _require_external_private_parent,
    _require_parent_outside_roots,
)
from pymo.migration.unattended_binding import require_private_unattended_log_directory
from pymo.migration.virtual import PolicyPlanningError


def read_private(path: Path) -> bytes:
    return read_private_identity(path)[0]


def read_private_identity(path: Path) -> tuple[bytes, tuple[int, ...]]:
    path = path.expanduser().absolute()
    require_private_unattended_log_directory(path.parent)
    with _pinned_outcome_parent(path) as (parent_fd, name, _):
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_fd,
        )
        try:
            initial = os.fstat(fd)
            if (
                not stat.S_ISREG(initial.st_mode)
                or initial.st_nlink != 1
                or initial.st_uid != os.getuid()
                or initial.st_mode & 0o077
                or not 0 < initial.st_size <= 64 * 1024 * 1024
            ):
                raise PolicyPlanningError(
                    "candidate file is unsafe or exceeds its size limit"
                )
            with os.fdopen(os.dup(fd), "rb") as handle:
                payload = handle.read(64 * 1024 * 1024 + 1)
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                len(payload) > 64 * 1024 * 1024
                or _file_identity_from_stat(os.fstat(fd))
                != _file_identity_from_stat(initial)
                or _file_identity_from_stat(current)
                != _file_identity_from_stat(initial)
            ):
                raise PolicyPlanningError("candidate changed during access")
        finally:
            os.close(fd)
    return payload, _file_identity_from_stat(initial)


def publish_private(path: Path, payload: bytes, roots: tuple[Path, Path]) -> None:
    if len(payload) > 64 * 1024 * 1024:
        raise PolicyPlanningError("private artifact exceeds the supported size")
    path = _require_external_private_parent(path, roots)
    require_private_unattended_log_directory(path.parent)
    with _pinned_outcome_parent(path) as (parent_fd, name, parent):
        _require_parent_outside_roots(parent, parent_fd, roots)
        # An interrupted write leaves a private scratch artifact, never a
        # partially published policy. No recovery path adopts that scratch.
        temporary = f".pymo-policy-{uuid.uuid4().hex}.tmp"
        fd = os.open(
            temporary,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        try:
            with os.fdopen(os.dup(fd), "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            current = os.stat(temporary, dir_fd=parent_fd, follow_symlinks=False)
            opened = os.fstat(fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_mode & 0o077
                or opened.st_size != len(payload)
                or _file_identity_from_stat(current) != _file_identity_from_stat(opened)
            ):
                raise PolicyPlanningError("artifact changed during publication")
            os.lseek(fd, 0, os.SEEK_SET)
            with os.fdopen(os.dup(fd), "rb") as handle:
                if handle.read(len(payload) + 1) != payload:
                    raise PolicyPlanningError("artifact bytes failed verification")
            _require_parent_outside_roots(parent, parent_fd, roots)
            require_private_unattended_log_directory(parent)
            _atomic_rename_without_replace(parent_fd, temporary, parent_fd, name)
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if _file_identity_from_stat(current) != _file_identity_from_stat(
                os.fstat(fd)
            ):
                raise PolicyPlanningError("published artifact identity changed")
            os.fsync(parent_fd)
            _require_parent_outside_roots(parent, parent_fd, roots)
        finally:
            os.close(fd)
