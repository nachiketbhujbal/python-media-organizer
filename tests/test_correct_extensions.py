from __future__ import annotations

import errno
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from pymo import correct_extensions, discovery
from pymo.action_log import action_log_path
from pymo.config import load_config


def make_transport_stream(path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None, "the release test environment requires FFmpeg"
    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=16x16:d=0.25",
            "-c:v",
            "mpeg2video",
            "-f",
            "mpegts",
            "-y",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def make_mp4(path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None, "the release test environment requires FFmpeg"
    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=16x16:d=0.25",
            "-c:v",
            "mpeg4",
            "-f",
            "mp4",
            "-y",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_image_correction_is_preview_first_logged_and_reversible(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "collection"
    incoming = root / "incoming"
    incoming.mkdir(parents=True)
    source = incoming / "garden.jpg"
    Image.new("RGB", (3, 2), "blue").save(source, format="PNG")
    original_bytes = source.read_bytes()

    preview = run_script("correct_extensions.py", root)

    assert preview.returncode == 0, preview.stdout + preview.stderr
    assert "would correct extension" in preview.stdout
    assert "garden.png" in preview.stdout
    assert source.read_bytes() == original_bytes
    assert not action_log_path(root).exists()

    applied = run_script("correct_extensions.py", root, "--apply")

    target = incoming / "garden.png"
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert not source.exists()
    assert target.read_bytes() == original_bytes
    events = [
        json.loads(line)
        for line in action_log_path(root).read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["tool"] == "correct_extensions"
    assert events[1]["action"]["operation"] == "RENAME"

    undo_preview = run_script("correct_extensions.py", root, "--undo")
    assert undo_preview.returncode == 0
    assert target.exists()

    undone = run_script("correct_extensions.py", root, "--undo", "--apply")
    assert undone.returncode == 0, undone.stdout + undone.stderr
    assert source.read_bytes() == original_bytes
    assert not target.exists()


def test_valid_image_synonyms_remain_unchanged(tmp_path: Path, run_script) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    jpeg = root / "photo.jpeg"
    tiff = root / "scan.tiff"
    Image.new("RGB", (2, 2), "red").save(jpeg, format="JPEG")
    Image.new("RGB", (2, 2), "green").save(tiff, format="TIFF")

    result = run_script("correct_extensions.py", root, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Corrected 0 media extension(s)" in result.stdout
    assert "Already truthful: 2 media file(s)" in result.stdout
    assert jpeg.exists()
    assert tiff.exists()
    assert not action_log_path(root).exists()


def test_correction_uses_collision_safe_numbering(tmp_path: Path, run_script) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "photo.jpg"
    occupied = root / "photo.png"
    Image.new("RGB", (2, 2), "blue").save(source, format="PNG")
    Image.new("RGB", (2, 2), "green").save(occupied, format="PNG")
    occupied_bytes = occupied.read_bytes()

    result = run_script("correct_extensions.py", root, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / "photo (1).png").exists()
    assert occupied.read_bytes() == occupied_bytes


def test_real_transport_stream_receives_canonical_ts_extension(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "clip.mp4"
    make_transport_stream(source)
    original_bytes = source.read_bytes()

    result = run_script("correct_extensions.py", root, "--apply")

    target = root / "clip.ts"
    assert result.returncode == 0, result.stdout + result.stderr
    assert target.read_bytes() == original_bytes
    assert not source.exists()


def test_missing_ffprobe_stops_before_state(tmp_path: Path, run_script) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "clip.mp4"
    make_transport_stream(source)

    result = run_script(
        "correct_extensions.py", root, "--ffprobe", root / "missing-ffprobe"
    )

    assert result.returncode == 2
    assert source.exists()
    assert not action_log_path(root).exists()


def test_shared_video_family_is_left_ambiguous(tmp_path: Path, run_script) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "clip.ts"
    make_mp4(source)
    original_bytes = source.read_bytes()

    result = run_script("correct_extensions.py", root, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Corrected 0 media extension(s)" in result.stdout
    assert (
        "Unsupported or ambiguous extension evidence: 1 media file(s)" in result.stdout
    )
    assert source.read_bytes() == original_bytes
    assert not action_log_path(root).exists()


def test_non_media_ts_never_invokes_ffprobe(tmp_path: Path, run_script) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "component.ts"
    source.write_text("export const answer = 42;\n", encoding="utf-8")

    result = run_script(
        "correct_extensions.py", root, "--ffprobe", root / "missing-ffprobe"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Would correct 0 media extension(s)" in result.stdout
    assert source.exists()
    assert not action_log_path(root).exists()


def test_custom_classification_extension_remains_untouched(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "photo.garden"
    Image.new("RGB", (2, 2), "blue").save(source, format="PNG")
    original_bytes = source.read_bytes()
    (root / ".pymo.toml").write_text(
        'version = 1\n[classification]\nimage_extensions = [".garden"]\n',
        encoding="utf-8",
    )

    result = run_script("correct_extensions.py", root, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Corrected 0 media extension(s)" in result.stdout
    assert "Unsupported or ambiguous extension evidence: 1" in result.stdout
    assert source.read_bytes() == original_bytes
    assert not (root / "photo.png").exists()
    assert not action_log_path(root).exists()


def test_corrupt_media_is_counted_and_left_untouched(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "broken.jpg"
    # Keep a meaningful image signature so classification reaches the decoder;
    # arbitrary damaged bytes may truthfully classify as non-media instead.
    source.write_bytes(b"\x89PNG\r\n\x1a\nnot-a-complete-image")

    result = run_script("correct_extensions.py", root, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Corrected 0 media extension(s)" in result.stdout
    assert "could not be inspected conclusively: 1 file(s)" in result.stdout
    assert source.exists()
    assert not action_log_path(root).exists()


def test_dups_and_ignored_files_remain_private_and_untouched(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "collection"
    duplicate = root / "dups" / "pics" / "duplicate.jpg"
    ignored = root / "incoming" / "private.jpg"
    duplicate.parent.mkdir(parents=True)
    ignored.parent.mkdir()
    Image.new("RGB", (2, 2), "blue").save(duplicate, format="PNG")
    Image.new("RGB", (2, 2), "green").save(ignored, format="PNG")
    (root / ".pymo.toml").write_text(
        'version = 1\n[ignore]\nfiles = ["private.jpg"]\n', encoding="utf-8"
    )

    result = run_script("correct_extensions.py", root, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ignored by configuration: 2 path(s)." in result.stdout
    assert "private.jpg" not in result.stdout
    assert duplicate.exists()
    assert ignored.exists()
    assert not action_log_path(root).exists()


def test_incomplete_discovery_stops_before_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "photo.jpg"
    Image.new("RGB", (2, 2), "blue").save(source, format="PNG")

    def incomplete_walk(_root: Path, *, topdown: bool, onerror):
        assert topdown
        yield str(root), [], [source.name]
        onerror(OSError(errno.EACCES, "permission denied", str(root / "closed")))

    monkeypatch.setattr(discovery.os, "walk", incomplete_walk)

    assert correct_extensions.main([str(root), "--apply"]) == 1
    assert source.exists()
    assert not action_log_path(root).exists()


def test_concurrent_change_stops_before_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "photo.jpg"
    Image.new("RGB", (2, 2), "blue").save(source, format="PNG")
    inspect = correct_extensions.inspect_image_format

    def replace_after_inspection(descriptor: int) -> str:
        result = inspect(descriptor)
        replacement = root / "replacement.jpg"
        Image.new("RGB", (2, 2), "red").save(replacement, format="JPEG")
        os.replace(replacement, source)
        return result

    monkeypatch.setattr(
        correct_extensions, "inspect_image_format", replace_after_inspection
    )

    assert correct_extensions.main([str(root), "--apply"]) == 1
    assert source.exists()
    assert not (root / "photo.png").exists()
    assert not action_log_path(root).exists()


def test_later_rename_blocks_extension_undo(tmp_path: Path, run_script) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "IMG_20200102_030405.jpg"
    Image.new("RGB", (2, 2), "blue").save(source, format="PNG")

    assert run_script("correct_extensions.py", root, "--apply").returncode == 0
    assert run_script("rename_media.py", root, "--apply").returncode == 0

    blocked = run_script("correct_extensions.py", root, "--undo", "--apply")

    assert blocked.returncode == 1
    assert "rename_media" in blocked.stderr
    assert run_script("rename_media.py", root, "--undo", "--apply").returncode == 0
    final = run_script("correct_extensions.py", root, "--undo", "--apply")
    assert final.returncode == 0, final.stdout + final.stderr
    assert source.exists()


def test_final_verification_rehashes_the_stable_target(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "photo.jpg"
    Image.new("RGB", (2, 2), "blue").save(source, format="PNG")
    analysis = correct_extensions.analyze_corrections(root, load_config(root))

    correct_extensions.apply_correction_plan(root, analysis.plan)
    target = root / "photo.png"
    target.write_bytes(b"changed after apply")

    assert correct_extensions.verify_correction_plan(root, analysis.plan) == (
        analysis.plan[0],
    )


def test_final_verification_reports_a_missing_target(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    source = root / "photo.jpg"
    Image.new("RGB", (2, 2), "blue").save(source, format="PNG")
    analysis = correct_extensions.analyze_corrections(root, load_config(root))

    correct_extensions.apply_correction_plan(root, analysis.plan)
    (root / "photo.png").unlink()

    assert correct_extensions.verify_correction_plan(root, analysis.plan) == (
        analysis.plan[0],
    )
