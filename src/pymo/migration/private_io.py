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
    log_name: str | None = None
    log_identity: tuple[int, int] | None = None

    def as_argument(self) -> str:
        return json.dumps(
            {
                "directory": str(self.directory),
                "ancestry": self.ancestry,
                "lock_identity": self.lock_identity,
                "log_name": self.log_name,
                "log_identity": self.log_identity,
            },
            separators=(",", ":"),
        )

    @contextmanager
    def pinned(self, path: Path) -> Iterator[tuple[int, str, Path]]:
        from pymo.migration.policy_files import _pinned_private_parent

        if path.parent != self.directory:
            raise RuntimeError("private output directory differs from its binding")
        with _pinned_private_parent(path, self.ancestry) as parent:
            self._check_bindings(parent[0])
            yield parent
            self._check_bindings(parent[0])

    def _check_bindings(self, descriptor: int) -> None:
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

        if self.log_name is not None:
            log = os.stat(self.log_name, dir_fd=descriptor, follow_symlinks=False)
            if (
                not stat.S_ISREG(log.st_mode)
                or log.st_nlink != 1
                or log.st_mode & 0o077
                or log.st_uid != os.getuid()
                or (log.st_dev, log.st_ino) != self.log_identity
            ):
                raise RuntimeError("private migration log binding changed")

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
        descriptor: int | None = None
        try:
            with self.pinned(path) as (parent, name, _):
                if not create and (name != self.log_name or self.log_identity is None):
                    raise RuntimeError("private log lacks its allocation binding")
                descriptor = os.open(name, flags, 0o600, dir_fd=parent)
                value = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(value.st_mode)
                    or value.st_nlink != 1
                    or value.st_mode & 0o077
                    or value.st_uid != os.getuid()
                    or (
                        not create and (value.st_dev, value.st_ino) != self.log_identity
                    )
                ):
                    raise RuntimeError("private migration log is unsafe")
            return descriptor
        except BaseException:
            if descriptor is not None:
                os.close(descriptor)
            raise

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
                self._check_bindings(parent)
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

        def unique(items: list[tuple[str, object]]) -> dict[str, object]:
            result = dict(items)
            if len(result) != len(items):
                raise ValueError
            return result

        if len(value) > 65536:
            raise ValueError
        data = json.loads(value, object_pairs_hook=unique)
        if not isinstance(data, dict) or set(data) != {
            "directory",
            "ancestry",
            "lock_identity",
            "log_name",
            "log_identity",
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
        log_name = data["log_name"]
        if log_name is not None and (
            not isinstance(log_name, str)
            or not log_name
            or Path(log_name).name != log_name
            or log_name in {".", ".."}
            or "\x00" in log_name
        ):
            raise ValueError
        log_identity = (
            pairs(data["log_identity"]) if data["log_identity"] is not None else None
        )
        if (log_name is None) != (log_identity is None):
            raise ValueError
        return PrivateIO(
            directory,
            tuple(pairs(v) for v in data["ancestry"]),
            pairs(data["lock_identity"]),
            log_name,
            log_identity,
        )
    except (ValueError, TypeError, KeyError, RecursionError):
        raise argparse.ArgumentTypeError(
            "invalid private migration I/O binding"
        ) from None
