from __future__ import annotations

import errno
import json
import os
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
FILE_COMMAND = shutil.which("file")
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG or not FFPROBE,
    reason="real video validation requires ffmpeg and ffprobe",
)
requires_file_command = pytest.mark.skipif(
    not FILE_COMMAND,
    reason="descriptor-backed content classification requires the file utility",
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
    # Genuinely damaged media: a real PNG truncated past its header. Plain text
    # in a media-named file is a naming mismatch rather than damage, and is
    # covered separately.
    intact_png = root / "healthy.png"
    (root / "damaged.png").write_bytes(intact_png.read_bytes()[:32])
    (root / "notes.txt").write_text("garden notes", encoding="utf-8")
    (root / ".DS_Store").write_bytes(b"view state")
    before = snapshot(root)

    result = run_script("validate.py", root, "--no-cache")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "Collection validation" in result.stdout
    assert "Files with errors: 1" in result.stdout
    assert "ERROR invalid_image: 1 file(s)" in result.stdout
    assert "Validation did not modify media or action history" in result.stdout
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
    assert report["schema_version"] == 2
    assert report["profile"] == "standard"
    assert report["health"]["files_with_errors"] == 1
    assert report["finding_files"] == []
    assert report["cache"] == {
        "enabled": True,
        "fresh_validation_performed": True,
        "fresh_validation_files": 1,
        "issue": None,
        "location": "collection-local",
        "mode": "fresh",
        "records_reused": 0,
        "records_written": 1,
    }
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


@requires_file_command
def test_discovery_classifies_unknown_extension_through_stable_descriptor(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    path = root / "unknown.data"
    Image.new("RGB", (2, 2), "green").save(path, format="PNG")

    discovery = validate.discover_candidates(root, load_config(root))

    assert len(discovery.candidates) == 1
    assert discovery.candidates[0].detected_kind == "picture"
    assert discovery.candidates[0].extension_kind is None


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
    report = validate.build_report(
        root,
        discovery,
        (),
        validate.ReportOptions(
            full=False, workers=1, show_files=True, show_ignored=False
        ),
    )

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
        root=tmp_path,
        path=path,
        state=validate.FileState.capture(path),
        kind="video",
        extension_kind="video",
        detected_kind="video",
    )

    def change_then_fail(_descriptor: int, _ffprobe: str) -> dict[str, Any]:
        path.write_bytes(b"replacement bytes")
        raise validate.VideoInspectionError("synthetic decoder failure")

    monkeypatch.setattr(validate, "_probe_video", change_then_fail)

    result = validate.validate_video(
        candidate,
        "ffprobe",
        None,
        30,
        container_families=load_config(tmp_path).validation.container_families,
    )

    assert [finding.code for finding in result.findings] == [
        "changed_during_validation"
    ]


def test_image_validation_reads_pinned_descriptor_during_path_swap(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    path = root / "picture.png"
    Image.new("RGB", (2, 2), "green").save(path)
    original_bytes = path.read_bytes()
    outside = tmp_path / "outside.png"
    Image.new("RGB", (2, 2), "blue").save(outside)
    candidate = validate.MediaCandidate(
        root=root,
        path=path,
        state=validate.FileState.capture(path),
        kind="picture",
        extension_kind="picture",
        detected_kind="picture",
    )
    original_open = validate.Image.open
    observed: list[bytes] = []

    def swap_then_open(handle):
        position = handle.tell()
        handle.seek(0)
        observed.append(handle.read())
        handle.seek(position)
        path.unlink()
        path.symlink_to(outside)
        return original_open(handle)

    monkeypatch.setattr(validate.Image, "open", swap_then_open)

    result = validate.validate_image(candidate, False)

    assert observed == [original_bytes]
    assert [finding.code for finding in result.findings] == [
        "changed_during_validation"
    ]


def test_video_validation_reports_missing_codec_and_dimensions(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"synthetic video")
    candidate = validate.MediaCandidate(
        root=tmp_path,
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

    result = validate.validate_video(
        candidate,
        "ffprobe",
        None,
        30,
        container_families=load_config(tmp_path).validation.container_families,
    )
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

    descriptor = os.open(path, os.O_RDONLY)
    try:
        payload = validate._probe_video(descriptor, "ffprobe")
    finally:
        os.close(descriptor)

    assert payload == {"streams": [], "format": {}}
    assert "-show_entries" in observed["command"]
    assert observed["kwargs"]["stdout"] is subprocess.PIPE
    assert observed["kwargs"]["stderr"] is subprocess.DEVNULL
    assert observed["kwargs"]["pass_fds"] == (descriptor,)
    show_entries = observed["command"][observed["command"].index("-show_entries") + 1]
    assert "probe_score" in show_entries


@requires_ffmpeg
def test_video_validation_continues_after_a_corrupt_file(
    tmp_path: Path, run_script
) -> None:
    assert FFMPEG
    root = tmp_path / "media-collection"
    root.mkdir()
    healthy = root / "healthy.mp4"
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
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            healthy,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr
    damaged = root / "damaged.mp4"
    # Genuinely damaged media: a real container truncated past its header, so
    # the content signature still identifies video and the decoder is what
    # fails. Plain text in a media-named file is a naming mismatch, not damage.
    damaged.write_bytes(Path(healthy).read_bytes()[:64])
    before = snapshot(root)

    result = run_script("validate.py", root, "--show-files", "--no-cache")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "Healthy files: 1" in result.stdout
    assert "Files with errors: 1" in result.stdout
    assert "ERROR invalid_video: 1 file(s)" in result.stdout
    assert "damaged.mp4: error invalid_video" in result.stdout
    assert "healthy.mp4" not in result.stdout
    assert snapshot(root) == before
    assert not action_log_path(root).exists()
    assert not CollectionLayout(root).video_cache.exists()


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
            "mpeg4",
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

    result = run_script("validate.py", root, "--full", "--workers", "4", "--no-cache")

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

    def classify_then_change(
        classifier, target: Path, descriptor: int | None = None
    ) -> tuple[str, str]:
        result = original_classify(classifier, target, descriptor)
        target.write_bytes(target.read_bytes() + b"changed")
        return result

    monkeypatch.setattr(validate.Classifier, "classify", classify_then_change)

    discovery = validate.discover_candidates(root, load_config(root))

    assert discovery.candidates == ()
    assert discovery.changed_count == 1


@requires_file_command
def test_non_media_content_with_media_extension_is_not_validated_as_media(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    (root / "caption.jpg").write_text("a caption, not a photograph\n")
    (root / "component.ts").write_text(
        "export const value: number = 1;\nconsole.log(value);\n"
    )
    (root / "notes.mp4").write_text("plain text, not a movie\n")

    discovery = validate.discover_candidates(root, load_config(root))

    assert discovery.candidates == ()
    assert sorted(path.name for path in discovery.mismatched_paths) == [
        "caption.jpg",
        "component.ts",
        "notes.mp4",
    ]
    assert discovery.mismatched_count == 3


@requires_file_command
def test_media_extension_mismatch_warns_without_failing_the_run(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    Image.new("RGB", (2, 2), "green").save(root / "healthy.png")
    (root / "component.ts").write_text("export const value: number = 1;\n")

    result = run_script("validate.py", root, "--show-files", "--no-cache")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "invalid_video" not in result.stdout
    assert "WARNING extension_content_mismatch" in result.stdout
    assert (
        "component.ts: warning extension_content_mismatch" in result.stdout
    ), result.stdout
    assert "Files with errors: 0" in result.stdout


@requires_file_command
def test_media_extension_mismatch_json_counts_a_non_media_file(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    (root / "component.ts").write_text("export const value: number = 1;\n")

    result = run_script("validate.py", root, "--json", "--no-cache")
    report = json.loads(result.stdout)

    assert result.returncode == 0, result.stdout + result.stderr
    assert report["inventory"]["videos"] == 0
    assert report["inventory"]["media_files"] == 0
    assert report["inventory"]["other_files"] == 1
    assert report["health"]["files_with_errors"] == 0
    assert report["health"]["files_with_warnings"] == 1
    codes = {finding["code"] for finding in report["findings"]}
    assert codes == {"extension_content_mismatch"}


@requires_ffmpeg
@requires_file_command
def test_genuine_transport_stream_named_ts_still_validates_as_video(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    clip = root / "broadcast.ts"
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
            "mpeg2video",
            "-pix_fmt",
            "yuv420p",
            "-f",
            "mpegts",
            str(clip),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr

    discovery = validate.discover_candidates(root, load_config(root))

    assert discovery.mismatched_paths == ()
    assert [candidate.path.name for candidate in discovery.candidates] == [
        "broadcast.ts"
    ]
    assert discovery.candidates[0].kind == "video"


def test_media_extension_precedence_needs_a_content_signature(
    tmp_path: Path, monkeypatch
) -> None:
    """Without the content-signature utility there is no meaningful signature.

    The classifier already warns that classification fell back to filenames, and
    the configured extension is then the only available evidence. The filename
    MIME guess that remains is derived from that same name, so it must not
    outrank the extension policy. The guess is forced to a non-video type here
    because platform MIME databases disagree about media extensions, and the
    documented boundary must hold on every platform rather than only on those
    whose database happens to agree.
    """

    root = tmp_path / "media-collection"
    root.mkdir()
    (root / "component.ts").write_text("export const value: number = 1;\n")
    monkeypatch.setattr("pymo.classification.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "pymo.classification.mimetypes.guess_type",
        lambda _name, strict=True: ("text/vnd.trolltech.linguist", None),
    )

    discovery = validate.discover_candidates(root, load_config(root))

    assert discovery.mismatched_paths == ()
    assert [candidate.kind for candidate in discovery.candidates] == ["video"]
    assert discovery.classifier_warning is not None


@requires_file_command
def test_failed_content_signature_does_not_outrank_a_media_extension(
    tmp_path: Path, monkeypatch
) -> None:
    """A utility that fails on one file leaves only a filename guess.

    The utility is present, so no fallback warning is raised, but nothing was
    read from this file's content. The guess must still not be able to report
    configured media as a naming mismatch.
    """

    root = tmp_path / "media-collection"
    root.mkdir()
    (root / "clip.ts").write_bytes(b"\x47" + bytes(187))

    def failing_run(*args: object, **kwargs: object) -> None:
        raise OSError("content signature utility failed")

    monkeypatch.setattr("pymo.classification.subprocess.run", failing_run)
    monkeypatch.setattr(
        "pymo.classification.mimetypes.guess_type",
        lambda _name, strict=True: ("text/vnd.trolltech.linguist", None),
    )

    discovery = validate.discover_candidates(root, load_config(root))

    assert discovery.mismatched_paths == ()
    assert [candidate.kind for candidate in discovery.candidates] == ["video"]
