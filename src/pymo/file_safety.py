"""Stable local file-state snapshots for analysis and mutation preflight."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class FileChangedError(RuntimeError):
    """A file no longer has the state used to derive an analysis result."""


@dataclass(frozen=True)
class FileState:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def _from_stat(cls, value: os.stat_result, description: str) -> FileState:
        if not stat.S_ISREG(value.st_mode):
            raise FileChangedError(f"not a regular file: {description}")
        return cls(
            device=value.st_dev,
            inode=value.st_ino,
            size=value.st_size,
            modified_ns=value.st_mtime_ns,
            changed_ns=value.st_ctime_ns,
        )

    @classmethod
    def capture(cls, path: Path) -> FileState:
        try:
            value = path.stat(follow_symlinks=False)
        except OSError as error:
            raise FileChangedError(f"cannot read file state: {path}") from error
        return cls._from_stat(value, str(path))

    @classmethod
    def capture_descriptor(cls, descriptor: int) -> FileState:
        try:
            value = os.fstat(descriptor)
        except OSError as error:
            raise FileChangedError("cannot read open file state") from error
        return cls._from_stat(value, "open descriptor")

    def require_unchanged(self, path: Path, operation: str) -> None:
        try:
            current = self.capture(path)
        except FileChangedError as error:
            raise FileChangedError(
                f"file changed during {operation}: {path}"
            ) from error
        if current != self:
            raise FileChangedError(f"file changed during {operation}: {path}")


@contextmanager
def open_stable_file(
    root: Path,
    path: Path,
    expected: FileState,
    operation: str,
) -> Iterator[int]:
    """Open one unchanged regular file without following collection links."""
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise FileChangedError(f"file escaped collection during {operation}") from error
    if not relative.parts:
        raise FileChangedError(f"invalid file path during {operation}")

    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    file_flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    parent_descriptor: int | None = None
    file_descriptor: int | None = None
    try:
        try:
            parent_descriptor = os.open(root, directory_flags)
            for part in relative.parts[:-1]:
                next_descriptor = os.open(
                    part, directory_flags, dir_fd=parent_descriptor
                )
                os.close(parent_descriptor)
                parent_descriptor = next_descriptor
            file_descriptor = os.open(
                relative.name, file_flags, dir_fd=parent_descriptor
            )
        except OSError as error:
            raise FileChangedError(
                f"file changed during {operation}: {path}"
            ) from error
        if FileState.capture_descriptor(file_descriptor) != expected:
            raise FileChangedError(f"file changed during {operation}: {path}")
        try:
            yield file_descriptor
        finally:
            if FileState.capture_descriptor(file_descriptor) != expected:
                raise FileChangedError(f"file changed during {operation}: {path}")
            expected.require_unchanged(path, operation)
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
