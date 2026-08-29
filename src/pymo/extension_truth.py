"""Fresh descriptor-pinned evidence for truthful media extensions."""

from __future__ import annotations

import json
import os
import subprocess
import warnings
from dataclasses import dataclass

from PIL import Image, ImageSequence, UnidentifiedImageError

from pymo.config import canonical_container_family


class ExtensionEvidenceError(RuntimeError):
    """A file cannot support a safe extension conclusion."""


@dataclass(frozen=True)
class VideoContainerEvidence:
    family: str
    probe_score: int


def inspect_image_format(descriptor: int) -> str:
    """Return one fully decoded Pillow format from a stable descriptor."""

    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with os.fdopen(os.dup(descriptor), "rb") as handle:
                with Image.open(handle) as opened:
                    format_name = opened.format
                    opened.verify()
            os.lseek(descriptor, 0, os.SEEK_SET)
            with os.fdopen(os.dup(descriptor), "rb") as handle:
                with Image.open(handle) as opened:
                    if opened.format != format_name:
                        raise ValueError("image format changed between decoder passes")
                    for frame in ImageSequence.Iterator(opened):
                        frame.load()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        ValueError,
    ) as error:
        raise ExtensionEvidenceError("image format could not be verified") from error
    if not isinstance(format_name, str) or not format_name:
        raise ExtensionEvidenceError("image decoder reported no format")
    return format_name.upper()


def inspect_video_container(descriptor: int, ffprobe: str) -> VideoContainerEvidence:
    """Return confidence-gated container evidence from an extensionless input."""

    os.lseek(descriptor, 0, os.SEEK_SET)
    command = [
        ffprobe,
        "-v",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-show_entries",
        "stream=codec_type:format=format_name,probe_score",
        "-of",
        "json",
        f"/dev/fd/{descriptor}",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            pass_fds=(descriptor,),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ExtensionEvidenceError("ffprobe could not inspect the file") from error
    if result.returncode != 0:
        raise ExtensionEvidenceError("ffprobe rejected the file")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ExtensionEvidenceError("ffprobe returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise ExtensionEvidenceError("ffprobe returned invalid evidence")
    streams = payload.get("streams")
    if not isinstance(streams, list) or not any(
        isinstance(stream, dict) and stream.get("codec_type") == "video"
        for stream in streams
    ):
        raise ExtensionEvidenceError("ffprobe found no video stream")
    format_data = payload.get("format")
    if not isinstance(format_data, dict):
        raise ExtensionEvidenceError("ffprobe returned no container evidence")
    probe_score = format_data.get("probe_score")
    format_name = format_data.get("format_name")
    if type(probe_score) is not int or not 50 <= probe_score <= 100:
        raise ExtensionEvidenceError("video container evidence is not confident")
    if not isinstance(format_name, str):
        raise ExtensionEvidenceError("ffprobe returned no container family")
    family = canonical_container_family(format_name)
    if family is None:
        raise ExtensionEvidenceError("ffprobe returned an invalid container family")
    return VideoContainerEvidence(family=family, probe_score=probe_score)
