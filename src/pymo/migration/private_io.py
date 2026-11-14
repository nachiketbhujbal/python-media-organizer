"""Ephemeral directory/lock bindings propagated to queue stage I/O."""

from __future__ import annotations

import argparse
import json
import os
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PrivateIO:
    directory: Path
    ancestry: tuple[tuple[int, int], ...]
    lock_identity: tuple[int, int]

    def as_argument(self) -> str:
        return json.dumps(
            {
                "directory": str(self.directory),
                "ancestry": self.ancestry,
                "lock_identity": self.lock_identity,
            },
            separators=(",", ":"),
        )

    @contextmanager
    def pinned(self, path: Path) -> Iterator[tuple[int, str, Path]]:
        from pymo.migration.policy_files import _pinned_private_parent

        if path.parent != self.directory:
            raise RuntimeError("private output directory differs from its binding")
        with _pinned_private_parent(path, self.ancestry) as parent:
            self._check_lock(parent[0])
            yield parent
            self._check_lock(parent[0])

    def _check_lock(self, descriptor: int) -> None:
        current = os.stat(
            "pymo-migration-state.lock", dir_fd=descriptor, follow_symlinks=False
        )
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_nlink != 1
            or current.st_mode & 0o077
            or current.st_uid != os.getuid()
            or (current.st_dev, current.st_ino) != self.lock_identity
        ):
            raise RuntimeError("private migration lock binding changed")

    def require_current(self) -> None:
        with self.pinned(self.directory / "pymo-migration-state.lock"):
            pass

    def read(self, path: Path) -> bytes:
        from pymo.migration.policy_files import read_private_identity

        with self.pinned(path):
            return read_private_identity(path, expected_ancestry=self.ancestry)[0]

    def open_log(self, path: Path, *, create: bool) -> int:
        flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        flags |= os.O_CREAT | os.O_EXCL if create else os.O_APPEND
        with self.pinned(path) as (parent, name, _):
            descriptor = os.open(name, flags, 0o600, dir_fd=parent)
            try:
                value = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(value.st_mode)
                    or value.st_nlink != 1
                    or value.st_mode & 0o077
                ):
                    raise RuntimeError("private migration log is unsafe")
            except BaseException:
                os.close(descriptor)
                raise
        return descriptor

    def replace_state(self, path: Path, payload: bytes) -> None:
        with self.pinned(path) as (parent, name, _):
            # This is the existing replaceable bookkeeping record, never media.
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (
                not stat.S_ISREG(current.st_mode)
                or current.st_nlink != 1
                or current.st_mode & 0o077
            ):
                raise RuntimeError("private restart state is unsafe")
            temporary = f".{name}.{uuid.uuid4().hex}.tmp"
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            try:
                with os.fdopen(os.dup(descriptor), "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                self._check_lock(parent)
                os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                os.close(descriptor)


def parse_private_io(value: str) -> PrivateIO:
    """Strict private child invocation binding; it conveys no media authority."""
    try:

        def pairs(value: object) -> tuple[int, int]:
            if (
                not isinstance(value, list)
                or len(value) != 2
                or any(type(v) is not int or v < 0 for v in value)
            ):
                raise ValueError
            return value[0], value[1]

        data = json.loads(value)
        if not isinstance(data, dict) or set(data) != {
            "directory",
            "ancestry",
            "lock_identity",
        }:
            raise ValueError
        directory = Path(data["directory"])
        if (
            not directory.is_absolute()
            or str(directory) != data["directory"]
            or ".." in directory.parts
        ):
            raise ValueError
        if not isinstance(data["ancestry"], list) or not data["ancestry"]:
            raise ValueError
        return PrivateIO(
            directory,
            tuple(pairs(v) for v in data["ancestry"]),
            pairs(data["lock_identity"]),
        )
    except (ValueError, TypeError, KeyError):
        raise argparse.ArgumentTypeError(
            "invalid private migration I/O binding"
        ) from None
