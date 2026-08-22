"""Descriptor-pinned, atomically published cache-file primitives.

This module owns cache filesystem safety, process coordination, and the shared
schema. Evidence-specific payload policy belongs to higher-level services so
the same safe publication boundary can support video, image, hash, and probe
evidence.
"""

from __future__ import annotations

import ctypes
import errno
import fcntl
import json
import os
import re
import secrets
import sqlite3
import stat
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

# These values are persisted in the shared SQLite cache. Changing either one
# without an explicit migration would make stored evidence ambiguous.
SCHEMA_VERSION = 1
LEGACY_VIDEO_EVIDENCE_TYPE = "exact-video-playback"
CacheSchemaKind = Literal["empty", "legacy-video", "current"]


class CacheError(RuntimeError):
    """A derived cache cannot be accessed or published safely."""


@dataclass(frozen=True)
class DerivedEvidence:
    """One algorithm/runtime-specific result keyed by whole-file content."""

    file_sha256: str
    evidence_type: str
    algorithm: str
    runtime: str
    payload_json: str


@dataclass(frozen=True)
class FileObservation:
    """Stable file identity and an optional verified whole-file digest."""

    scope: str
    relative_path: str
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int
    byte_sha256: str | None


def _schema_objects(connection: sqlite3.Connection) -> list[tuple[str, str]]:
    return connection.execute(
        "SELECT type, name FROM sqlite_schema "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()


def _table_signature(
    connection: sqlite3.Connection, table: str
) -> list[tuple[str, str, int, int]]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [(row[1], str(row[2]).upper(), row[3], row[5]) for row in rows]


def _current_signatures() -> dict[str, list[tuple[str, str, int, int]]]:
    return {
        "cache_schema": [
            ("singleton", "INTEGER", 1, 1),
            ("schema_version", "INTEGER", 1, 0),
        ],
        "derived_evidence": [
            ("file_sha256", "TEXT", 1, 1),
            ("evidence_type", "TEXT", 1, 2),
            ("algorithm", "TEXT", 1, 3),
            ("runtime", "TEXT", 1, 4),
            ("payload_json", "TEXT", 1, 0),
        ],
        "file_observations": [
            ("scope", "TEXT", 1, 1),
            ("relative_path", "TEXT", 1, 2),
            ("device", "INTEGER", 1, 0),
            ("inode", "INTEGER", 1, 0),
            ("size", "INTEGER", 1, 0),
            ("modified_ns", "INTEGER", 1, 0),
            ("changed_ns", "INTEGER", 1, 0),
            ("byte_sha256", "TEXT", 0, 0),
        ],
    }


def _current_objects() -> list[tuple[str, str]]:
    return [("table", name) for name in sorted(_current_signatures())]


def _legacy_video_signature() -> list[tuple[str, str, int, int]]:
    return [
        ("file_sha256", "TEXT", 1, 1),
        ("algorithm", "TEXT", 1, 2),
        ("ffmpeg_version", "TEXT", 1, 3),
        ("fingerprint", "TEXT", 1, 0),
        ("video_frames", "INTEGER", 1, 0),
        ("audio_bytes", "INTEGER", 1, 0),
    ]


def _require_integrity(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
        raise CacheError("SQLite cache failed integrity check")


def detect_schema(connection: sqlite3.Connection) -> CacheSchemaKind:
    """Identify only the empty, legacy-video, or exact current cache schema."""

    _require_integrity(connection)
    objects = _schema_objects(connection)
    if not objects:
        return "empty"
    if objects == [("table", "video_fingerprints")]:
        if _table_signature(connection, "video_fingerprints") != (
            _legacy_video_signature()
        ):
            raise CacheError("SQLite cache has an incompatible legacy schema")
        _validated_legacy_video_rows(connection)
        return "legacy-video"
    if objects != _current_objects():
        raise CacheError("SQLite cache has an incompatible schema")
    validate_current_schema(connection)
    return "current"


def _create_current_tables(connection: sqlite3.Connection) -> None:
    # Individual execute calls preserve the caller's transaction. executescript()
    # may commit a pending transaction before running its input.
    statements = (
        "CREATE TABLE cache_schema ("
        "singleton INTEGER NOT NULL PRIMARY KEY CHECK (singleton = 1), "
        "schema_version INTEGER NOT NULL)",
        "CREATE TABLE derived_evidence ("
        "file_sha256 TEXT NOT NULL, evidence_type TEXT NOT NULL, "
        "algorithm TEXT NOT NULL, runtime TEXT NOT NULL, payload_json TEXT NOT NULL, "
        "PRIMARY KEY (file_sha256, evidence_type, algorithm, runtime))",
        "CREATE TABLE file_observations ("
        "scope TEXT NOT NULL, relative_path TEXT NOT NULL, device INTEGER NOT NULL, "
        "inode INTEGER NOT NULL, size INTEGER NOT NULL, modified_ns INTEGER NOT NULL, "
        "changed_ns INTEGER NOT NULL, byte_sha256 TEXT, "
        "PRIMARY KEY (scope, relative_path))",
    )
    for statement in statements:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO cache_schema (singleton, schema_version) VALUES (1, ?)",
        (SCHEMA_VERSION,),
    )


@contextmanager
def _schema_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """Make a multi-statement schema change atomic, including SQLite DDL."""

    connection.execute("SAVEPOINT pymo_schema_change")
    try:
        yield
    except BaseException:
        connection.execute("ROLLBACK TO pymo_schema_change")
        connection.execute("RELEASE pymo_schema_change")
        raise
    else:
        connection.execute("RELEASE pymo_schema_change")


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create the current schema in an otherwise empty SQLite database."""

    if detect_schema(connection) != "empty":
        raise CacheError("SQLite cache schema is already initialized")
    with _schema_transaction(connection):
        _create_current_tables(connection)
    validate_current_schema(connection)


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validate_derived_evidence(record: DerivedEvidence) -> None:
    def reject_nonstandard_constant(value: str) -> object:
        raise ValueError(f"non-standard JSON constant: {value}")

    try:
        payload = json.loads(
            record.payload_json, parse_constant=reject_nonstandard_constant
        )
    except (TypeError, ValueError) as error:
        raise CacheError("SQLite cache contains invalid derived evidence") from error
    if (
        not _is_sha256(record.file_sha256)
        or not isinstance(record.evidence_type, str)
        or not record.evidence_type
        or not isinstance(record.algorithm, str)
        or not record.algorithm
        or not isinstance(record.runtime, str)
        or not record.runtime
        or any(
            "\0" in value
            for value in (record.evidence_type, record.algorithm, record.runtime)
        )
        or not isinstance(payload, dict)
    ):
        raise CacheError("SQLite cache contains invalid derived evidence")


def _validate_file_observation(record: FileObservation) -> None:
    if not isinstance(record.scope, str) or not isinstance(record.relative_path, str):
        raise CacheError("SQLite cache contains an invalid file observation")
    relative = PurePosixPath(record.relative_path)
    integers = (
        record.device,
        record.inode,
        record.size,
        record.modified_ns,
        record.changed_ns,
    )
    if (
        not record.scope
        or not record.relative_path
        or "\0" in record.scope
        or "\0" in record.relative_path
        or relative.is_absolute()
        or not relative.parts
        or relative.as_posix() != record.relative_path
        or any(part == ".." for part in relative.parts)
        or any(
            isinstance(value, bool) or not isinstance(value, int) for value in integers
        )
        or record.device < 0
        or record.inode < 0
        or record.size < 0
        or (record.byte_sha256 is not None and not _is_sha256(record.byte_sha256))
    ):
        raise CacheError("SQLite cache contains an invalid file observation")


def validate_current_schema(connection: sqlite3.Connection) -> None:
    """Validate the exact current schema, version row, and every stored record."""

    _require_integrity(connection)
    if _schema_objects(connection) != _current_objects():
        raise CacheError("SQLite cache has an incompatible schema")
    for table, expected in _current_signatures().items():
        if _table_signature(connection, table) != expected:
            raise CacheError("SQLite cache has an incompatible schema")
    versions = connection.execute(
        "SELECT singleton, schema_version FROM cache_schema"
    ).fetchall()
    if versions != [(1, SCHEMA_VERSION)]:
        raise CacheError("SQLite cache has an unsupported schema version")
    for row in connection.execute(
        "SELECT file_sha256, evidence_type, algorithm, runtime, payload_json "
        "FROM derived_evidence"
    ):
        _validate_derived_evidence(DerivedEvidence(*row))
    for row in connection.execute(
        "SELECT scope, relative_path, device, inode, size, modified_ns, "
        "changed_ns, byte_sha256 FROM file_observations"
    ):
        _validate_file_observation(FileObservation(*row))


def _validated_legacy_video_rows(
    connection: sqlite3.Connection,
) -> list[tuple[str, str, str, str, int, int]]:
    rows = connection.execute(
        "SELECT file_sha256, algorithm, ffmpeg_version, fingerprint, "
        "video_frames, audio_bytes FROM video_fingerprints"
    ).fetchall()
    for file_hash, algorithm, runtime, fingerprint, video_frames, audio_bytes in rows:
        if (
            not _is_sha256(file_hash)
            or not isinstance(algorithm, str)
            or not algorithm
            or not isinstance(runtime, str)
            or not runtime
            or not _is_sha256(fingerprint)
            or isinstance(video_frames, bool)
            or not isinstance(video_frames, int)
            or video_frames <= 0
            or isinstance(audio_bytes, bool)
            or not isinstance(audio_bytes, int)
            or audio_bytes < 0
        ):
            raise CacheError("SQLite legacy video cache contains an invalid row")
    return rows


def migrate_legacy_video_schema(connection: sqlite3.Connection) -> None:
    """Upgrade a validated legacy video schema inside a private working database."""

    if detect_schema(connection) != "legacy-video":
        raise CacheError("SQLite cache is not a legacy video cache")
    rows = _validated_legacy_video_rows(connection)
    with _schema_transaction(connection):
        connection.execute(
            "ALTER TABLE video_fingerprints RENAME TO legacy_video_fingerprints"
        )
        _create_current_tables(connection)
        connection.executemany(
            "INSERT INTO derived_evidence "
            "(file_sha256, evidence_type, algorithm, runtime, payload_json) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    file_hash,
                    LEGACY_VIDEO_EVIDENCE_TYPE,
                    algorithm,
                    runtime,
                    json.dumps(
                        {
                            "audio_bytes": audio_bytes,
                            "digest": fingerprint,
                            "video_frames": video_frames,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
                for (
                    file_hash,
                    algorithm,
                    runtime,
                    fingerprint,
                    video_frames,
                    audio_bytes,
                ) in rows
            ],
        )
        connection.execute("DROP TABLE legacy_video_fingerprints")
    validate_current_schema(connection)


def read_legacy_video_evidence(
    connection: sqlite3.Connection,
) -> list[DerivedEvidence]:
    """Read a validated legacy cache without modifying it."""

    if detect_schema(connection) != "legacy-video":
        raise CacheError("SQLite cache is not a legacy video cache")
    return [
        DerivedEvidence(
            file_sha256=file_hash,
            evidence_type=LEGACY_VIDEO_EVIDENCE_TYPE,
            algorithm=algorithm,
            runtime=runtime,
            payload_json=json.dumps(
                {
                    "audio_bytes": audio_bytes,
                    "digest": fingerprint,
                    "video_frames": video_frames,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        for (
            file_hash,
            algorithm,
            runtime,
            fingerprint,
            video_frames,
            audio_bytes,
        ) in _validated_legacy_video_rows(connection)
    ]


def read_derived_evidence(
    connection: sqlite3.Connection,
    *,
    evidence_type: str,
    algorithm: str,
    runtime: str,
) -> list[DerivedEvidence]:
    """Read one exact evidence namespace from a validated current cache."""

    validate_current_schema(connection)
    rows = connection.execute(
        "SELECT file_sha256, evidence_type, algorithm, runtime, payload_json "
        "FROM derived_evidence WHERE evidence_type = ? AND algorithm = ? "
        "AND runtime = ? ORDER BY file_sha256",
        (evidence_type, algorithm, runtime),
    ).fetchall()
    return [DerivedEvidence(*row) for row in rows]


def read_all_derived_evidence(
    connection: sqlite3.Connection,
) -> list[DerivedEvidence]:
    """Read all validated evidence namespaces from a current cache."""

    validate_current_schema(connection)
    rows = connection.execute(
        "SELECT file_sha256, evidence_type, algorithm, runtime, payload_json "
        "FROM derived_evidence "
        "ORDER BY file_sha256, evidence_type, algorithm, runtime"
    ).fetchall()
    return [DerivedEvidence(*row) for row in rows]


def read_file_observations(
    connection: sqlite3.Connection,
) -> list[FileObservation]:
    """Read all validated file observations from a current cache."""

    validate_current_schema(connection)
    rows = connection.execute(
        "SELECT scope, relative_path, device, inode, size, modified_ns, "
        "changed_ns, byte_sha256 FROM file_observations "
        "ORDER BY scope, relative_path"
    ).fetchall()
    return [FileObservation(*row) for row in rows]


def upsert_derived_evidence(
    connection: sqlite3.Connection, records: Iterable[DerivedEvidence]
) -> None:
    """Validate and merge generic derived evidence into a current cache."""

    validate_current_schema(connection)
    materialized = list(records)
    for record in materialized:
        _validate_derived_evidence(record)
    connection.executemany(
        "INSERT OR REPLACE INTO derived_evidence "
        "(file_sha256, evidence_type, algorithm, runtime, payload_json) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (
                record.file_sha256,
                record.evidence_type,
                record.algorithm,
                record.runtime,
                record.payload_json,
            )
            for record in materialized
        ],
    )


def upsert_file_observations(
    connection: sqlite3.Connection, records: Iterable[FileObservation]
) -> None:
    """Validate and merge stable file identities into a current cache."""

    validate_current_schema(connection)
    materialized = list(records)
    for record in materialized:
        _validate_file_observation(record)
    connection.executemany(
        "INSERT OR REPLACE INTO file_observations "
        "(scope, relative_path, device, inode, size, modified_ns, changed_ns, "
        "byte_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                record.scope,
                record.relative_path,
                record.device,
                record.inode,
                record.size,
                record.modified_ns,
                record.changed_ns,
                record.byte_sha256,
            )
            for record in materialized
        ],
    )


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


@dataclass(frozen=True)
class CacheSnapshot:
    """One descriptor-pinned, read-only view of a public cache database."""

    connection: sqlite3.Connection
    state: CacheEntryState


@contextmanager
def read_cache_snapshot(database: Path) -> Iterator[CacheSnapshot | None]:
    """Read a cache without creating a lock, sidecar, directory, or database.

    A concurrent atomic publisher may replace the public pathname while this
    descriptor remains a safe snapshot. Such a change is reported on context
    exit rather than silently presenting the snapshot as current.
    """

    if database.name in {"", ".", ".."}:
        raise CacheError("unexpected SQLite cache path")
    directory = database.parent
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    directory_descriptor: int | None = None
    cache_descriptor: int | None = None
    connection: sqlite3.Connection | None = None
    try:
        try:
            directory_descriptor = os.open(directory, directory_flags)
        except FileNotFoundError:
            yield None
            return
        except OSError as error:
            raise CacheError("cannot open the SQLite cache directory safely") from error
        directory_state = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(directory_state.st_mode):
            raise CacheError("SQLite cache parent is not a directory")

        def require_directory_current() -> None:
            try:
                current = os.stat(directory, follow_symlinks=False)
            except OSError as error:
                raise CacheError(
                    "SQLite cache directory changed during status inspection"
                ) from error
            if (
                not stat.S_ISDIR(current.st_mode)
                or current.st_dev != directory_state.st_dev
                or current.st_ino != directory_state.st_ino
            ):
                raise CacheError(
                    "SQLite cache directory changed during status inspection"
                )

        require_directory_current()
        entry_state = cache_entry_at(
            directory_descriptor, database.name, "SQLite cache"
        )
        if entry_state is None:
            yield None
            require_directory_current()
            if (
                cache_entry_at(directory_descriptor, database.name, "SQLite cache")
                is not None
            ):
                raise CacheError("SQLite cache changed during status inspection")
            return

        cache_descriptor = open_cache_entry(
            directory_descriptor, database.name, entry_state
        )
        connection = connect_cache_descriptor(cache_descriptor, read_only=True)
        connection.execute("PRAGMA query_only=ON")
        try:
            yield CacheSnapshot(connection=connection, state=entry_state)
        finally:
            connection.close()
            connection = None
            require_cache_entry(
                directory_descriptor,
                database.name,
                entry_state,
                "SQLite cache",
            )
            require_directory_current()
    except sqlite3.Error as error:
        raise CacheError("cannot read the SQLite cache") from error
    finally:
        if connection is not None:
            connection.close()
        if cache_descriptor is not None:
            os.close(cache_descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)
