from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pymo.collection import CollectionLayout

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG or not FFPROBE,
    reason="real FFmpeg integration test requires ffmpeg and ffprobe",
)


def run_pymo(command: str, *arguments: object) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(SOURCE_ROOT)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pymo",
            "--no-timestamps",
            command,
            *(str(item) for item in arguments),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def run_cache(*arguments: object) -> subprocess.CompletedProcess[str]:
    return run_pymo("cache", *arguments)


def make_video(path: Path) -> None:
    assert FFMPEG
    result = subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=64x48:rate=5:duration=0.4",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            path,
        ],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_empty_video_warm_creates_no_collection_state(tmp_path: Path) -> None:
    (tmp_path / "vids").mkdir()

    result = run_cache("warm", "videos", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "No video content required cache warming" in result.stdout
    assert list(tmp_path.iterdir()) == [tmp_path / "vids"]


@requires_ffmpeg
def test_video_warm_populates_and_reuses_collection_cache(tmp_path: Path) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    make_video(vids / "garden.mp4")
    layout = CollectionLayout(tmp_path)

    first = run_cache("warm", "videos", tmp_path)
    second = run_cache("warm", "videos", tmp_path)

    assert first.returncode == 0, first.stdout + first.stderr
    assert "0 reusable record(s); 1 hash(es) required" in first.stdout
    assert "0 reusable record(s); 1 fingerprint(s) required" in first.stdout
    assert "1 new record(s) persisted" in first.stdout
    assert "complete discovered-video coverage" in first.stdout
    assert second.returncode == 0, second.stdout + second.stderr
    assert "1 reusable record(s); 0 hash(es) required" in second.stdout
    assert "1 reusable record(s); 0 fingerprint(s) required" in second.stdout
    assert layout.derived_cache.is_file()
    assert layout.derived_cache_lock.is_file()
    assert not layout.action_log.exists()
    assert not layout.dups.exists()


@requires_ffmpeg
def test_video_warm_can_write_only_to_an_explicit_external_cache(
    tmp_path: Path,
) -> None:
    collection = tmp_path / "collection"
    vids = collection / "vids"
    vids.mkdir(parents=True)
    make_video(vids / "harbor.mp4")
    external = tmp_path / "derived"
    external.mkdir()
    database = external / "portable.sqlite3"

    result = run_cache("warm", "videos", collection, "--cache", database)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Cache location: explicit" in result.stdout
    assert database.is_file()
    assert database.with_name(f"{database.name}.lock").is_file()
    assert not CollectionLayout(collection).derived_cache.exists()
    assert not CollectionLayout(collection).derived_cache_lock.exists()
    assert not CollectionLayout(collection).action_log.exists()
    assert sorted(path.name for path in collection.iterdir()) == ["vids"]
    assert str(collection) not in result.stdout + result.stderr

    shutil.copyfile(vids / "harbor.mp4", vids / "harbor-copy.mp4")
    finder = run_pymo(
        "find-video-duplicates",
        collection,
        "--cache",
        database,
        "--summary",
    )
    assert finder.returncode == 0, finder.stdout + finder.stderr
    assert "1 reusable record(s); 1 hash(es) required" in finder.stdout
    assert "1 reusable record(s); 0 fingerprint(s) required" in finder.stdout
    assert not CollectionLayout(collection).derived_cache.exists()
    assert not CollectionLayout(collection).derived_cache_lock.exists()


@requires_ffmpeg
def test_video_warm_returns_incomplete_for_unreadable_media_without_naming_it(
    tmp_path: Path,
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    make_video(vids / "healthy.mp4")
    damaged = vids / "damaged.mp4"
    make_video(damaged)
    damaged.write_bytes(damaged.read_bytes()[:128])

    result = run_cache("warm", "videos", tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "Uncached or unreadable files: 1" in result.stdout
    assert "incomplete media coverage" in result.stderr
    assert "damaged.mp4" not in result.stdout + result.stderr
    assert CollectionLayout(tmp_path).derived_cache.is_file()
    assert not CollectionLayout(tmp_path).action_log.exists()

    disclosed = run_cache("warm", "videos", tmp_path, "--show-files")
    assert disclosed.returncode == 1
    assert "vids/damaged.mp4" in disclosed.stdout


def test_video_warm_rejects_a_missing_explicit_cache_parent_without_state(
    tmp_path: Path,
) -> None:
    (tmp_path / "vids").mkdir()
    database = tmp_path / "missing" / "cache.sqlite3"

    result = run_cache("warm", "videos", tmp_path, "--cache", database)

    assert result.returncode == 2
    assert "parent must be an existing regular directory" in result.stderr
    assert not database.parent.exists()
    assert list(tmp_path.iterdir()) == [tmp_path / "vids"]
