from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pymo import validate
from pymo.config import load_config

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
FILE_COMMAND = shutil.which("file")
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG or not FFPROBE,
    reason="real container validation requires ffmpeg and ffprobe",
)
requires_file_command = pytest.mark.skipif(
    not FILE_COMMAND,
    reason="container CLI classification requires the file utility",
)


def make_muxed_video(path: Path, muxer: str) -> None:
    assert FFMPEG
    codec = "mpeg2video" if muxer in {"mpeg2video", "mpegts"} else "mpeg4"
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
            codec,
            "-pix_fmt",
            "yuv420p",
            "-f",
            muxer,
            path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr


@pytest.mark.parametrize(
    ("filename", "kind", "format_data", "expected"),
    [
        (
            "clip.mp4",
            "video",
            {"format_name": "matroska,webm", "probe_score": 100},
            True,
        ),
        (
            "clip.mov",
            "video",
            {
                "format_name": "mp4,mov,m4a,3gp,3g2,mj2",
                "probe_score": 100,
            },
            False,
        ),
        (
            "clip.mp4",
            "video",
            {"format_name": "matroska,webm", "probe_score": 50},
            True,
        ),
        (
            "clip.mp4",
            "video",
            {"format_name": "matroska,webm", "probe_score": 49},
            False,
        ),
        (
            "clip.mp4",
            "video",
            {"format_name": "matroska,webm", "probe_score": 101},
            False,
        ),
        (
            "clip.mp4",
            "video",
            {"format_name": "matroska,webm", "probe_score": "100"},
            False,
        ),
        (
            "clip.mp4",
            "video",
            {"format_name": "matroska,webm", "probe_score": True},
            False,
        ),
        (
            "clip.mp4",
            "video",
            {"format_name": "matroska,,webm", "probe_score": 100},
            False,
        ),
        ("clip.mp4", "video", {"probe_score": 100}, False),
        (
            "clip.city",
            "video",
            {"format_name": "matroska,webm", "probe_score": 100},
            False,
        ),
        (
            "clip.mp4",
            "picture",
            {"format_name": "matroska,webm", "probe_score": 100},
            False,
        ),
    ],
)
def test_container_extension_finding_requires_confident_mapped_video_evidence(
    tmp_path: Path,
    filename: str,
    kind: str,
    format_data: dict[str, object],
    expected: bool,
) -> None:
    path = tmp_path / filename
    path.write_bytes(b"synthetic media")
    candidate = validate.MediaCandidate(
        root=tmp_path,
        path=path,
        state=validate.FileState.capture(path),
        kind=kind,  # type: ignore[arg-type]
        extension_kind=kind,  # type: ignore[arg-type]
        detected_kind=kind,
    )

    finding = validate._container_extension_finding(
        candidate,
        {"format": format_data},
        load_config(tmp_path).validation.container_families,
    )

    assert (finding is not None) is expected
    if finding is not None:
        assert finding.severity == "warning"
        assert finding.code == "container_extension_mismatch"
        assert finding.description == (
            "video container does not match the filename extension"
        )


@pytest.mark.parametrize(
    "failure",
    ["synthetic full-decode failure", "synthetic full-decode timeout"],
)
def test_full_decode_failure_preserves_probe_and_container_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
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
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "mpeg4",
                    "width": 32,
                    "height": 24,
                },
                {"codec_type": "subtitle"},
            ],
            "format": {
                "duration": "1.0",
                "format_name": "matroska,webm",
                "probe_score": 100,
            },
        },
    )

    def fail_decode(*_args: object) -> None:
        raise validate.VideoInspectionError(failure)

    monkeypatch.setattr(validate, "_full_video_decode", fail_decode)

    result = validate.validate_video(
        candidate,
        "ffprobe",
        "ffmpeg",
        30,
        container_families=load_config(tmp_path).validation.container_families,
    )

    assert [finding.code for finding in result.findings] == [
        "additional_streams",
        "container_extension_mismatch",
        "invalid_video",
    ]


