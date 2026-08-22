from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

import pytest

from pymo.cache import (
    LEGACY_VIDEO_EVIDENCE_TYPE,
    SCHEMA_VERSION,
    CacheError,
    DerivedEvidence,
    FileObservation,
    create_cache_stage,
    detect_schema,
    initialize_schema,
    locked_cache_directory,
    migrate_legacy_video_schema,
    upsert_derived_evidence,
    upsert_file_observations,
    validate_current_schema,
)


def legacy_video_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE video_fingerprints ("
        "file_sha256 TEXT NOT NULL, algorithm TEXT NOT NULL, "
        "ffmpeg_version TEXT NOT NULL, fingerprint TEXT NOT NULL, "
        "video_frames INTEGER NOT NULL, audio_bytes INTEGER NOT NULL, "
        "PRIMARY KEY (file_sha256, algorithm, ffmpeg_version))"
    )


def test_cache_lock_is_anchored_to_cache_directory_not_media_root(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    cache_directory = tmp_path / "derived-state"
    media_root.mkdir()
    cache_directory.mkdir()
    lock = cache_directory / "cache.lock"

    with locked_cache_directory(cache_directory, lock, exclusive=False) as locked:
        assert locked.directory == cache_directory
        assert locked.descriptor >= 0

    assert lock.is_file()
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    assert list(media_root.iterdir()) == []


def test_cache_lock_rejects_a_path_outside_its_directory(tmp_path: Path) -> None:
    cache_directory = tmp_path / "derived-state"
    cache_directory.mkdir()
    outside = tmp_path / "outside.lock"

    with pytest.raises(CacheError, match="unexpected SQLite cache lock path"):
        with locked_cache_directory(cache_directory, outside, exclusive=True):
            pytest.fail("an outside lock path must not be opened")

    assert not outside.exists()


def test_cache_stage_is_private_and_created_in_the_pinned_directory(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "cache.lock"

    with locked_cache_directory(tmp_path, lock, exclusive=True) as locked:
        name, descriptor = create_cache_stage(locked.descriptor)
        try:
            state = os.fstat(descriptor)
            assert stat.S_ISREG(state.st_mode)
            assert stat.S_IMODE(state.st_mode) == 0o600
            assert state.st_nlink == 1
            assert (tmp_path / name).is_file()
        finally:
            os.close(descriptor)
            os.unlink(name, dir_fd=locked.descriptor)

    assert not list(tmp_path.glob(".pymo.sqlite3.new.*"))


def test_current_schema_records_versioned_evidence_and_file_identity() -> None:
    connection = sqlite3.connect(":memory:")
    initialize_schema(connection)

    assert detect_schema(connection) == "current"
    assert connection.execute("SELECT schema_version FROM cache_schema").fetchone() == (
        SCHEMA_VERSION,
    )

    upsert_derived_evidence(
        connection,
        iter(
            [
                DerivedEvidence(
                    file_sha256="a" * 64,
                    evidence_type="displayed-pixels",
                    algorithm="pixels-v1",
                    runtime="pillow-test",
                    payload_json='{"digest":"' + "b" * 64 + '"}',
                )
            ]
        ),
    )
    upsert_file_observations(
        connection,
        iter(
            [
                FileObservation(
                    scope="source-a",
                    relative_path="pics/leaf.jpg",
                    device=1,
                    inode=2,
                    size=3,
                    modified_ns=4,
                    changed_ns=5,
                    byte_sha256="a" * 64,
                )
            ]
        ),
    )
    connection.commit()

    validate_current_schema(connection)
    assert connection.execute(
        "SELECT evidence_type, algorithm, runtime FROM derived_evidence"
    ).fetchone() == ("displayed-pixels", "pixels-v1", "pillow-test")
    assert connection.execute(
        "SELECT scope, relative_path, byte_sha256 FROM file_observations"
    ).fetchone() == ("source-a", "pics/leaf.jpg", "a" * 64)
    connection.close()


def test_legacy_video_schema_migrates_to_generic_evidence() -> None:
    connection = sqlite3.connect(":memory:")
    legacy_video_schema(connection)
    connection.execute(
        "INSERT INTO video_fingerprints VALUES (?, ?, ?, ?, ?, ?)",
        ("a" * 64, "exact-playback-v2", "ffmpeg-test", "b" * 64, 12, 34),
    )
    connection.commit()

    assert detect_schema(connection) == "legacy-video"
    migrate_legacy_video_schema(connection)

    assert detect_schema(connection) == "current"
    assert connection.execute(
        "SELECT file_sha256, evidence_type, algorithm, runtime, payload_json "
        "FROM derived_evidence"
    ).fetchone() == (
        "a" * 64,
        LEGACY_VIDEO_EVIDENCE_TYPE,
        "exact-playback-v2",
        "ffmpeg-test",
        '{"audio_bytes":34,"digest":"' + "b" * 64 + '","video_frames":12}',
    )
    assert (
        connection.execute(
            "SELECT name FROM sqlite_schema WHERE name = 'video_fingerprints'"
        ).fetchone()
        is None
    )
    connection.close()


def test_legacy_migration_rolls_back_every_schema_change_on_failure() -> None:
    connection = sqlite3.connect(":memory:")
    legacy_video_schema(connection)
    connection.execute(
        "INSERT INTO video_fingerprints VALUES (?, ?, ?, ?, ?, ?)",
        ("a" * 64, "exact-playback-v2", "ffmpeg-test", "b" * 64, 12, 34),
    )
    connection.commit()

    def deny_drop(
        action: int,
        _arg1: str | None,
        _arg2: str | None,
        _database: str | None,
        _trigger: str | None,
    ) -> int:
        if action == sqlite3.SQLITE_DROP_TABLE:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(deny_drop)
    with pytest.raises(sqlite3.DatabaseError):
        migrate_legacy_video_schema(connection)
    connection.set_authorizer(None)

    assert detect_schema(connection) == "legacy-video"
    assert connection.execute(
        "SELECT file_sha256 FROM video_fingerprints"
    ).fetchall() == [("a" * 64,)]
    connection.close()


def test_schema_rejects_an_unsupported_version_without_modifying_it() -> None:
    connection = sqlite3.connect(":memory:")
    initialize_schema(connection)
    connection.execute("UPDATE cache_schema SET schema_version = 999")
    connection.commit()

    with pytest.raises(CacheError, match="unsupported schema version"):
        detect_schema(connection)

    assert connection.execute("SELECT schema_version FROM cache_schema").fetchone() == (
        999,
    )
    connection.close()


def test_malformed_legacy_row_is_rejected_without_migration() -> None:
    connection = sqlite3.connect(":memory:")
    legacy_video_schema(connection)
    connection.execute(
        "INSERT INTO video_fingerprints VALUES (?, ?, ?, ?, ?, ?)",
        ("bad", "exact-playback-v2", "ffmpeg-test", "also-bad", 0, -1),
    )
    connection.commit()

    with pytest.raises(CacheError, match="invalid row"):
        migrate_legacy_video_schema(connection)

    assert connection.execute(
        "SELECT name FROM sqlite_schema WHERE name = 'video_fingerprints'"
    ).fetchone() == ("video_fingerprints",)
    connection.close()


def test_current_schema_rejects_malformed_evidence_and_file_identity() -> None:
    connection = sqlite3.connect(":memory:")
    initialize_schema(connection)
    connection.execute(
        "INSERT INTO derived_evidence VALUES (?, ?, ?, ?, ?)",
        ("a" * 64, "displayed-pixels", "pixels-v1", "runtime", "[]"),
    )
    connection.commit()

    with pytest.raises(CacheError, match="invalid derived evidence"):
        validate_current_schema(connection)

    connection.execute("DELETE FROM derived_evidence")
    connection.execute(
        "INSERT INTO file_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("source-a", "../escape.jpg", 1, 2, 3, 4, 5, None),
    )
    connection.commit()

    with pytest.raises(CacheError, match="invalid file observation"):
        validate_current_schema(connection)
    connection.close()


@pytest.mark.parametrize(
    "payload",
    ['{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}'],
)
def test_current_schema_rejects_nonstandard_json_constants(payload: str) -> None:
    connection = sqlite3.connect(":memory:")
    initialize_schema(connection)
    connection.execute(
        "INSERT INTO derived_evidence VALUES (?, ?, ?, ?, ?)",
        ("a" * 64, "displayed-pixels", "pixels-v1", "runtime", payload),
    )
    connection.commit()

    with pytest.raises(CacheError, match="invalid derived evidence"):
        validate_current_schema(connection)
    connection.close()


@pytest.mark.parametrize("relative_path", [".", "pics//leaf.jpg", "pics/./leaf.jpg"])
def test_current_schema_rejects_noncanonical_relative_paths(
    relative_path: str,
) -> None:
    connection = sqlite3.connect(":memory:")
    initialize_schema(connection)
    connection.execute(
        "INSERT INTO file_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("source-a", relative_path, 1, 2, 3, 4, 5, None),
    )
    connection.commit()

    with pytest.raises(CacheError, match="invalid file observation"):
        validate_current_schema(connection)
    connection.close()
