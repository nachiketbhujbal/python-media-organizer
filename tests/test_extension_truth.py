from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from pymo import extension_truth
from pymo.extension_truth import ExtensionEvidenceError


def probe_payload(*, score: object = 50, family: object = "mpegts") -> str:
    return json.dumps(
        {
            "streams": [{"codec_type": "video"}],
            "format": {"format_name": family, "probe_score": score},
        }
    )


def test_video_container_evidence_uses_only_the_inherited_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "clip.bin"
    source.write_bytes(b"synthetic")
    descriptor = os.open(source, os.O_RDONLY)
    observed: list[str] = []

    def run(command, **kwargs):
        observed.extend(command)
        assert kwargs["pass_fds"] == (descriptor,)
        assert kwargs["timeout"] == 60
        return subprocess.CompletedProcess(command, 0, probe_payload(), "")

    monkeypatch.setattr(extension_truth.subprocess, "run", run)
    try:
        evidence = extension_truth.inspect_video_container(descriptor, "/bin/ffprobe")
    finally:
        os.close(descriptor)

    assert evidence.family == "mpegts"
    assert evidence.probe_score == 50
    assert f"/dev/fd/{descriptor}" in observed
    assert "file,pipe" in observed
    assert str(source) not in observed


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (probe_payload(score=49), "not confident"),
        (probe_payload(score=True), "not confident"),
        (probe_payload(family="bad family"), "invalid container family"),
        (
            json.dumps(
                {
                    "streams": [{"codec_type": "audio"}],
                    "format": {"format_name": "mpegts", "probe_score": 100},
                }
            ),
            "no video stream",
        ),
    ],
)
def test_video_container_evidence_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
    message: str,
) -> None:
    source = tmp_path / "clip.bin"
    source.write_bytes(b"synthetic")
    descriptor = os.open(source, os.O_RDONLY)
    monkeypatch.setattr(
        extension_truth.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, payload, ""),
    )
    try:
        with pytest.raises(ExtensionEvidenceError, match=message):
            extension_truth.inspect_video_container(descriptor, "/bin/ffprobe")
    finally:
        os.close(descriptor)
