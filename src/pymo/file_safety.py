"""Stable local file-state snapshots for analysis and mutation preflight."""

from __future__ import annotations

import stat
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
    def capture(cls, path: Path) -> FileState:
        try:
            value = path.stat(follow_symlinks=False)
        except OSError as error:
            raise FileChangedError(f"cannot read file state: {path}") from error
        if not stat.S_ISREG(value.st_mode):
            raise FileChangedError(f"not a regular file: {path}")
        return cls(
            device=value.st_dev,
            inode=value.st_ino,
            size=value.st_size,
            modified_ns=value.st_mtime_ns,
            changed_ns=value.st_ctime_ns,
        )

    def require_unchanged(self, path: Path, operation: str) -> None:
        try:
            current = self.capture(path)
        except FileChangedError as error:
            raise FileChangedError(
                f"file changed during {operation}: {path}"
            ) from error
        if current != self:
            raise FileChangedError(f"file changed during {operation}: {path}")
