from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from pymo.cache import service as cache_service
from pymo.cache import status as cache_status
from pymo.cache.hashes import observation_scope
from pymo.cache.probes import (
    VIDEO_PROBE_ALGORITHM,
    VIDEO_PROBE_EVIDENCE_TYPE,
    encode_probe,
)
from pymo.collection import CollectionLayout
from pymo.logging_config import configure_logging
from pymo.video import ProbeInfo


def _write_current_cache(root: Path, media: Path) -> bytes:
    layout = CollectionLayout(root)
    state = media.stat(follow_symlinks=False)
    file_hash = hashlib.sha256(media.read_bytes()).hexdigest()
    connection = sqlite3.connect(layout.derived_cache)
    cache_service.initialize_schema(connection)
    cache_service.upsert_derived_evidence(
        connection,
        [
            cache_service.DerivedEvidence(
                file_sha256=file_hash,
                evidence_type="displayed-pixels",
                algorithm="pixels-v1",
                runtime="pillow-test",
                payload_json='{"digest":"' + "b" * 64 + '"}',
            )
        ],
    )
    cache_service.upsert_file_observations(
        connection,
        [
            cache_service.FileObservation(
                scope=observation_scope(root),
                relative_path=media.relative_to(root).as_posix(),
                device=state.st_dev,
                inode=state.st_ino,
                size=state.st_size,
                modified_ns=state.st_mtime_ns,
                changed_ns=state.st_ctime_ns,
                byte_sha256=file_hash,
            )
        ],
    )
    connection.commit()
    connection.close()
    return layout.derived_cache.read_bytes()


def _write_legacy_cache(database: Path) -> None:
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE video_fingerprints ("
        "file_sha256 TEXT NOT NULL, algorithm TEXT NOT NULL, "
        "ffmpeg_version TEXT NOT NULL, fingerprint TEXT NOT NULL, "
        "video_frames INTEGER NOT NULL, audio_bytes INTEGER NOT NULL, "
        "PRIMARY KEY (file_sha256, algorithm, ffmpeg_version))"
    )
    connection.execute(
        "INSERT INTO video_fingerprints VALUES (?, ?, ?, ?, ?, ?)",
        ("a" * 64, "exact-playback-v2", "ffmpeg-test", "b" * 64, 12, 34),
    )
    connection.commit()
    connection.close()


def test_missing_cache_status_creates_no_collection_state(tmp_path: Path) -> None:
    report, status = cache_status.inspect_cache_status(
        tmp_path,
        CollectionLayout(tmp_path).derived_cache,
        location="collection-local",
    )

    assert status == 0
    assert report["cache"]["state"] == "missing"
    assert report["writes_performed"] is False
    assert list(tmp_path.iterdir()) == []


def test_current_cache_reports_evidence_coverage_without_writing(
    tmp_path: Path,
) -> None:
    pics = tmp_path / "pics"
    pics.mkdir()
    media = pics / "garden.jpg"
    media.write_bytes(b"synthetic image bytes")
    original = _write_current_cache(tmp_path, media)
    layout = CollectionLayout(tmp_path)
    original_modified = layout.derived_cache.stat().st_mtime_ns

    report, status = cache_status.inspect_cache_status(
        tmp_path, layout.derived_cache, location="collection-local"
    )

    assert status == 0
    assert report["cache"] == {
        "location": "collection-local",
        "state": "healthy",
        "format": "shared",
        "cache_schema_version": 1,
        "bytes": len(original),
        "evidence_records": 1,
        "evidence_types": {"displayed-pixels": 1},
        "evidence_namespaces": 1,
        "evidence_compatibility": {
            "algorithm_compatible": 0,
            "stale_algorithm": 0,
            "unknown_type": 1,
            "runtime_checked": False,
        },
        "evidence_coverage": {
            "linked_to_observation": 1,
            "linked_to_current_observation": 1,
            "unlinked": 0,
        },
        "file_observations": {
            "total": 1,
            "current": 1,
            "stale": 0,
            "unreadable": 0,
        },
        "legacy_migration_pending": False,
        "issue": None,
    }
    assert layout.derived_cache.read_bytes() == original
    assert layout.derived_cache.stat().st_mtime_ns == original_modified
    assert not layout.derived_cache_lock.exists()


