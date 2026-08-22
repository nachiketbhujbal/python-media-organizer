from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

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
