from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import threading
from pathlib import Path

import pytest

from pymo import cache as cache_service
from pymo.action_log import action_log_path
from pymo.collection import CollectionLayout
from pymo.config import load_config
from pymo.discovery import DiscoveryError
from pymo.duplicates import common as duplicate_common
from pymo.duplicates import videos as video_duplicates
from pymo.duplicates.videos import ProbeInfo
from pymo.organize import Classifier

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG or not FFPROBE,
    reason="real FFmpeg integration test requires ffmpeg and ffprobe",
)


def ffmpeg(*arguments: object) -> None:
    assert FFMPEG
    result = subprocess.run(
        [FFMPEG, "-v", "error", "-y", *(str(item) for item in arguments)],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def make_video(path: Path, *, frequency: int = 440, audio: bool = True) -> None:
    arguments: list[object] = [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=64x48:rate=5:duration=1",
    ]
    if audio:
        arguments.extend(
            [
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:sample_rate=8000:duration=1",
            ]
        )
    arguments.extend(["-c:v", "mpeg4", "-pix_fmt", "yuv420p"])
    if audio:
        arguments.extend(["-c:a", "aac", "-shortest"])
    arguments.append(path)
    ffmpeg(*arguments)


@requires_ffmpeg
def test_video_finder_dry_run_apply_and_undo_exact_playback(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    cache = CollectionLayout(tmp_path).video_cache
    base = vids / "base.mp4"
    byte_copy = vids / "byte-copy.mp4"
    metadata_copy = vids / "metadata-copy.mp4"
    make_video(base)
    shutil.copyfile(base, byte_copy)
    ffmpeg(
        "-i",
        base,
        "-map",
        "0",
        "-c",
        "copy",
        "-metadata",
        "title=synthetic",
        metadata_copy,
    )
    assert base.read_bytes() != metadata_copy.read_bytes()

    dry_run = run_script("find_video_duplicates.py", tmp_path)

    assert dry_run.returncode == 0, dry_run.stdout + dry_run.stderr
    assert "Would move 2 duplicate(s) from 1 group(s)" in dry_run.stdout
    assert "Potentially reclaimable if extra copies were deleted" in dry_run.stdout
    assert "No files are deleted by this tool" in dry_run.stdout
    assert (
        "Fingerprint cache lookup: 0 reusable record(s); 2 fingerprint(s) required."
        in dry_run.stdout
    )
    assert (
        "Fingerprint cache update: 2 new record(s) persisted; "
        "0 required fingerprint(s) not persisted." in dry_run.stdout
    )
    assert "inspected 3/3 (100.0%)" in dry_run.stdout
    assert "Fingerprinting 2 candidate content file(s)" in dry_run.stdout
    assert "fingerprint progress 2/2 (100.0%)" in dry_run.stdout
    for stage in ("discovery", "probing", "fingerprinting", "planning"):
        assert f"Stage timing: {stage} " in dry_run.stdout
    assert "Stage timing: apply " not in dry_run.stdout
    assert "Stage timing: verification " not in dry_run.stdout
    assert "/s" in dry_run.stdout
    assert not (tmp_path / "dups").exists()
    assert cache.is_file()
    assert not action_log_path(tmp_path).exists()

    applied = run_script("find_video_duplicates.py", tmp_path, "--apply")

    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert (
        "Fingerprint cache lookup: 2 reusable record(s); 0 fingerprint(s) required."
        in applied.stdout
    )
    assert (
        "Fingerprint cache update: 0 new record(s) persisted; "
        "0 required fingerprint(s) not persisted." in applied.stdout
    )
    for stage in (
        "discovery",
        "probing",
        "fingerprinting",
        "planning",
        "apply",
        "verification",
    ):
        assert f"Stage timing: {stage} " in applied.stdout
    assert not base.exists()
    assert not byte_copy.exists()
    assert metadata_copy.exists()
    assert (tmp_path / "dups" / "vids" / "metadata-copy_copy(1).mp4").exists()
    assert (tmp_path / "dups" / "vids" / "metadata-copy_copy(2).mp4").exists()
    assert not (tmp_path / "dups" / "pics").exists()
    assert cache.is_file()
    assert CollectionLayout(tmp_path).video_cache_lock.is_file()
    assert not list(tmp_path.glob(".pymo.sqlite3.new.*"))
    assert not cache.with_name(f"{cache.name}-wal").exists()
    assert not cache.with_name(f"{cache.name}-shm").exists()
    assert action_log_path(tmp_path).is_file()

    undone = run_script("find_video_duplicates.py", tmp_path, "--undo", "--apply")

    assert undone.returncode == 0, undone.stdout + undone.stderr
    assert base.exists()
    assert byte_copy.exists()
    assert metadata_copy.exists()
    assert not (tmp_path / "dups").exists()
    assert cache.is_file()
    assert action_log_path(tmp_path).is_file()


@requires_ffmpeg
def test_video_finder_can_disable_all_cache_reads_and_writes(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    first = vids / "first.mp4"
    second = vids / "second.mp4"
    make_video(first)
    shutil.copyfile(first, second)

    result = run_script("find_video_duplicates.py", tmp_path, "--no-cache")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "Fingerprint cache disabled by --no-cache: no records read or written; "
        "1 fingerprint(s) required." in result.stdout
    )
    assert "Fingerprint cache lookup:" not in result.stdout
    assert "Fingerprint cache update:" not in result.stdout
    assert not CollectionLayout(tmp_path).video_cache.exists()
    assert not action_log_path(tmp_path).exists()


def test_video_finder_rejects_conflicting_cache_controls(
    tmp_path: Path, run_script
) -> None:
    result = run_script(
        "find_video_duplicates.py",
        tmp_path,
        "--no-cache",
        "--cache",
        tmp_path / "cache.sqlite3",
    )

    assert result.returncode == 2
    assert "--no-cache cannot be combined with --cache" in result.stderr
    assert list(tmp_path.iterdir()) == []


@requires_ffmpeg
def test_video_summary_applies_with_path_private_aggregate_output(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "private-garden-collection"
    vids = root / "vids"
    vids.mkdir(parents=True)
    first = vids / "secret-cedar.mp4"
    second = vids / "secret-maple.mp4"
    broken = vids / "secret-broken.mp4"
    make_video(first)
    shutil.copyfile(first, second)
    broken.write_bytes(first.read_bytes()[:32])

    result = run_script("find_video_duplicates.py", root, "--summary", "--apply")

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Scanning 3 video(s)" in result.stdout
    assert "Moved 1 duplicate(s) from 1 group(s)" in result.stdout
    assert "Skipped 1 file(s)." in result.stdout
    assert "Duplicate storage summary:" in result.stdout
    assert "Action log updated." in result.stdout
    assert "Stage timing: verification " in result.stdout
    assert "Group 1:" not in output
    assert "duplicate:" not in output
    assert "starting fingerprint" not in output
    assert "Action log:" not in output
    for private_text in (root.name, first.name, second.name, broken.name, str(root)):
        assert private_text not in output
    assert action_log_path(root).is_file()

    undo_preview = run_script("find_video_duplicates.py", root, "--summary", "--undo")

    undo_output = undo_preview.stdout + undo_preview.stderr
    assert undo_preview.returncode == 0, undo_output
    assert "Would reverse" in undo_preview.stdout
    assert "Using action log:" not in undo_output
    assert "Video duplicate-finder run:" not in undo_output
    for private_text in (root.name, first.name, second.name, broken.name, str(root)):
        assert private_text not in undo_output


def test_video_summary_refuses_explicit_ignored_paths(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "private-garden-collection"
    (root / "vids").mkdir(parents=True)

    result = run_script("find_video_duplicates.py", root, "--summary", "--show-ignored")

    assert result.returncode == 2
    assert "cannot be combined" in result.stderr
    assert root.name not in result.stdout + result.stderr


def test_video_finder_requires_only_vids(tmp_path: Path, run_script) -> None:
    result = run_script("find_video_duplicates.py", tmp_path)

    assert result.returncode == 2
    assert "missing required folder" in result.stderr
    assert "videos are directly in vids" in result.stderr


@requires_ffmpeg
def test_video_finder_ignores_picture_folder_state(tmp_path: Path, run_script) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    (vids / ".DS_Store").write_bytes(b"view state")
    (vids / "protected.mp4").write_bytes(b"not inspected")
    (tmp_path / ".pymo.toml").write_text(
        'version = 1\n\n[ignore]\nfiles = ["protected.mp4"]\n',
        encoding="utf-8",
    )
    (tmp_path / "pictures").mkdir()
    dups = tmp_path / "dups"
    dups.mkdir()
    (dups / "pics").write_text("owned by the image finder", encoding="utf-8")

    result = run_script("find_video_duplicates.py", tmp_path, "--show-ignored")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Scanning 0 video(s)" in result.stdout
    assert "Ignored by configuration: 2 path(s)." in result.stdout
    assert "  vids/.DS_Store" in result.stdout
    assert "  vids/protected.mp4" in result.stdout
    assert (vids / "protected.mp4").read_bytes() == b"not inspected"
    assert (dups / "pics").read_text(encoding="utf-8") == "owned by the image finder"


@requires_ffmpeg
def test_video_finder_does_not_match_different_audio(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    make_video(vids / "tone-440.mp4", frequency=440)
    make_video(vids / "tone-880.mp4", frequency=880)

    result = run_script("find_video_duplicates.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Would move 0 duplicate(s)" in result.stdout
    assert not (tmp_path / "dups").exists()


@requires_ffmpeg
def test_video_finder_does_not_match_different_playback_timing(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    original = vids / "original.mkv"
    slower = vids / "slower.mkv"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=64x48:rate=5:duration=1",
        "-c:v",
        "ffv1",
        original,
    )
    ffmpeg(
        "-i",
        original,
        "-vf",
        "setpts=2*PTS",
        "-fps_mode",
        "passthrough",
        "-c:v",
        "ffv1",
        slower,
    )

    result = run_script("find_video_duplicates.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Would move 0 duplicate(s)" in result.stdout


@requires_ffmpeg
def test_video_finder_skips_corrupt_and_multiple_audio_streams(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    (vids / "broken.mp4").write_bytes(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    )
    ambiguous = vids / "multiple-audio.mkv"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=64x48:rate=5:duration=1",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=8000:duration=1",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:sample_rate=8000:duration=1",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-map",
        "2:a:0",
        "-c:v",
        "mpeg4",
        "-c:a",
        "aac",
        "-shortest",
        ambiguous,
    )

    result = run_script("find_video_duplicates.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Skipped 2 file(s)" in result.stdout
    assert "multiple audio streams are not yet supported" in result.stdout
    assert "ffprobe rejected the file" in result.stdout
    assert (vids / "broken.mp4").exists()
    assert ambiguous.exists()


@requires_ffmpeg
def test_video_finder_never_overwrites_and_preserves_pics_review(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    first = vids / "first.mp4"
    second = vids / "second.mp4"
    make_video(first)
    shutil.copyfile(first, second)
    duplicate_vids = tmp_path / "dups" / "vids"
    duplicate_vids.mkdir(parents=True)
    duplicate_pics = tmp_path / "dups" / "pics"
    duplicate_pics.mkdir()
    protected = duplicate_pics / "review.jpg"
    protected.write_bytes(b"leave this alone")
    occupied = duplicate_vids / "first_copy(1).mp4"
    occupied.write_bytes(b"do not overwrite")

    result = run_script("find_video_duplicates.py", tmp_path, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert occupied.read_bytes() == b"do not overwrite"
    assert (duplicate_vids / "first_copy(2).mp4").exists()
    assert protected.read_bytes() == b"leave this alone"


@requires_ffmpeg
def test_video_duplicate_run_blocks_earlier_rename_undo(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "collection"
    vids = root / "vids"
    pics = root / "pics"
    vids.mkdir(parents=True)
    pics.mkdir()
    first = vids / "first.mp4"
    second = vids / "second.mp4"
    make_video(first)
    shutil.copyfile(first, second)

    renamed = run_script("rename_media.py", root, "--apply")
    assert renamed.returncode == 0, renamed.stdout + renamed.stderr
    duplicate_run = run_script("find_video_duplicates.py", root, "--apply")
    assert duplicate_run.returncode == 0, duplicate_run.stdout + duplicate_run.stderr

    blocked = run_script("rename_media.py", root, "--undo", "--apply")
    assert blocked.returncode == 1
    assert "find_video_duplicates" in blocked.stderr

    assert (
        run_script("find_video_duplicates.py", root, "--undo", "--apply").returncode
        == 0
    )
    assert run_script("rename_media.py", root, "--undo", "--apply").returncode == 0
    assert first.exists()
    assert second.exists()


def test_video_finder_reports_missing_explicit_ffmpeg(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    (vids / "first.mp4").write_bytes(b"\x00first")
    (vids / "second.mp4").write_bytes(b"\x00second")
    missing = tmp_path / "not-ffmpeg"

    result = run_script(
        "find_video_duplicates.py",
        tmp_path,
        "--ffmpeg",
        missing,
        "--ffprobe",
        missing,
    )

    assert result.returncode == 2
    assert "not an executable ffmpeg path" in result.stderr


def test_video_finder_does_not_require_ffmpeg_without_a_comparison(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    (vids / "only.mp4").write_bytes(b"\x00single video placeholder")
    missing = tmp_path / "not-ffmpeg"

    result = run_script(
        "find_video_duplicates.py",
        tmp_path,
        "--ffmpeg",
        missing,
        "--ffprobe",
        missing,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Fewer than two videos" in result.stdout
    assert "Would move 0 duplicate(s)" in result.stdout


def test_video_cache_keeps_completed_fingerprints_after_interruption(
    tmp_path: Path, monkeypatch
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    first = vids / "first.mp4"
    second = vids / "second.mp4"
    first.write_bytes(b"first content")
    second.write_bytes(b"second content")
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
    calls = 0

    monkeypatch.setattr(video_duplicates, "resolve_executable", lambda *_: "tool")
    monkeypatch.setattr(video_duplicates, "ffmpeg_version", lambda _: "test-ffmpeg")
    monkeypatch.setattr(
        video_duplicates,
        "discover_videos",
        lambda *_: ([first, second], []),
    )
    monkeypatch.setattr(video_duplicates, "probe_video", lambda *_: probe)

    def interrupt_after_first(*_):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return video_duplicates.DerivedFingerprint("1" * 64, 1, 0)

    monkeypatch.setattr(video_duplicates, "derive_fingerprint", interrupt_after_first)

    with pytest.raises(KeyboardInterrupt):
        video_duplicates.main([str(tmp_path)])

    cached = video_duplicates.load_cached_fingerprints(
        tmp_path,
        CollectionLayout(tmp_path).video_cache,
        "test-ffmpeg",
    )
    assert cached == {
        hashlib.sha256(
            first.read_bytes()
        ).hexdigest(): video_duplicates.DerivedFingerprint("1" * 64, 1, 0)
    }


def test_video_finder_rejects_a_corrupt_cache_before_decoding(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    first = vids / "first.mp4"
    second = vids / "second.mp4"
    first.write_bytes(b"first content")
    second.write_bytes(b"second content")
    CollectionLayout(tmp_path).video_cache.write_bytes(b"not a SQLite database")
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

    monkeypatch.setattr(video_duplicates, "resolve_executable", lambda *_: "tool")
    monkeypatch.setattr(video_duplicates, "ffmpeg_version", lambda _: "test-ffmpeg")
    monkeypatch.setattr(
        video_duplicates, "discover_videos", lambda *_: ([first, second], [])
    )
    monkeypatch.setattr(video_duplicates, "probe_video", lambda *_: probe)
    monkeypatch.setattr(
        video_duplicates,
        "derive_fingerprint",
        lambda *_: pytest.fail("decoding must not start with a corrupt cache"),
    )

    assert video_duplicates.main([str(tmp_path)]) == 1
    assert "Whole-file hash cache cannot be used safely" in caplog.text
    assert "rerun with --no-cache" in caplog.text


def test_video_cache_rejects_malformed_rows(tmp_path: Path) -> None:
    database = CollectionLayout(tmp_path).video_cache
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
        ("bad-hash", video_duplicates.FINGERPRINT_ALGORITHM, "test", "bad", 0, -1),
    )
    connection.commit()
    connection.close()

    with pytest.raises(video_duplicates.VideoInspectionError, match="invalid row"):
        video_duplicates.load_cached_fingerprints(tmp_path, database, "test")


def test_video_cache_reads_legacy_without_writing_and_upgrades_on_next_write(
    tmp_path: Path,
) -> None:
    database = CollectionLayout(tmp_path).video_cache
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE video_fingerprints ("
        "file_sha256 TEXT NOT NULL, algorithm TEXT NOT NULL, "
        "ffmpeg_version TEXT NOT NULL, fingerprint TEXT NOT NULL, "
        "video_frames INTEGER NOT NULL, audio_bytes INTEGER NOT NULL, "
        "PRIMARY KEY (file_sha256, algorithm, ffmpeg_version))"
    )
    first = video_duplicates.DerivedFingerprint("1" * 64, 1, 0)
    second = video_duplicates.DerivedFingerprint("2" * 64, 2, 4)
    connection.execute(
        "INSERT INTO video_fingerprints VALUES (?, ?, ?, ?, ?, ?)",
        (
            "a" * 64,
            video_duplicates.FINGERPRINT_ALGORITHM,
            "test-ffmpeg",
            first.digest,
            first.video_frames,
            first.audio_bytes,
        ),
    )
    connection.commit()
    connection.close()
    legacy_bytes = database.read_bytes()

    assert video_duplicates.load_cached_fingerprints(
        tmp_path, database, "test-ffmpeg"
    ) == {"a" * 64: first}
    assert database.read_bytes() == legacy_bytes

    video_duplicates.save_cached_fingerprints(
        tmp_path, database, "test-ffmpeg", {"b" * 64: second}
    )

    assert video_duplicates.load_cached_fingerprints(
        tmp_path, database, "test-ffmpeg"
    ) == {"a" * 64: first, "b" * 64: second}
    connection = sqlite3.connect(database)
    assert cache_service.detect_schema(connection) == "current"
    assert (
        connection.execute(
            "SELECT name FROM sqlite_schema WHERE name = 'video_fingerprints'"
        ).fetchone()
        is None
    )
    connection.close()


def test_video_cache_read_pins_original_database_during_path_swap(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    cache = CollectionLayout(root).video_cache
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    outside = CollectionLayout(outside_root).video_cache
    displaced = root / "displaced.sqlite3"
    original = video_duplicates.DerivedFingerprint("1" * 64, 1, 0)
    unrelated = video_duplicates.DerivedFingerprint("2" * 64, 2, 0)
    file_hash = "a" * 64
    video_duplicates.save_cached_fingerprints(
        root, cache, "test-ffmpeg", {file_hash: original}
    )
    video_duplicates.save_cached_fingerprints(
        outside_root, outside, "test-ffmpeg", {file_hash: unrelated}
    )
    real_connect = sqlite3.connect
    observed: list[str] = []

    def swap_before_sqlite_read(*args, **kwargs):
        cache.rename(displaced)
        cache.symlink_to(outside)
        connection = real_connect(*args, **kwargs)
        row = connection.execute("SELECT payload_json FROM derived_evidence").fetchone()
        assert row is not None
        observed.append(json.loads(row[0])["digest"])
        return connection

    monkeypatch.setattr(cache_service.sqlite3, "connect", swap_before_sqlite_read)

    with pytest.raises(
        video_duplicates.VideoInspectionError, match="not a private regular file"
    ):
        video_duplicates.load_cached_fingerprints(root, cache, "test-ffmpeg")

    assert observed == [original.digest]


def test_video_cache_writers_serialize_and_merge_completed_updates(
    tmp_path: Path,
) -> None:
    layout = CollectionLayout(tmp_path)
    first = video_duplicates.DerivedFingerprint("1" * 64, 1, 0)
    second = video_duplicates.DerivedFingerprint("2" * 64, 2, 0)
    started = [threading.Event(), threading.Event()]
    finished = [threading.Event(), threading.Event()]
    errors: list[BaseException] = []

    def save(number: int, file_hash: str, value) -> None:
        started[number].set()
        try:
            video_duplicates.save_cached_fingerprints(
                tmp_path,
                layout.video_cache,
                "test-ffmpeg",
                {file_hash: value},
            )
        except BaseException as error:
            errors.append(error)
        finally:
            finished[number].set()

    with cache_service.locked_cache_directory(
        tmp_path, layout.video_cache_lock, exclusive=True
    ):
        threads = [
            threading.Thread(target=save, args=(0, "a" * 64, first)),
            threading.Thread(target=save, args=(1, "b" * 64, second)),
        ]
        for thread in threads:
            thread.start()
        assert all(event.wait(1) for event in started)
        assert not any(event.wait(0.05) for event in finished)
    for thread in threads:
        thread.join(timeout=5)

    assert not errors
    assert all(event.is_set() for event in finished)
    assert video_duplicates.load_cached_fingerprints(
        tmp_path, layout.video_cache, "test-ffmpeg"
    ) == {"a" * 64: first, "b" * 64: second}
    assert not list(tmp_path.glob(".pymo.sqlite3.new.*"))


def test_video_cache_interruption_preserves_public_cache_and_complete_stage(
    tmp_path: Path, monkeypatch
) -> None:
    layout = CollectionLayout(tmp_path)
    first = video_duplicates.DerivedFingerprint("1" * 64, 1, 0)
    second = video_duplicates.DerivedFingerprint("2" * 64, 2, 0)
    video_duplicates.save_cached_fingerprints(
        tmp_path, layout.video_cache, "test-ffmpeg", {"a" * 64: first}
    )
    original_bytes = layout.video_cache.read_bytes()

    def interrupt_before_publication(*_args, **_kwargs) -> None:
        raise cache_service.CacheError("simulated interruption")

    monkeypatch.setattr(
        cache_service, "_publish_generic_stage", interrupt_before_publication
    )

    with pytest.raises(video_duplicates.VideoInspectionError, match="interruption"):
        video_duplicates.save_cached_fingerprints(
            tmp_path,
            layout.video_cache,
            "test-ffmpeg",
            {"b" * 64: second},
        )

    assert layout.video_cache.read_bytes() == original_bytes
    stages = list(tmp_path.glob(".pymo.sqlite3.new.*"))
    assert len(stages) == 1 and stages[0].is_file()
    connection = sqlite3.connect(stages[0])
    staged_rows = connection.execute(
        "SELECT file_sha256 FROM derived_evidence ORDER BY file_sha256"
    ).fetchall()
    connection.close()
    assert staged_rows == [("a" * 64,), ("b" * 64,)]


def test_video_cache_publication_never_writes_through_substituted_path(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "collection"
    outside_root = tmp_path / "outside"
    root.mkdir()
    outside_root.mkdir()
    layout = CollectionLayout(root)
    outside_layout = CollectionLayout(outside_root)
    original = video_duplicates.DerivedFingerprint("1" * 64, 1, 0)
    unrelated = video_duplicates.DerivedFingerprint("9" * 64, 9, 0)
    update = video_duplicates.DerivedFingerprint("2" * 64, 2, 0)
    video_duplicates.save_cached_fingerprints(
        root, layout.video_cache, "test-ffmpeg", {"a" * 64: original}
    )
    video_duplicates.save_cached_fingerprints(
        outside_root,
        outside_layout.video_cache,
        "test-ffmpeg",
        {"f" * 64: unrelated},
    )
    outside_bytes = outside_layout.video_cache.read_bytes()
    displaced = root / "displaced.sqlite3"
    real_rename = cache_service.atomic_cache_rename
    swapped = False

    def substitute_before_publication(*args, **kwargs) -> None:
        nonlocal swapped
        if kwargs.get("exchange") and not swapped:
            swapped = True
            layout.video_cache.rename(displaced)
            layout.video_cache.symlink_to(outside_layout.video_cache)
        real_rename(*args, **kwargs)

    monkeypatch.setattr(
        cache_service, "atomic_cache_rename", substitute_before_publication
    )

    with pytest.raises(
        video_duplicates.VideoInspectionError, match="changed during atomic publication"
    ):
        video_duplicates.save_cached_fingerprints(
            root,
            layout.video_cache,
            "test-ffmpeg",
            {"b" * 64: update},
        )

    assert swapped
    assert layout.video_cache.is_symlink()
    assert displaced.is_file()
    assert outside_layout.video_cache.read_bytes() == outside_bytes
    assert len(list(root.glob(".pymo.sqlite3.new.*"))) == 1


def test_video_cache_rejects_substituted_lock_without_touching_target(
    tmp_path: Path,
) -> None:
    layout = CollectionLayout(tmp_path)
    outside = tmp_path / "outside.lock"
    outside.write_bytes(b"unrelated lock target")
    layout.video_cache_lock.symlink_to(outside)

    with pytest.raises(video_duplicates.VideoInspectionError, match="lock safely"):
        video_duplicates.save_cached_fingerprints(
            tmp_path,
            layout.video_cache,
            "test-ffmpeg",
            {"a" * 64: video_duplicates.DerivedFingerprint("1" * 64, 1, 0)},
        )

    assert outside.read_bytes() == b"unrelated lock target"
    assert not layout.video_cache.exists()
    assert not list(tmp_path.glob(".pymo.sqlite3.new.*"))


def test_video_cache_rechecks_lock_before_publication(
    tmp_path: Path, monkeypatch
) -> None:
    layout = CollectionLayout(tmp_path)
    original = video_duplicates.DerivedFingerprint("1" * 64, 1, 0)
    update = video_duplicates.DerivedFingerprint("2" * 64, 2, 0)
    video_duplicates.save_cached_fingerprints(
        tmp_path, layout.video_cache, "test-ffmpeg", {"a" * 64: original}
    )
    original_cache = layout.video_cache.read_bytes()
    outside = tmp_path / "outside.lock"
    outside.write_bytes(b"unrelated lock target")
    displaced_lock = tmp_path / "displaced.lock"
    real_build = cache_service._build_generic_stage

    def substitute_lock_after_staging(*args, **kwargs):
        result = real_build(*args, **kwargs)
        layout.video_cache_lock.rename(displaced_lock)
        layout.video_cache_lock.symlink_to(outside)
        return result

    monkeypatch.setattr(
        cache_service, "_build_generic_stage", substitute_lock_after_staging
    )

    with pytest.raises(video_duplicates.VideoInspectionError, match="cache lock"):
        video_duplicates.save_cached_fingerprints(
            tmp_path,
            layout.video_cache,
            "test-ffmpeg",
            {"b" * 64: update},
        )

    assert layout.video_cache.read_bytes() == original_cache
    assert outside.read_bytes() == b"unrelated lock target"
    assert displaced_lock.is_file()
    assert len(list(tmp_path.glob(".pymo.sqlite3.new.*"))) == 1


def test_video_inspection_rejects_a_file_changed_during_probe(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "changing.mp4"
    path.write_bytes(b"before")
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

    def mutate_during_probe(*_) -> ProbeInfo:
        path.write_bytes(b"after")
        return probe

    monkeypatch.setattr(video_duplicates, "probe_video", mutate_during_probe)

    with pytest.raises(
        video_duplicates.FileChangedError, match="changed during video inspection"
    ):
        video_duplicates.inspect_video(tmp_path, path, "ffprobe")


def test_decimal_microseconds_rejects_non_finite_values() -> None:
    assert video_duplicates.decimal_microseconds("NaN") is None
    assert video_duplicates.decimal_microseconds("Infinity") is None
    assert video_duplicates.decimal_microseconds("-Infinity") is None


def test_probe_rejects_non_object_stream_entries(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "invalid.mp4"
    path.write_bytes(b"\x00invalid")
    result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps({"streams": [None]}), stderr=""
    )
    monkeypatch.setattr(video_duplicates.subprocess, "run", lambda *_, **__: result)

    descriptor = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(
            video_duplicates.VideoInspectionError, match="invalid stream entry"
        ):
            video_duplicates.probe_video(descriptor, "ffprobe")
    finally:
        os.close(descriptor)


def test_ffmpeg_decode_commands_only_use_pinned_local_file_inputs(
    tmp_path: Path, monkeypatch
) -> None:
    commands: list[list[str]] = []
    inherited_descriptors: list[tuple[int, ...]] = []

    def fake_stream(
        command: list[str],
        consume_stdout,
        timeout: int,
        progress_callback=None,
        pass_fds: tuple[int, ...] = (),
    ) -> None:
        commands.append(command)
        inherited_descriptors.append(pass_fds)
        if progress_callback is not None:
            progress_callback()
        if "framehash" in command:
            consume_stdout(
                b"0, 0, 0, 200000, 4, "
                b"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
            )
        else:
            consume_stdout(b"\x00\x01\x02\x03")

    monkeypatch.setattr(video_duplicates, "_stream_command", fake_stream)
    local_path = tmp_path / "local-video.mp4"
    local_path.write_bytes(b"local video")
    probe = ProbeInfo(
        display_width=64,
        display_height=48,
        duration_us=1_000_000,
        video_start_us=0,
        audio_start_us=0,
        audio_sample_rate=8_000,
        audio_channels=1,
        audio_layout="mono",
        has_audio=True,
    )

    descriptor = os.open(local_path, os.O_RDONLY)
    try:
        video_duplicates.derive_fingerprint(descriptor, probe, "/usr/bin/ffmpeg", 60)
    finally:
        os.close(descriptor)

    assert len(commands) == 2
    for command, pass_fds in zip(commands, inherited_descriptors, strict=True):
        assert command[command.index("-i") + 1] == f"/dev/fd/{descriptor}"
        assert pass_fds == (descriptor,)
        assert command[command.index("-protocol_whitelist") + 1] == "file,pipe"
        assert not {"avfoundation", "x11grab", "gdigrab"}.intersection(command)


def test_video_discovery_pins_classification_during_path_swap(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    vids = root / "vids"
    vids.mkdir(parents=True)
    candidate = vids / "candidate.mp4"
    candidate.write_bytes(b"original video bytes")
    replacement = tmp_path / "replacement.mp4"
    replacement.write_bytes(b"unrelated replacement")
    displaced = vids / "displaced.mp4"
    observed = b""

    class SwappingClassifier(Classifier):
        def classify(
            self, _path: Path, descriptor: int | None = None
        ) -> tuple[str, str]:
            nonlocal observed
            assert descriptor is not None
            candidate.rename(displaced)
            candidate.symlink_to(replacement)
            observed = os.pread(descriptor, 1024, 0)
            return "video", "video/mp4"

    config = load_config(root)
    videos, _ = video_duplicates.discover_videos(
        vids, root, SwappingClassifier(config.classification), config
    )

    assert observed == b"original video bytes"
    assert videos == []


def test_video_inspection_pins_probe_during_path_swap(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "collection"
    vids = root / "vids"
    vids.mkdir(parents=True)
    candidate = vids / "candidate.mp4"
    candidate.write_bytes(b"original video bytes")
    replacement = tmp_path / "replacement.mp4"
    replacement.write_bytes(b"unrelated replacement")
    displaced = vids / "displaced.mp4"
    observed = b""

    payload = {
        "streams": [
            {
                "codec_type": "video",
                "width": 64,
                "height": 48,
                "pix_fmt": "yuv420p",
                "duration": "1.0",
            }
        ],
        "format": {"duration": "1.0"},
    }

    def swap_during_probe(command, **kwargs):
        nonlocal observed
        descriptor = kwargs["pass_fds"][0]
        candidate.rename(displaced)
        candidate.symlink_to(replacement)
        observed = os.pread(descriptor, 1024, 0)
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(video_duplicates.subprocess, "run", swap_during_probe)

    with pytest.raises(
        video_duplicates.FileChangedError, match="changed during video inspection"
    ):
        video_duplicates.inspect_video(root, candidate, "ffprobe")

    assert observed == b"original video bytes"


def test_video_fingerprint_pins_decode_during_path_swap(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "collection"
    vids = root / "vids"
    vids.mkdir(parents=True)
    candidate = vids / "candidate.mp4"
    candidate.write_bytes(b"original video bytes")
    state = video_duplicates.FileState.capture(candidate)
    record = video_duplicates.VideoRecord(
        path=candidate,
        byte_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
        state=state,
        probe=ProbeInfo(
            display_width=64,
            display_height=48,
            duration_us=1_000_000,
            video_start_us=0,
            audio_start_us=None,
            audio_sample_rate=None,
            audio_channels=None,
            audio_layout=None,
            has_audio=False,
        ),
    )
    replacement = tmp_path / "replacement.mp4"
    replacement.write_bytes(b"unrelated replacement")
    displaced = vids / "displaced.mp4"
    observed = b""

    def swap_during_decode(descriptor: int, *_):
        nonlocal observed
        candidate.rename(displaced)
        candidate.symlink_to(replacement)
        observed = os.pread(descriptor, 1024, 0)
        return video_duplicates.DerivedFingerprint("1" * 64, 1, 0)

    monkeypatch.setattr(video_duplicates, "derive_fingerprint", swap_during_decode)

    derived, skipped = video_duplicates.derive_candidate_fingerprints(
        root,
        [record],
        CollectionLayout(root).video_cache,
        "ffmpeg",
        "test-ffmpeg",
        60,
        15,
        True,
    )

    assert observed == b"original video bytes"
    assert derived == {}
    assert skipped and skipped[0][0] == candidate


def test_video_discovery_failure_creates_no_cache_or_action_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    (vids / "clip.mp4").write_bytes(b"synthetic video")

    def fail_discovery(_path: Path) -> tuple[Path, ...]:
        raise DiscoveryError("incomplete discovery")

    monkeypatch.setattr(video_duplicates, "list_directory_complete", fail_discovery)

    assert video_duplicates.main([str(tmp_path), "--apply"]) == 1
    assert (vids / "clip.mp4").is_file()
    assert not (tmp_path / "dups").exists()
    assert not action_log_path(tmp_path).exists()
    assert not (tmp_path / ".pymo.sqlite3").exists()


def test_video_ghost_entry_creates_no_cache_or_action_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    source = vids / "clip.mp4"
    source.write_bytes(b"synthetic video")

    monkeypatch.setattr(
        duplicate_common, "list_directory_complete", lambda _path: (source,)
    )
    monkeypatch.setattr(
        video_duplicates,
        "list_directory_complete",
        lambda _path: (source, vids / "vanished.mp4"),
    )

    assert video_duplicates.main([str(tmp_path), "--apply"]) == 1
    assert source.is_file()
    assert not (tmp_path / "dups").exists()
    assert not action_log_path(tmp_path).exists()
    assert not (tmp_path / ".pymo.sqlite3").exists()