def test_status_reports_stale_observations_after_file_change(tmp_path: Path) -> None:
    media = tmp_path / "garden.jpg"
    media.write_bytes(b"before")
    _write_current_cache(tmp_path, media)
    media.write_bytes(b"after")

    report, status = cache_status.inspect_cache_status(
        tmp_path,
        CollectionLayout(tmp_path).derived_cache,
        location="collection-local",
    )

    assert status == 0
    assert report["cache"]["file_observations"] == {
        "total": 1,
        "current": 0,
        "stale": 1,
        "unreadable": 0,
    }
    assert report["cache"]["evidence_coverage"] == {
        "linked_to_observation": 1,
        "linked_to_current_observation": 0,
        "unlinked": 0,
    }


def test_status_recognizes_and_validates_video_probe_evidence(tmp_path: Path) -> None:
    layout = CollectionLayout(tmp_path)
    probe = ProbeInfo(
        display_width=64,
        display_height=48,
        duration_us=1_000_000,
        video_start_us=0,
        audio_start_us=None,
        audio_sample_rate=None,
        audio_channels=None,
        audio_layout=None,
        has_audio=False,
    )
    connection = sqlite3.connect(layout.derived_cache)
    cache_service.initialize_schema(connection)
    cache_service.upsert_derived_evidence(
        connection,
        [
            cache_service.DerivedEvidence(
                file_sha256="a" * 64,
                evidence_type=VIDEO_PROBE_EVIDENCE_TYPE,
                algorithm=VIDEO_PROBE_ALGORITHM,
                runtime="ffprobe-test",
                payload_json=encode_probe(probe),
            )
        ],
    )
    connection.commit()
    connection.close()

    report, status = cache_status.inspect_cache_status(
        tmp_path, layout.derived_cache, location="collection-local"
    )

    assert status == 0
    assert report["cache"]["evidence_types"] == {VIDEO_PROBE_EVIDENCE_TYPE: 1}
    assert report["cache"]["evidence_compatibility"] == {
        "algorithm_compatible": 1,
        "stale_algorithm": 0,
        "unknown_type": 0,
        "runtime_checked": False,
    }


def test_status_rejects_malformed_video_probe_evidence(tmp_path: Path) -> None:
    layout = CollectionLayout(tmp_path)
    connection = sqlite3.connect(layout.derived_cache)
    cache_service.initialize_schema(connection)
    cache_service.upsert_derived_evidence(
        connection,
        [
            cache_service.DerivedEvidence(
                file_sha256="a" * 64,
                evidence_type=VIDEO_PROBE_EVIDENCE_TYPE,
                algorithm=VIDEO_PROBE_ALGORITHM,
                runtime="ffprobe-test",
                payload_json='{"unexpected":true}',
            )
        ],
    )
    connection.commit()
    connection.close()

    report, status = cache_status.inspect_cache_status(
        tmp_path, layout.derived_cache, location="collection-local"
    )

    assert status == 1
    assert report["cache"]["state"] == "invalid"


