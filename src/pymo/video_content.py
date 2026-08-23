"""Shared strict decoded-video normalization and native-tool policy."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from pymo.video import ProbeInfo

# Persisted derived evidence depends on this exact normalization contract.
EXACT_PLAYBACK_ALGORITHM = "exact-playback-v2"


class VideoInspectionError(RuntimeError):
    """A video cannot be safely included in exact playback comparison."""


@dataclass(frozen=True)
class DerivedFingerprint:
    digest: str
    video_frames: int
    audio_bytes: int


def decimal_microseconds(value: object, *, default: int | None = None) -> int | None:
    if value in (None, "", "N/A"):
        return default
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite():
            return default
        decimal = parsed * Decimal(1_000_000)
        return int(decimal.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, OverflowError, ValueError):
        return default


def stream_rotation(stream: dict[str, object]) -> int:
    values: list[object] = []
    tags = stream.get("tags")
    if isinstance(tags, dict):
        values.append(tags.get("rotate"))
    side_data = stream.get("side_data_list")
    if isinstance(side_data, list):
        for item in side_data:
            if isinstance(item, dict):
                values.append(item.get("rotation"))
    for value in values:
        if value in (None, ""):
            continue
        try:
            rotation = round(float(str(value))) % 360
        except (OverflowError, ValueError) as error:
            raise VideoInspectionError(
                f"invalid rotation metadata: {value!r}"
            ) from error
        if rotation not in {0, 90, 180, 270}:
            raise VideoInspectionError(f"unsupported rotation: {rotation} degrees")
        return rotation
    return 0


def _positive_int(value: object, description: str) -> int:
    try:
        result = int(str(value))
    except (TypeError, ValueError) as error:
        raise VideoInspectionError(f"missing or invalid {description}") from error
    if result <= 0:
        raise VideoInspectionError(f"missing or invalid {description}")
    return result


def probe_video(descriptor: int, ffprobe: str) -> ProbeInfo:
    """Return conservative normalized structure from one inherited descriptor."""

    os.lseek(descriptor, 0, os.SEEK_SET)
    command = [
        ffprobe,
        "-v",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-show_streams",
        "-show_format",
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
        raise VideoInspectionError(f"ffprobe failed: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or "unrecognized or unreadable media"
        raise VideoInspectionError(f"ffprobe rejected the file: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise VideoInspectionError("ffprobe returned invalid JSON") from error

    if not isinstance(payload, dict):
        raise VideoInspectionError("ffprobe returned a non-object JSON value")
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise VideoInspectionError("ffprobe returned no stream list")
    if not all(isinstance(item, dict) for item in streams):
        raise VideoInspectionError("ffprobe returned an invalid stream entry")
    videos = [item for item in streams if item.get("codec_type") == "video"]
    audios = [item for item in streams if item.get("codec_type") == "audio"]
    others = [
        item for item in streams if item.get("codec_type") not in {"video", "audio"}
    ]
    if len(videos) != 1:
        raise VideoInspectionError(
            f"requires exactly one video stream; found {len(videos)}"
        )
    if len(audios) > 1:
        raise VideoInspectionError(
            f"multiple audio streams are not yet supported; found {len(audios)}"
        )
    if others:
        kinds = sorted({str(item.get("codec_type", "unknown")) for item in others})
        raise VideoInspectionError(
            "subtitle, data, or attachment streams are not yet supported: "
            + ", ".join(kinds)
        )

    video = videos[0]
    disposition = video.get("disposition")
    if isinstance(disposition, dict) and disposition.get("attached_pic"):
        raise VideoInspectionError("attached-picture video streams are not supported")
    width = _positive_int(video.get("width"), "video width")
    height = _positive_int(video.get("height"), "video height")
    pixel_format = str(video.get("pix_fmt") or "").lower()
    bit_depth = video.get("bits_per_raw_sample")
    if (
        not pixel_format
        or re.search(r"(?:10|12|14|16|48|64)(?:le|be)?$", pixel_format)
        or (str(bit_depth).isdigit() and int(str(bit_depth)) > 8)
        or str(video.get("color_transfer") or "").lower()
        in ("arib-std-b67", "smpte2084")
    ):
        raise VideoInspectionError(
            "HDR or high-bit-depth pixel format is not yet supported: "
            f"{pixel_format or 'unknown'}"
        )

    rotation = stream_rotation(video)
    display_width, display_height = (
        (height, width) if rotation in {90, 270} else (width, height)
    )
    format_data = payload.get("format")
    if not isinstance(format_data, dict):
        format_data = {}
    duration_us = decimal_microseconds(
        video.get("duration"),
        default=decimal_microseconds(format_data.get("duration"), default=None),
    )
    if duration_us is None or duration_us <= 0:
        raise VideoInspectionError("missing or invalid playback duration")
    video_start_us = decimal_microseconds(video.get("start_time"), default=0) or 0
    if not audios:
        return ProbeInfo(
            display_width=display_width,
            display_height=display_height,
            duration_us=duration_us,
            video_start_us=video_start_us,
            audio_start_us=None,
            audio_sample_rate=None,
            audio_channels=None,
            audio_layout=None,
            has_audio=False,
        )

    audio = audios[0]
    sample_rate = _positive_int(audio.get("sample_rate"), "audio sample rate")
    channels = _positive_int(audio.get("channels"), "audio channel count")
    layout = str(audio.get("channel_layout") or f"{channels}ch")
    audio_start_us = decimal_microseconds(audio.get("start_time"), default=0) or 0
    return ProbeInfo(
        display_width=display_width,
        display_height=display_height,
        duration_us=duration_us,
        video_start_us=video_start_us,
        audio_start_us=audio_start_us,
        audio_sample_rate=sample_rate,
        audio_channels=channels,
        audio_layout=layout,
        has_audio=True,
    )


def resolve_executable(value: Path | None, name: str) -> str:
    candidate = str(value.expanduser()) if value else shutil.which(name)
    if not candidate:
        raise VideoInspectionError(
            f"{name} was not found. Install FFmpeg and ensure both ffmpeg and "
            "ffprobe are available on PATH."
        )
    resolved = Path(candidate).resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise VideoInspectionError(f"not an executable {name} path: {resolved}")
    return str(resolved)


def native_tool_version(executable: str, name: str) -> str:
    try:
        result = subprocess.run(
            [executable, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise VideoInspectionError(f"cannot query {name} version: {error}") from error
    if result.returncode != 0 or not result.stdout.strip():
        raise VideoInspectionError(f"cannot query {name} version")
    return result.stdout.splitlines()[0].strip()


def ffmpeg_version(ffmpeg: str) -> str:
    return native_tool_version(ffmpeg, "FFmpeg")


def ffprobe_version(ffprobe: str) -> str:
    return native_tool_version(ffprobe, "FFprobe")


def _stream_command(
    command: list[str],
    consume_stdout: Callable[[bytes], None],
    timeout: int,
    progress_callback: Callable[[], None] | None = None,
    pass_fds: tuple[int, ...] = (),
) -> None:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=pass_fds,
        )
    except OSError as error:
        raise VideoInspectionError(f"cannot start FFmpeg: {error}") from error
    assert process.stdout is not None and process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    errors: deque[bytes] = deque(maxlen=32)
    deadline = time.monotonic() + timeout
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                raise VideoInspectionError(
                    f"FFmpeg decoding exceeded the {timeout}-second safety limit"
                )
            for key, _ in selector.select(timeout=min(1.0, remaining)):
                chunk = os.read(key.fd, 1024 * 1024)
                if not chunk:
                    selector.unregister(key.fileobj)
                elif key.data == "stdout":
                    consume_stdout(chunk)
                else:
                    errors.append(chunk)
            if progress_callback is not None:
                progress_callback()
        return_code = process.wait(timeout=10)
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.wait()
        raise
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    if return_code != 0:
        detail = b"".join(errors).decode("utf-8", "replace").strip()
        raise VideoInspectionError(
            "FFmpeg could not completely decode the file"
            + (f": {detail}" if detail else "")
        )


def video_frame_signature(
    descriptor: int,
    ffmpeg: str,
    timeout: int,
    progress_callback: Callable[[], None] | None = None,
) -> tuple[str, int]:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    line_buffer = bytearray()
    frame_count = 0

    def consume(chunk: bytes) -> None:
        nonlocal frame_count
        line_buffer.extend(chunk)
        while b"\n" in line_buffer:
            raw_line, _, remainder = line_buffer.partition(b"\n")
            line_buffer[:] = remainder
            line = raw_line.decode("ascii", "replace").strip()
            if not line or line.startswith("#"):
                continue
            fields = [field.strip() for field in line.split(",", 5)]
            if len(fields) != 6:
                raise VideoInspectionError(
                    f"unexpected FFmpeg framehash output: {line}"
                )
            _, _dts, pts, duration, size, frame_hash = fields
            digest.update(f"{pts},{duration},{size},{frame_hash}\n".encode("ascii"))
            frame_count += 1

    command = [
        ffmpeg,
        "-v",
        "error",
        "-nostdin",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        f"/dev/fd/{descriptor}",
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-vf",
        "settb=AVTB,setpts=PTS-STARTPTS,format=rgba",
        "-fps_mode",
        "passthrough",
        "-enc_time_base:v",
        "filter",
        "-f",
        "framehash",
        "-hash",
        "sha256",
        "pipe:1",
    ]
    _stream_command(
        command, consume, timeout, progress_callback, pass_fds=(descriptor,)
    )
    if line_buffer.strip():
        consume(b"\n")
    if frame_count == 0:
        raise VideoInspectionError("FFmpeg decoded no video frames")
    return digest.hexdigest(), frame_count


def audio_pcm_signature(
    descriptor: int,
    ffmpeg: str,
    probe: ProbeInfo,
    timeout: int,
    progress_callback: Callable[[], None] | None = None,
) -> tuple[str, int]:
    if not probe.has_audio:
        return "none", 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    byte_count = 0

    def consume(chunk: bytes) -> None:
        nonlocal byte_count
        digest.update(chunk)
        byte_count += len(chunk)

    command = [
        ffmpeg,
        "-v",
        "error",
        "-nostdin",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        f"/dev/fd/{descriptor}",
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-af",
        "asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0",
        "-acodec",
        "pcm_s32le",
        "-f",
        "s32le",
        "pipe:1",
    ]
    _stream_command(
        command, consume, timeout, progress_callback, pass_fds=(descriptor,)
    )
    if byte_count == 0:
        raise VideoInspectionError("FFmpeg decoded no audio samples")
    return digest.hexdigest(), byte_count


def derive_fingerprint(
    descriptor: int,
    probe: ProbeInfo,
    ffmpeg: str,
    timeout: int,
    progress_callback: Callable[[], None] | None = None,
) -> DerivedFingerprint:
    video_hash, frame_count = video_frame_signature(
        descriptor, ffmpeg, timeout, progress_callback
    )
    audio_hash, audio_bytes = audio_pcm_signature(
        descriptor, ffmpeg, probe, timeout, progress_callback
    )
    starts = [probe.video_start_us]
    if probe.audio_start_us is not None:
        starts.append(probe.audio_start_us)
    earliest_start = min(starts)
    canonical = {
        "algorithm": EXACT_PLAYBACK_ALGORITHM,
        "display_width": probe.display_width,
        "display_height": probe.display_height,
        "video_start_us": probe.video_start_us - earliest_start,
        "audio_start_us": (
            probe.audio_start_us - earliest_start
            if probe.audio_start_us is not None
            else None
        ),
        "audio_sample_rate": probe.audio_sample_rate,
        "audio_channels": probe.audio_channels,
        "audio_layout": probe.audio_layout,
        "video_frames": frame_count,
        "video_sha256": video_hash,
        "audio_bytes": audio_bytes,
        "audio_sha256": audio_hash,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return DerivedFingerprint(
        digest=hashlib.sha256(encoded).hexdigest(),
        video_frames=frame_count,
        audio_bytes=audio_bytes,
    )