@requires_ffmpeg
@pytest.mark.parametrize(
    ("filename", "muxer", "expected_family", "expected_mismatch"),
    [
        ("misnamed-transport.mp4", "mpegts", "mpegts", True),
        ("misnamed-matroska.mp4", "matroska", "matroska,webm", True),
        ("misnamed-raw.mp4", "mpeg2video", "mpegvideo", True),
        ("correct.mp4", "mp4", "mov,mp4,m4a,3gp,3g2,mj2", False),
        ("correct.mov", "mov", "mov,mp4,m4a,3gp,3g2,mj2", False),
        ("correct.mkv", "matroska", "matroska,webm", False),
        ("correct.ts", "mpegts", "mpegts", False),
        ("shared.webm", "matroska", "matroska,webm", False),
        ("raw.mpg", "mpeg2video", "mpegvideo", False),
    ],
)
def test_real_muxers_apply_the_confident_container_family_boundary(
    tmp_path: Path,
    filename: str,
    muxer: str,
    expected_family: str,
    expected_mismatch: bool,
) -> None:
    assert FFPROBE
    path = tmp_path / filename
    make_muxed_video(path, muxer)
    with path.open("rb") as stream:
        descriptor = stream.fileno()
        independent = subprocess.run(
            [
                FFPROBE,
                "-v",
                "error",
                "-show_entries",
                "format=format_name,probe_score",
                "-of",
                "json",
                f"/dev/fd/{descriptor}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            pass_fds=(descriptor,),
        )
    assert independent.returncode == 0, independent.stderr
    independent_format = json.loads(independent.stdout)["format"]
    assert independent_format["format_name"] == expected_family
    assert 50 <= independent_format["probe_score"] <= 100

    candidate = validate.MediaCandidate(
        root=tmp_path,
        path=path,
        state=validate.FileState.capture(path),
        kind="video",
        extension_kind="video",
        detected_kind="video",
    )
    result = validate.validate_video(
        candidate,
        FFPROBE,
        None,
        30,
        container_families=load_config(tmp_path).validation.container_families,
    )

    codes = {finding.code for finding in result.findings}
    assert ("container_extension_mismatch" in codes) is expected_mismatch
    if muxer == "mpegts" and filename.endswith(".mp4"):
        discovery = validate.discover_candidates(tmp_path, load_config(tmp_path))
        assert discovery.mismatched_paths == ()
        assert [item.path for item in discovery.candidates] == [path]


@requires_ffmpeg
@requires_file_command
def test_container_mismatch_json_is_warning_only_and_path_private(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    path = root / "misnamed.mp4"
    make_muxed_video(path, "matroska")
    (root / "component.ts").write_text(
        "export const value: number = 1;\n", encoding="utf-8"
    )

    private = run_script("validate.py", root, "--json", "--no-cache")
    explicit = run_script(
        "validate.py", root, "--full", "--json", "--show-files", "--no-cache"
    )

    assert private.returncode == explicit.returncode == 0
    report = json.loads(private.stdout)
    finding = next(
        item
        for item in report["findings"]
        if item["code"] == "container_extension_mismatch"
    )
    assert finding == {
        "code": "container_extension_mismatch",
        "count": 1,
        "description": "video container does not match the filename extension",
        "severity": "warning",
    }
    assert {item["code"] for item in report["findings"]} == {
        "container_extension_mismatch",
        "extension_content_mismatch",
    }
    assert "misnamed.mp4" not in private.stdout
    assert "component.ts" not in private.stdout
    shown = json.loads(explicit.stdout)
    assert report["profile"] == "standard"
    assert shown["profile"] == "full"
    assert {
        (item["path"], item["code"], item["severity"])
        for item in shown["finding_files"]
    } == {
        ("component.ts", "extension_content_mismatch", "warning"),
        ("misnamed.mp4", "container_extension_mismatch", "warning"),
    }