def test_status_treats_another_collection_scope_as_stale(tmp_path: Path) -> None:
    collection = tmp_path / "media-collection"
    other = tmp_path / "other-collection"
    collection.mkdir()
    other.mkdir()
    media = collection / "garden.jpg"
    media.write_bytes(b"content")
    state = media.stat(follow_symlinks=False)
    layout = CollectionLayout(collection)
    connection = sqlite3.connect(layout.derived_cache)
    cache_service.initialize_schema(connection)
    cache_service.upsert_file_observations(
        connection,
        [
            cache_service.FileObservation(
                scope=observation_scope(other),
                relative_path="garden.jpg",
                device=state.st_dev,
                inode=state.st_ino,
                size=state.st_size,
                modified_ns=state.st_mtime_ns,
                changed_ns=state.st_ctime_ns,
                byte_sha256=hashlib.sha256(media.read_bytes()).hexdigest(),
            )
        ],
    )
    connection.commit()
    connection.close()

    report, status = cache_status.inspect_cache_status(
        collection, layout.derived_cache, location="collection-local"
    )

    assert status == 0
    assert report["cache"]["file_observations"] == {
        "total": 1,
        "current": 0,
        "stale": 1,
        "unreadable": 0,
    }


def test_status_does_not_follow_an_observation_parent_symlink(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    outside = tmp_path / "outside"
    collection.mkdir()
    outside.mkdir()
    outside_media = outside / "garden.jpg"
    outside_media.write_bytes(b"outside")
    linked_parent = collection / "pics"
    linked_parent.symlink_to(outside, target_is_directory=True)
    state = outside_media.stat()
    file_hash = hashlib.sha256(outside_media.read_bytes()).hexdigest()
    layout = CollectionLayout(collection)
    connection = sqlite3.connect(layout.derived_cache)
    cache_service.initialize_schema(connection)
    cache_service.upsert_file_observations(
        connection,
        [
            cache_service.FileObservation(
                scope=observation_scope(collection),
                relative_path="pics/garden.jpg",
                device=state.st_dev,
                inode=state.st_ino,
                size=state.st_size,
                modified_ns=state.st_mtime_ns,
                changed_ns=state.st_ctime_ns,
                byte_sha256=file_hash,
            )
        ],
    )
    connection.commit()
    connection.close()

    report, status = cache_status.inspect_cache_status(
        collection, layout.derived_cache, location="collection-local"
    )

    assert status == 0
    assert report["cache"]["file_observations"] == {
        "total": 1,
        "current": 0,
        "stale": 0,
        "unreadable": 1,
    }
    assert outside_media.read_bytes() == b"outside"


def test_legacy_status_does_not_migrate_or_create_a_lock(tmp_path: Path) -> None:
    layout = CollectionLayout(tmp_path)
    _write_legacy_cache(layout.derived_cache)
    original = layout.derived_cache.read_bytes()

    report, status = cache_status.inspect_cache_status(
        tmp_path, layout.derived_cache, location="collection-local"
    )

    assert status == 0
    assert report["cache"]["state"] == "healthy"
    assert report["cache"]["format"] == "legacy-video"
    assert report["cache"]["evidence_records"] == 1
    assert report["cache"]["legacy_migration_pending"] is True
    assert layout.derived_cache.read_bytes() == original
    assert not layout.derived_cache_lock.exists()


def test_invalid_cache_is_reported_and_preserved(tmp_path: Path) -> None:
    layout = CollectionLayout(tmp_path)
    original = b"not a SQLite database"
    layout.derived_cache.write_bytes(original)

    report, status = cache_status.inspect_cache_status(
        tmp_path, layout.derived_cache, location="collection-local"
    )

    assert status == 1
    assert report["cache"]["state"] == "invalid"
    assert report["cache"]["issue"] == "unsafe-unreadable-or-incompatible"
    assert layout.derived_cache.read_bytes() == original
    assert not layout.derived_cache_lock.exists()


def test_malformed_supported_evidence_makes_cache_status_invalid(
    tmp_path: Path,
) -> None:
    layout = CollectionLayout(tmp_path)
    connection = sqlite3.connect(layout.derived_cache)
    cache_service.initialize_schema(connection)
    cache_service.upsert_derived_evidence(
        connection,
        [
            cache_service.DerivedEvidence(
                file_sha256="a" * 64,
                evidence_type=cache_service.LEGACY_VIDEO_EVIDENCE_TYPE,
                algorithm="exact-playback-v2",
                runtime="ffmpeg-test",
                payload_json='{"unexpected":true}',
            )
        ],
    )
    connection.commit()
    connection.close()
    original = layout.derived_cache.read_bytes()

    report, status = cache_status.inspect_cache_status(
        tmp_path, layout.derived_cache, location="collection-local"
    )

    assert status == 1
    assert report["cache"]["state"] == "invalid"
    assert layout.derived_cache.read_bytes() == original
    assert not layout.derived_cache_lock.exists()


def test_symlink_cache_is_rejected_without_reading_its_target(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    outside = tmp_path / "outside"
    collection.mkdir()
    outside.mkdir()
    target = outside / "derived.sqlite3"
    _write_legacy_cache(target)
    original = target.read_bytes()
    CollectionLayout(collection).derived_cache.symlink_to(target)

    report, status = cache_status.inspect_cache_status(
        collection,
        CollectionLayout(collection).derived_cache,
        location="collection-local",
    )

    assert status == 1
    assert report["cache"]["state"] == "invalid"
    assert target.read_bytes() == original
    assert not CollectionLayout(collection).derived_cache_lock.exists()


def test_explicit_cache_can_live_outside_the_collection(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    cache_directory = tmp_path / "derived-state"
    collection.mkdir()
    cache_directory.mkdir()
    database = cache_directory / "cache.sqlite3"
    _write_legacy_cache(database)

    report, status = cache_status.inspect_cache_status(
        collection, database, location="explicit"
    )

    assert status == 0
    assert report["cache"]["location"] == "explicit"
    assert report["cache"]["format"] == "legacy-video"
    assert list(collection.iterdir()) == []
    assert list(cache_directory.iterdir()) == [database]


def test_json_main_is_path_private_and_creates_no_state(tmp_path: Path, capsys) -> None:
    collection = tmp_path / "private-topic"
    collection.mkdir()
    configure_logging(timestamps=False)

    status = cache_status.main(["status", str(collection), "--json"])
    captured = capsys.readouterr()

    assert status == 0
    report = json.loads(captured.out)
    assert report["cache"]["state"] == "missing"
    assert str(collection) not in captured.out
    assert collection.name not in captured.out
    assert captured.err == ""
    assert list(collection.iterdir()) == []


def test_human_report_is_aggregate_and_path_private(tmp_path: Path, capsys) -> None:
    media = tmp_path / "garden.jpg"
    media.write_bytes(b"synthetic image bytes")
    _write_current_cache(tmp_path, media)
    report, status = cache_status.inspect_cache_status(
        tmp_path,
        CollectionLayout(tmp_path).derived_cache,
        location="collection-local",
    )
    configure_logging(timestamps=False)

    cache_status.print_report(report)
    captured = capsys.readouterr()

    assert status == 0
    assert "State: healthy" in captured.out
    assert "Format: shared schema 1" in captured.out
    assert '"displayed-pixels": 1' in captured.out
    assert "Runtime compatibility: not checked" in captured.out
    assert "1 total; 1 current; 0 stale; 0 unreadable" in captured.out
    assert (
        "Read-only: no cache, lock, media, or action state was written" in captured.out
    )
    assert str(tmp_path) not in captured.out
    assert media.name not in captured.out
    assert captured.err == ""


def test_invalid_collection_json_is_path_private_setup_error(
    tmp_path: Path, capsys
) -> None:
    missing = tmp_path / "private-topic"
    configure_logging(timestamps=False)

    status = cache_status.main(["status", str(missing), "--json"])
    captured = capsys.readouterr()

    assert status == 2
    report = json.loads(captured.out)
    assert report["cache"]["state"] == "invalid"
    assert report["cache"]["issue"] == "collection-not-directory"
    assert str(missing) not in captured.out
    assert missing.name not in captured.out
    assert captured.err == ""
    assert not missing.exists()
