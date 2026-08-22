"""Descriptor-pinned, atomically published cache-file primitives.

This module owns cache filesystem safety and process coordination. Cache
schemas and evidence types belong to higher-level services so the same safe
publication boundary can support video, image, hash, and probe evidence.
"""

from __future__ import annotations

import ctypes
import errno
import fcntl
import os
import secrets
import sqlite3
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class CacheError(RuntimeError):
    """A derived cache cannot be accessed or published safely."""


@dataclass(frozen=True)
class CacheEntryState:
    """Stable identity for one private regular cache entry."""

    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int
    link_count: int

    @classmethod
    def from_stat(cls, value: os.stat_result, description: str) -> CacheEntryState:
        if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
            raise CacheError(f"{description} is not a private regular file")
        return cls(
            device=value.st_dev,
            inode=value.st_ino,
            size=value.st_size,
            modified_ns=value.st_mtime_ns,
            changed_ns=value.st_ctime_ns,
            link_count=value.st_nlink,
        )

    @classmethod
    def capture_descriptor(cls, descriptor: int, description: str) -> CacheEntryState:
        try:
            value = os.fstat(descriptor)
        except OSError as error:
            raise CacheError(f"cannot inspect {description}") from error
        return cls.from_stat(value, description)

    def matches_renamed(self, other: CacheEntryState | None) -> bool:
        """Return whether ``other`` is this entry after an atomic rename."""

        return other is not None and (
            self.device,
            self.inode,
            self.size,
            self.modified_ns,
            self.link_count,
        ) == (
            other.device,
            other.inode,
            other.size,
            other.modified_ns,
            other.link_count,
        )


@dataclass(frozen=True)
class LockedCacheDirectory:
    """Pinned cache directory and lock entry held under ``flock``."""

    directory: Path
    descriptor: int
    directory_device: int
    directory_inode: int
    lock_name: str
    lock_state: CacheEntryState

    def require_current(self) -> None:
        require_cache_entry(
            self.descriptor,
            self.lock_name,
            self.lock_state,
            "SQLite cache lock",
        )
        try:
            current = os.stat(self.directory, follow_symlinks=False)
        except OSError as error:
            raise CacheError("cache directory changed during cache access") from error
        if (
            not stat.S_ISDIR(current.st_mode)
            or current.st_dev != self.directory_device
            or current.st_ino != self.directory_inode
        ):
            raise CacheError("cache directory changed during cache access")


def cache_entry_at(
    directory_descriptor: int, name: str, description: str
) -> CacheEntryState | None:
    """Capture a direct child without following links, or return missing."""

    try:
        value = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise CacheError(f"cannot inspect {description}") from error
    return CacheEntryState.from_stat(value, description)


def require_cache_entry(
    directory_descriptor: int,
    name: str,
    expected: CacheEntryState,
    description: str,
) -> None:
    """Reject a direct child that no longer has its expected identity."""

    if cache_entry_at(directory_descriptor, name, description) != expected:
        raise CacheError(f"{description} changed during cache access")


@contextmanager
def locked_cache_directory(
    directory: Path, lock_path: Path, *, exclusive: bool
) -> Iterator[LockedCacheDirectory]:
    """Pin a cache directory and hold its direct-child lock safely."""

    if lock_path.parent != directory or lock_path.name in {"", ".", ".."}:
        raise CacheError("unexpected SQLite cache lock path")
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    lock_flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    directory_descriptor: int | None = None
    lock_descriptor: int | None = None
    try:
        try:
            directory_descriptor = os.open(directory, directory_flags)
            directory_state = os.fstat(directory_descriptor)
            if not stat.S_ISDIR(directory_state.st_mode):
                raise OSError(errno.ENOTDIR, "cache parent is not a directory")
            lock_descriptor = os.open(
                lock_path.name,
                lock_flags,
                0o600,
                dir_fd=directory_descriptor,
            )
        except OSError as error:
            raise CacheError("cannot open the SQLite cache lock safely") from error
        lock_state = CacheEntryState.capture_descriptor(
            lock_descriptor, "SQLite cache lock"
        )
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        except OSError as error:
            raise CacheError("cannot acquire the SQLite cache lock") from error
        locked = LockedCacheDirectory(
            directory=directory,
            descriptor=directory_descriptor,
            directory_device=directory_state.st_dev,
            directory_inode=directory_state.st_ino,
            lock_name=lock_path.name,
            lock_state=lock_state,
        )
        try:
            locked.require_current()
            yield locked
            locked.require_current()
        finally:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
    finally:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)


def atomic_cache_rename(
    directory_descriptor: int,
    before_name: str,
    after_name: str,
    *,
    exchange: bool,
) -> None:
    """Publish or exchange direct children atomically without replacement races."""

    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = library.renameatx_np
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        # RENAME_SWAP exchanges entries; RENAME_EXCL refuses an occupied
        # destination. NOFOLLOW_ANY rejects links in either path.
        flags = (0x02 if exchange else 0x04) | 0x10
    elif sys.platform.startswith("linux"):
        try:
            rename = library.renameat2
        except AttributeError as error:
            raise CacheError(
                "this Linux runtime cannot publish the cache atomically"
            ) from error
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        # RENAME_EXCHANGE swaps entries; RENAME_NOREPLACE refuses an occupied
        # destination.
        flags = 0x02 if exchange else 0x01
    else:
        raise CacheError(
            "atomic cache publication is supported only on macOS and Linux"
        )
    result = rename(
        directory_descriptor,
        os.fsencode(before_name),
        directory_descriptor,
        os.fsencode(after_name),
        flags,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise CacheError("SQLite cache path became occupied")
    if error_number in {errno.ELOOP, errno.ENOTDIR}:
        raise CacheError("SQLite cache path became unsafe")
    raise CacheError(
        f"cannot publish SQLite cache atomically: {os.strerror(error_number)}"
    )


def connect_cache_descriptor(descriptor: int, *, read_only: bool) -> sqlite3.Connection:
    """Open SQLite through a pinned descriptor instead of a mutable pathname."""

    mode = "ro" if read_only else "rw"
    return sqlite3.connect(f"file:/dev/fd/{descriptor}?mode={mode}", uri=True)


def open_cache_entry(
    directory_descriptor: int,
    name: str,
    expected: CacheEntryState,
) -> int:
    """Open and identity-check one private cache file without following links."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as error:
        raise CacheError("cannot open SQLite cache safely") from error
    try:
        if (
            CacheEntryState.capture_descriptor(descriptor, "SQLite fingerprint cache")
            != expected
        ):
            raise CacheError("SQLite fingerprint cache changed before open")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def create_cache_stage(directory_descriptor: int) -> tuple[str, int]:
    """Create a private, collision-resistant staging file in the pinned directory."""

    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _ in range(16):
        name = f".pymo.sqlite3.new.{secrets.token_hex(8)}"
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=directory_descriptor)
        except FileExistsError:
            continue
        except OSError as error:
            raise CacheError(
                "cannot create a private SQLite cache staging file"
            ) from error
        return name, descriptor
    raise CacheError("cannot allocate a unique SQLite cache staging file")
