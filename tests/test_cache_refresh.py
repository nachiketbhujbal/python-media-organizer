from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from pymo.cache import service as cache_service
from pymo.cache.images import IMAGE_PIXEL_EVIDENCE_TYPE
from pymo.cache.validation import VALIDATION_EVIDENCE_TYPE
from pymo.collection import CollectionLayout

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG or not FFPROBE,
    reason="real video cache refresh test requires ffmpeg and ffprobe",
)


def run_cache(*arguments: object) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(SOURCE_ROOT)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pymo",
            "--no-timestamps",
            "cache",
            *(str(item) for item in arguments),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def make_image(path: Path, color: str = "green") -> None:
    Image.new("RGB", (8, 6), color).save(path)


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
            "testsrc2=size=48x32:rate=5:duration=0.4",
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


def test_image_refresh_recomputes_selected_records_and_preserves_unrelated_evidence(
    tmp_path: Path,
) -> None:
    pics = tmp_path / "pics"
    pics.mkdir()
    make_image(pics / "fern.png")
    layout = CollectionLayout(tmp_path)
    seeded = run_cache("warm", "images", tmp_path)
    assert seeded.returncode == 0, seeded.stdout + seeded.stderr
    future_record = cache_service.DerivedEvidence(
        file_sha256="0" * 64,
        evidence_type="future-evidence",
        algorithm="future-v1",
        runtime="local",
        payload_json='{"value":1}',
    )
    cache_service.publish_cache_update(
        layout.derived_cache,
        lambda connection: cache_service.upsert_derived_evidence(
            connection, (future_record,)
        ),
    )

    refreshed = run_cache("refresh", "images", tmp_path)

    assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
    assert "Whole-file hash cache refresh: 0 reusable record(s)" in refreshed.stdout
    assert "Displayed-pixel cache refresh: 0 compatible record(s)" in refreshed.stdout
    assert "0 reused; 1 computed; 1 refreshed record(s) persisted" in refreshed.stdout
    assert "Image cache refresh summary" in refreshed.stdout
    contents = cache_service.read_coordinated_cache(layout.derived_cache)
    assert contents is not None
    assert {record.evidence_type for record in contents.evidence} == {
        IMAGE_PIXEL_EVIDENCE_TYPE,
        "future-evidence",
    }
    assert not layout.action_log.exists()
    assert not layout.dups.exists()


def test_validation_refresh_is_fresh_and_keeps_profiles_separate(
    tmp_path: Path,
) -> None:
    make_image(tmp_path / "willow.png")
    layout = CollectionLayout(tmp_path)

    first = run_cache("refresh", "validation-standard", tmp_path)
    second = run_cache("refresh", "validation-standard", tmp_path)
    full = run_cache("refresh", "validation-full", tmp_path)

    for result in (first, second, full):
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Compatible prior records reused: 0" in result.stdout
        assert "Files freshly validated: 1" in result.stdout
    contents = cache_service.read_coordinated_cache(layout.derived_cache)
    assert contents is not None
    validation_records = [
        record
        for record in contents.evidence
        if record.evidence_type == VALIDATION_EVIDENCE_TYPE
    ]
    assert len(validation_records) == 2
    assert not layout.action_log.exists()
    assert not layout.dups.exists()


def test_validation_refresh_supports_external_cache_without_collection_state(
    tmp_path: Path,
) -> None:
    collection = tmp_path / "media-collection"
    collection.mkdir()
    make_image(collection / "cedar.png")
    external = tmp_path / "derived"
    external.mkdir()
    database = external / "portable.sqlite3"

    result = run_cache(
        "refresh", "validation-standard", collection, "--cache", database
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert database.is_file()
    assert database.with_name(f"{database.name}.lock").is_file()
    assert not CollectionLayout(collection).derived_cache.exists()
    assert not CollectionLayout(collection).derived_cache_lock.exists()
    assert not CollectionLayout(collection).action_log.exists()


def test_refresh_rejects_target_specific_options_before_writing_state(
    tmp_path: Path,
) -> None:
    (tmp_path / "pics").mkdir()

    image_workers = run_cache("refresh", "images", tmp_path, "--workers", 2)
    validation_tools = run_cache(
        "refresh",
        "validation-standard",
        tmp_path,
        "--ffmpeg",
        tmp_path / "tool",
    )

    assert image_workers.returncode == 2
    assert "used only by validation cache refresh" in image_workers.stderr
    assert validation_tools.returncode == 2
    assert "not used by validation cache refresh" in validation_tools.stderr
    assert list(tmp_path.iterdir()) == [tmp_path / "pics"]


@requires_ffmpeg
def test_video_refresh_recomputes_video_evidence_and_preserves_image_evidence(
    tmp_path: Path,
) -> None:
    pics = tmp_path / "pics"
    vids = tmp_path / "vids"
    pics.mkdir()
    vids.mkdir()
    make_image(pics / "maple.png")
    video = vids / "harbor.mp4"
    make_video(video)
    original_video = video.read_bytes()
    layout = CollectionLayout(tmp_path)
    seeded = run_cache("warm", "all", tmp_path)
    assert seeded.returncode == 0, seeded.stdout + seeded.stderr

    refreshed = run_cache("refresh", "videos", tmp_path)

    assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
    assert "Whole-file hash cache refresh: 0 reusable record(s)" in refreshed.stdout
    assert "Video probe cache refresh: 0 compatible record(s)" in refreshed.stdout
    assert "Fingerprint cache refresh: 0 reusable record(s)" in refreshed.stdout
    assert "Video cache refresh summary" in refreshed.stdout
    contents = cache_service.read_coordinated_cache(layout.derived_cache)
    assert contents is not None
    assert IMAGE_PIXEL_EVIDENCE_TYPE in {
        record.evidence_type for record in contents.evidence
    }
    assert video.read_bytes() == original_video
    assert not layout.action_log.exists()
    assert not layout.dups.exists()
