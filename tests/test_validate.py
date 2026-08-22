from __future__ import annotations

import errno
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from pymo import validate
from pymo.action_log import action_log_path
from pymo.collection import CollectionLayout
from pymo.config import load_config

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG or not FFPROBE,
    reason="real video validation requires ffmpeg and ffprobe",
)


def snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
        if not path.is_symlink()
    }


def test_validation_reports_errors_without_paths_or_writes(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    Image.new("RGB", (3, 2), "green").save(root / "healthy.png")
    (root / "damaged.png").write_bytes(b"not an image")
    (root / "notes.txt").write_text("garden notes", encoding="utf-8")
    (root / ".DS_Store").write_bytes(b"view state")
    before = snapshot(root)

    result = run_script("validate.py", root)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "Collection validation" in result.stdout
    assert "Files with errors: 1" in result.stdout
    assert "ERROR invalid_image: 1 file(s)" in result.stdout
    assert "Validation is report-only; no files were changed" in result.stdout
    assert "healthy.png" not in result.stdout
    assert "damaged.png" not in result.stdout
    assert ".DS_Store" not in result.stdout
    assert str(root) not in result.stdout
    assert snapshot(root) == before
    assert not action_log_path(root).exists()
    assert not CollectionLayout(root).video_cache.exists()


def test_validation_path_display_is_explicit_and_collection_relative(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    pictures = root / "incoming"
    pictures.mkdir(parents=True)
    Image.new("RGB", (2, 2), "blue").save(pictures / "mismatch.jpg", format="PNG")

    result = run_script("validate.py", root, "--show-files")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "WARNING extension_content_mismatch" in result.stdout
    assert "incoming/mismatch.jpg: warning extension_content_mismatch" in result.stdout
    assert str(root) not in result.stdout.split("Affected files:", 1)[1]


def test_validation_json_is_path_private_and_stable(tmp_path: Path, run_script) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    (root / "empty.png").write_bytes(b"")

    private = run_script("validate.py", root, "--json")
    explicit = run_script("validate.py", root, "--json", "--show-files")

    assert private.returncode == 1
    report = json.loads(private.stdout)
    assert report["schema_version"] == 1
    assert report["profile"] == "standard"
    assert report["health"]["files_with_errors"] == 1
    assert report["finding_files"] == []
    assert "empty.png" not in private.stdout
    shown = json.loads(explicit.stdout)
    assert shown["finding_files"][0]["path"] == "empty.png"


def test_validation_reports_animated_images_without_treating_them_as_broken(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    first = Image.new("RGB", (2, 2), "green")
    second = Image.new("RGB", (2, 2), "blue")
    first.save(root / "animated.gif", save_all=True, append_images=[second])

    result = run_script("validate.py", root, "--full")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Profile: full" in result.stdout
    assert "Animated or multi-page images: 1" in result.stdout
    assert "Files with errors: 0" in result.stdout


def test_validation_does_not_require_video_tools_for_images(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    Image.new("RGB", (2, 2), "green").save(root / "picture.png")
    monkeypatch.setattr(
        validate,
        "resolve_executable",
        lambda *_: pytest.fail("video tools are not needed for image-only validation"),
    )

    assert validate.main([str(root)]) == 0


def test_validation_rejects_unsafe_worker_counts(tmp_path: Path, run_script) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()

    for workers in ("0", "33"):
        result = run_script("validate.py", root, "--workers", workers)
        assert result.returncode == 2
        assert "--workers must be between 1 and 32" in result.stderr


def test_validation_honors_ignore_and_symlink_rules(tmp_path: Path, run_script) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    protected = root / "protected.png"
    protected.write_bytes(b"not inspected")
    target = root / "target.png"
    Image.new("RGB", (2, 2), "green").save(target)
    (root / "linked.png").symlink_to(target)
    (root / ".pymo.toml").write_text(
        'version = 1\n\n[ignore]\nfiles = ["protected.png"]\n',
        encoding="utf-8",
    )

    result = run_script("validate.py", root, "--show-ignored")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ignored by configuration: 2 path(s)" in result.stdout
    assert "protected.png" in result.stdout
    assert "linked.png" not in result.stdout
    assert "symbolic_link_skipped" in result.stdout

    explicit = run_script("validate.py", root, "--show-files")

    assert explicit.returncode == 0, explicit.stdout + explicit.stderr
    assert "linked.png: warning symbolic_link_skipped" in explicit.stdout


def test_validation_does_not_require_video_tools_for_empty_videos(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    (root / "empty.mp4").write_bytes(b"")
    monkeypatch.setattr(
        validate,
        "resolve_executable",
        lambda *_: pytest.fail("empty videos do not need native video tools"),
    )

    assert validate.main([str(root)]) == 1


def test_discovery_records_directory_walk_errors(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    blocked = root / "closed"

    def inaccessible_walk(
        _root: Path, *, topdown: bool, onerror
    ) -> list[tuple[str, list[str], list[str]]]:
        assert topdown
        onerror(OSError(errno.EACCES, "permission denied", str(blocked)))
        return []

    monkeypatch.setattr(validate.os, "walk", inaccessible_walk)

    discovery = validate.discover_candidates(root, load_config(root))
    report = validate.build_report(root, discovery, (), False, 1, True, False)

    assert discovery.unreadable_count == 1
    assert discovery.unreadable_paths == (blocked,)
    assert report["health"]["files_with_errors"] == 1
    assert report["finding_files"][0]["path"] == "closed"


def test_video_change_takes_precedence_over_decoder_failure(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"original bytes")
    candidate = validate.MediaCandidate(
        path=path,
        state=validate.FileState.capture(path),
        kind="video",
        extension_kind="video",
        detected_kind="video",
    )

    def change_then_fail(_path: Path, _ffprobe: str) -> dict[str, Any]:
        path.write_bytes(b"replacement bytes")
        raise validate.VideoInspectionError("synthetic decoder failure")

    monkeypatch.setattr(validate, "_probe_video", change_then_fail)

    result = validate.validate_video(candidate, "ffprobe", None, 30)

    assert [finding.code for finding in result.findings] == [
        "changed_during_validation"
    ]


def test_video_validation_reports_missing_codec_and_dimensions(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"synthetic video")
    candidate = validate.MediaCandidate(
        path=path,
        state=validate.FileState.capture(path),
        kind="video",
        extension_kind="video",
        detected_kind="video",
    )
    monkeypatch.setattr(
        validate,
        "_probe_video",
        lambda *_: {
            "streams": [{"codec_type": "video", "width": 0}],
            "format": {"duration": "1.0"},
        },
    )

    result = validate.validate_video(candidate, "ffprobe", None, 30)
    codes = {finding.code for finding in result.findings}

    assert "missing_video_codec" in codes
    assert "invalid_video_dimensions" in codes


def test_video_probe_selects_metadata_and_discards_tool_diagnostics(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"synthetic video")
    observed: dict[str, Any] = {}

    def completed(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, '{"streams":[],"format":{}}')

    monkeypatch.setattr(validate.subprocess, "run", completed)

    payload = validate._probe_video(path, "ffprobe")

    assert payload == {"streams": [], "format": {}}
    assert "-show_entries" in observed["command"]
    assert observed["kwargs"]["stdout"] is subprocess.PIPE
    assert observed["kwargs"]["stderr"] is subprocess.DEVNULL


@requires_ffmpeg
def test_full_video_validation_uses_one_decode_worker_and_stays_read_only(
    tmp_path: Path, run_script
) -> None:
    assert FFMPEG
    root = tmp_path / "media-collection"
    root.mkdir()
    video = root / "healthy.mp4"
    generated = subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=32x24:rate=4:duration=0.5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            video,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr
    before = video.read_bytes()

    result = run_script("validate.py", root, "--full", "--workers", "4")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Profile: full (1 worker(s))" in result.stdout
    assert "Healthy files: 1" in result.stdout
    assert video.read_bytes() == before
    assert not action_log_path(root).exists()
    assert not CollectionLayout(root).video_cache.exists()


def test_validation_discovery_omits_a_changing_file(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    path = root / "changing.png"
    Image.new("RGB", (2, 2), "green").save(path)
    original_classify = validate.Classifier.classify

    def classify_then_change(classifier, target: Path) -> tuple[str, str]:
        result = original_classify(classifier, target)
        target.write_bytes(target.read_bytes() + b"changed")
        return result

    monkeypatch.setattr(validate.Classifier, "classify", classify_then_change)

    discovery = validate.discover_candidates(root, load_config(root))

    assert discovery.candidates == ()
    assert discovery.changed_count == 1
