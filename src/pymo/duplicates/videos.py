#!/usr/bin/env python3
"""Find deterministic, exact-playback video duplicates in ``vids``.

The default is a dry run. Nothing is moved unless ``--apply`` is supplied.
Whole-file SHA-256 is the fast path; non-identical files are compared using a
strict FFmpeg-derived fingerprint of displayed frames, normalized timing, and
decoded audio. Similar-looking, recompressed, cropped, or watermarked media is
not considered an exact duplicate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import time
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from pymo import cache as cache_service
from pymo.action_log import (
    Action,
    ActionConflict,
    ActionLog,
    ActionLogError,
    NoUndoableRun,
    ToolId,
)
from pymo.cache.hashes import HashCacheError, load_cached_hashes, save_cached_hashes
from pymo.classification import Classifier
from pymo.collection import CollectionLayout
from pymo.config import (
    ConfigError,
    PymoConfig,
    add_config_argument,
    add_show_ignored_argument,
    ignored_messages,
    load_config,
)
from pymo.discovery import (
    DiscoveryError,
    entry_kind_complete,
    list_directory_complete,
)
from pymo.duplicates.common import (
    copy_target,
    describe_undo_action,
    duplicate_layout,
    layout_problems,
)
from pymo.file_safety import FileChangedError, FileState, open_stable_file
from pymo.logging_config import emit as print
from pymo.progress import ProgressMeter, StageTimer, format_bytes

# This value is persisted with derived fingerprints. Changing the algorithm
# without changing this identifier could reuse incompatible cached results.
FINGERPRINT_ALGORITHM = "exact-playback-v2"


class VideoInspectionError(RuntimeError):
    """A video cannot be safely included in exact duplicate matching."""


class VideoCacheError(RuntimeError):
    """The derived fingerprint cache cannot be used safely."""


@dataclass(frozen=True)
class ProbeInfo:
    display_width: int
    display_height: int
    duration_us: int
    video_start_us: int
    audio_start_us: int | None
    audio_sample_rate: int | None
    audio_channels: int | None
    audio_layout: str | None
    has_audio: bool

    @property
    def candidate_key(self) -> tuple[object, ...]:
        # This intentionally omits codecs, containers, and source pixel format.
        # Files in different basic buckets cannot produce the same canonical
        # playback, while files in the same bucket still require full decoding.
        return (
            self.display_width,
            self.display_height,
            self.has_audio,
            self.audio_sample_rate,
            self.audio_channels,
            self.audio_layout,
        )


@dataclass(frozen=True)
class VideoRecord:
    path: Path
    byte_sha256: str
    state: FileState
    probe: ProbeInfo
    byte_sha256_cached: bool = False

    @property
    def file_size(self) -> int:
        return self.state.size

    @property
    def modified_ns(self) -> int:
        return self.state.modified_ns


@dataclass(frozen=True)
class DerivedFingerprint:
    digest: str
    video_frames: int
    audio_bytes: int


VideoMove = tuple[VideoRecord, VideoRecord, Path]


def sha256_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while chunk := os.read(descriptor, 1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def inspect_video(
    root: Path,
    path: Path,
    ffprobe: str,
    *,
    state: FileState | None = None,
    cached_sha256: str | None = None,
) -> VideoRecord:
    state = state or FileState.capture(path)
    with open_stable_file(root, path, state, "video inspection") as descriptor:
        byte_sha256 = cached_sha256 or sha256_descriptor(descriptor)
        probe = probe_video(descriptor, ffprobe)
    return VideoRecord(
        path=path,
        byte_sha256=byte_sha256,
        state=state,
        probe=probe,
        byte_sha256_cached=cached_sha256 is not None,
    )


def require_current_video(record: VideoRecord, operation: str) -> None:
    record.state.require_unchanged(record.path, operation)


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
            f"HDR or high-bit-depth pixel format is not yet supported: {pixel_format or 'unknown'}"
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


def discover_videos(
    vids: Path, root: Path, classifier: Classifier, config: PymoConfig
) -> tuple[list[Path], list[Path]]:
    videos: list[Path] = []
    ignored: list[Path] = []
    for path in list_directory_complete(vids):
        entry_kind = entry_kind_complete(path)
        if entry_kind == "symlink":
            continue
        if entry_kind == "directory":
            if config.ignores_directory(path, root):
                ignored.append(path)
            continue
        if entry_kind != "file":
            continue
        if config.ignores_file(path, root):
            ignored.append(path)
            continue
        try:
            state = FileState.capture(path)
            with open_stable_file(root, path, state, "video discovery") as descriptor:
                kind, _ = classifier.classify(path, descriptor)
        except FileChangedError:
            continue
        if kind == "video":
            videos.append(path.absolute())
    return (
        sorted(videos, key=lambda item: str(item).casefold()),
        sorted(ignored, key=lambda item: str(item).casefold()),
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


def writable_cache_path(root: Path, requested: Path | None) -> Path:
    """Resolve a local or explicit cache target without creating its parent."""

    if requested is None:
        return CollectionLayout(root).derived_cache
    database = Path(os.path.abspath(requested.expanduser()))
    if database.name in {"", ".", ".."}:
        raise VideoInspectionError("invalid explicit SQLite cache path")
    if not database.parent.is_dir() or database.parent.is_symlink():
        raise VideoInspectionError(
            "explicit SQLite cache parent must be an existing regular directory"
        )
    return database


def ffmpeg_version(ffmpeg: str) -> str:
    try:
        result = subprocess.run(
            [ffmpeg, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise VideoInspectionError(f"cannot query FFmpeg version: {error}") from error
    if result.returncode != 0 or not result.stdout.strip():
        raise VideoInspectionError("cannot query FFmpeg version")
    return result.stdout.splitlines()[0].strip()


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
        command,
        consume,
        timeout,
        progress_callback,
        pass_fds=(descriptor,),
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
        command,
        consume,
        timeout,
        progress_callback,
        pass_fds=(descriptor,),
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
        "algorithm": FINGERPRINT_ALGORITHM,
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


def decode_video_evidence(
    records: list[cache_service.DerivedEvidence],
) -> dict[str, DerivedFingerprint]:
    decoded: dict[str, DerivedFingerprint] = {}
    for record in records:
        try:
            payload = json.loads(record.payload_json)
        except json.JSONDecodeError as error:
            raise VideoInspectionError(
                "SQLite fingerprint cache contains invalid video evidence"
            ) from error
        if not isinstance(payload, dict) or set(payload) != {
            "digest",
            "video_frames",
            "audio_bytes",
        }:
            raise VideoInspectionError(
                "SQLite fingerprint cache contains invalid video evidence"
            )
        digest = payload["digest"]
        video_frames = payload["video_frames"]
        audio_bytes = payload["audio_bytes"]
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or isinstance(video_frames, bool)
            or not isinstance(video_frames, int)
            or video_frames <= 0
            or isinstance(audio_bytes, bool)
            or not isinstance(audio_bytes, int)
            or audio_bytes < 0
        ):
            raise VideoInspectionError(
                "SQLite fingerprint cache contains invalid video evidence"
            )
        decoded[record.file_sha256] = DerivedFingerprint(
            digest=digest,
            video_frames=video_frames,
            audio_bytes=audio_bytes,
        )
    return decoded


def load_cached_fingerprints(
    _root: Path, database: Path, ffmpeg_release: str
) -> dict[str, DerivedFingerprint]:
    try:
        contents = cache_service.read_coordinated_cache(database)
        if contents is None:
            return {}
        records = [
            record
            for record in contents.evidence
            if record.evidence_type == cache_service.LEGACY_VIDEO_EVIDENCE_TYPE
            and record.algorithm == FINGERPRINT_ALGORITHM
            and record.runtime == ffmpeg_release
        ]
        return decode_video_evidence(records)
    except cache_service.CacheError as error:
        raise VideoInspectionError(str(error)) from error


def save_cached_fingerprints(
    _root: Path,
    database: Path,
    ffmpeg_release: str,
    values: dict[str, DerivedFingerprint],
) -> None:
    if not values:
        return
    records = tuple(
        cache_service.DerivedEvidence(
            file_sha256=file_hash,
            evidence_type=cache_service.LEGACY_VIDEO_EVIDENCE_TYPE,
            algorithm=FINGERPRINT_ALGORITHM,
            runtime=ffmpeg_release,
            payload_json=json.dumps(
                {
                    "audio_bytes": value.audio_bytes,
                    "digest": value.digest,
                    "video_frames": value.video_frames,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        for file_hash, value in sorted(values.items())
    )
    try:
        cache_service.publish_cache_update(
            database,
            lambda connection: cache_service.upsert_derived_evidence(
                connection, records
            ),
        )
    except cache_service.CacheError as error:
        raise VideoInspectionError(str(error)) from error


def keep_sort_key(record: VideoRecord) -> tuple[int, int, str]:
    return (-record.file_size, record.modified_ns, str(record.path).casefold())


def print_storage_summary(
    duplicate_groups: list[list[VideoRecord]], scanned_bytes: int
) -> None:
    retained_bytes = 0
    duplicate_bytes = 0
    duplicate_count = 0
    for records in duplicate_groups:
        ordered = sorted(records, key=keep_sort_key)
        retained_bytes += ordered[0].file_size
        duplicate_bytes += sum(record.file_size for record in ordered[1:])
        duplicate_count += len(ordered) - 1
    duplicate_set_bytes = retained_bytes + duplicate_bytes
    set_percentage = (
        duplicate_bytes / duplicate_set_bytes * 100 if duplicate_set_bytes else 0.0
    )
    scan_percentage = duplicate_bytes / scanned_bytes * 100 if scanned_bytes else 0.0
    print("\nDuplicate storage summary:")
    print(
        f"  Retained originals: {len(duplicate_groups)} file(s), "
        f"{format_bytes(retained_bytes)}"
    )
    print(
        f"  Extra duplicate copies: {duplicate_count} file(s), "
        f"{format_bytes(duplicate_bytes)}"
    )
    print(f"  Duplicate sets combined: {format_bytes(duplicate_set_bytes)}")
    print(
        "  Potentially reclaimable if extra copies were deleted: "
        f"{format_bytes(duplicate_bytes)} ({set_percentage:.1f}% of duplicate-set "
        f"storage; {scan_percentage:.1f}% of scanned video storage)"
    )
    print("  No files are deleted by this tool.")


def undo_duplicate_run(root: Path, apply: bool, *, summary: bool = False) -> int:
    log = ActionLog(root)
    try:
        plan = log.plan_undo(ToolId.VIDEO_DUPLICATES)
    except NoUndoableRun as error:
        detail = "No undoable video duplicate run found." if summary else str(error)
        print(detail, file=sys.stderr)
        return 2
    except (ActionConflict, ActionLogError, OSError) as error:
        detail = "rerun without --summary for details" if summary else str(error)
        print(f"Cannot safely undo duplicate moves: {detail}", file=sys.stderr)
        return 1
    if not summary:
        print(f"Using action log: {log.path}")
        print(f"Video duplicate-finder run: {plan.target.run_id}")
        for action in plan.actions:
            describe_undo_action(root, action, apply)
    if not apply:
        print(f"\nWould reverse {len(plan.actions)} recorded action(s).")
        if plan.actions:
            print("Dry run only. Add --apply after reviewing this list.")
        return 0
    try:
        result = log.apply_undo(ToolId.VIDEO_DUPLICATES)
    except (ActionConflict, ActionLogError, OSError) as error:
        detail = "rerun without --summary for details" if summary else str(error)
        print(f"Video duplicate undo failed safely: {detail}", file=sys.stderr)
        return 1
    print(f"\nReversed {result.action_count} recorded action(s).")
    print("Verification passed: every recorded duplicate-video action was reversed.")
    return 0


def inspect_video_paths(
    root: Path,
    paths: list[Path],
    ffprobe: str,
    progress_interval_seconds: int,
    database: Path | None,
    publication_batch_size: int,
) -> tuple[list[VideoRecord], int, list[tuple[Path, str]]]:
    records: list[VideoRecord] = []
    scanned_bytes = 0
    skipped: list[tuple[Path, str]] = []
    states: dict[Path, FileState] = {}
    for path in paths:
        try:
            states[path] = FileState.capture(path)
        except FileChangedError as error:
            skipped.append((path, str(error)))
    try:
        cached_hashes = (
            {}
            if database is None
            else load_cached_hashes(root, database, states, coordinated=True)
        )
    except HashCacheError as error:
        raise VideoCacheError(
            "Whole-file hash cache cannot be used safely: "
            f"{error}\nThe cache is disposable; move it aside or rerun with --no-cache."
        ) from error
    if database is None:
        print("Whole-file hash cache disabled: no records read or written.")
    else:
        print(
            f"Whole-file hash cache lookup: {len(cached_hashes)} reusable "
            f"record(s); {len(states) - len(cached_hashes)} hash(es) required."
        )
    progress = ProgressMeter(
        len(states),
        sum(state.size for state in states.values()),
        progress_interval_seconds,
    )
    persisted = 0
    pending: list[tuple[Path, FileState, str]] = []

    def publish_pending() -> None:
        nonlocal persisted
        if database is None or not pending:
            return
        save_cached_hashes(root, database, pending)
        persisted += len(pending)
        pending.clear()

    for path, state in states.items():
        try:
            record = inspect_video(
                root,
                path,
                ffprobe,
                state=state,
                cached_sha256=cached_hashes.get(path),
            )
            records.append(record)
            scanned_bytes += record.file_size
            if database is not None and not record.byte_sha256_cached:
                pending.append((record.path, record.state, record.byte_sha256))
                if len(pending) >= publication_batch_size:
                    publish_pending()
        except (FileChangedError, OSError, VideoInspectionError) as error:
            skipped.append((path, str(error)))
        except HashCacheError as error:
            raise VideoCacheError(
                f"Whole-file hash cache update failed safely: {error}"
            ) from error
        progress_message = progress.advance("inspected", byte_count=state.size)
        if progress_message:
            print(f"  {progress_message}")
    try:
        publish_pending()
    except HashCacheError as error:
        raise VideoCacheError(
            f"Whole-file hash cache update failed safely: {error}"
        ) from error
    if database is not None:
        print(f"Whole-file hash cache update: {persisted} new record(s) persisted.")
    return records, scanned_bytes, skipped


def recheck_cached_video_hashes(root: Path, records: list[VideoRecord]) -> None:
    """Re-read cached byte identities before permitting any exact move."""

    for record in records:
        if not record.byte_sha256_cached:
            continue
        with open_stable_file(
            root, record.path, record.state, "cached video hash recheck"
        ) as descriptor:
            if sha256_descriptor(descriptor) != record.byte_sha256:
                raise FileChangedError(
                    "file content changed during cached video hash recheck: "
                    f"{record.path}"
                )


def candidate_video_records(records: list[VideoRecord]) -> list[VideoRecord]:
    candidates: dict[tuple[object, ...], list[VideoRecord]] = defaultdict(list)
    for record in records:
        candidates[record.probe.candidate_key].append(record)
    return [
        record for bucket in candidates.values() if len(bucket) > 1 for record in bucket
    ]


def derive_candidate_fingerprints(
    root: Path,
    candidate_records: list[VideoRecord],
    database: Path,
    ffmpeg: str,
    ffmpeg_release: str,
    decode_timeout: int,
    progress_interval_seconds: int,
    no_cache: bool,
    summary: bool = False,
    *,
    fingerprint_label: str = "candidate content",
) -> tuple[dict[str, DerivedFingerprint], list[tuple[Path, str]]]:
    unique_hashes = {record.byte_sha256: record for record in candidate_records}
    try:
        cached = (
            {} if no_cache else load_cached_fingerprints(root, database, ffmpeg_release)
        )
    except VideoInspectionError as error:
        raise VideoCacheError(
            "Fingerprint cache cannot be used safely: "
            f"{error}\nThe cache is disposable; move it aside or rerun with --no-cache."
        ) from error

    cache_hits = sum(file_hash in cached for file_hash in unique_hashes)
    cache_misses = len(unique_hashes) - cache_hits
    if no_cache:
        print(
            "Fingerprint cache disabled by --no-cache: no records read or written; "
            f"{cache_misses} fingerprint(s) required."
        )
    else:
        print(
            f"Fingerprint cache lookup: {cache_hits} reusable record(s); "
            f"{cache_misses} fingerprint(s) required."
        )
    ordered_hashes = sorted(
        unique_hashes.items(), key=lambda item: str(item[1].path).casefold()
    )
    derived = {
        file_hash: cached[file_hash]
        for file_hash, _ in ordered_hashes
        if file_hash in cached
    }
    decode_items = [
        (file_hash, representative)
        for file_hash, representative in ordered_hashes
        if file_hash not in cached
    ]
    progress = ProgressMeter(
        len(decode_items),
        sum(representative.file_size for _, representative in decode_items),
        progress_interval_seconds,
    )
    if decode_items:
        print(
            f"Fingerprinting {len(decode_items)} {fingerprint_label} "
            f"file(s), {format_bytes(progress.total_bytes or 0)} total."
        )

    skipped: list[tuple[Path, str]] = []
    persisted_records = 0
    for number, (file_hash, representative) in enumerate(decode_items, start=1):
        if not summary:
            print(
                f"  starting fingerprint {number}/{len(decode_items)} "
                f"({format_bytes(representative.file_size)})"
            )

        def report_heartbeat(active_number: int = number) -> None:
            message = progress.heartbeat("fingerprint progress", active_number)
            if message:
                print(f"  {message}")

        try:
            with open_stable_file(
                root,
                representative.path,
                representative.state,
                "video fingerprinting",
            ) as descriptor:
                fingerprint = derive_fingerprint(
                    descriptor,
                    representative.probe,
                    ffmpeg,
                    decode_timeout,
                    report_heartbeat,
                )
        except (FileChangedError, VideoInspectionError) as error:
            skipped.extend(
                (record.path, str(error))
                for record in candidate_records
                if record.byte_sha256 == file_hash
            )
        else:
            derived[file_hash] = fingerprint
            try:
                if not no_cache:
                    save_cached_fingerprints(
                        root, database, ffmpeg_release, {file_hash: fingerprint}
                    )
                    persisted_records += 1
            except VideoInspectionError as error:
                raise VideoCacheError(
                    f"Fingerprint cache update failed safely: {error}"
                ) from error
        progress_message = progress.advance(
            "fingerprint progress",
            byte_count=representative.file_size,
        )
        if progress_message:
            print(f"  {progress_message}")
    if not no_cache:
        print(
            f"Fingerprint cache update: {persisted_records} new record(s) persisted; "
            f"{cache_misses - persisted_records} required fingerprint(s) not "
            "persisted."
        )
    return derived, skipped


def group_video_duplicates(
    candidate_records: list[VideoRecord],
    derived: dict[str, DerivedFingerprint],
) -> tuple[list[list[VideoRecord]], list[tuple[Path, str]]]:
    stable_records: list[VideoRecord] = []
    skipped: list[tuple[Path, str]] = []
    for record in candidate_records:
        try:
            require_current_video(record, "duplicate analysis")
        except FileChangedError as error:
            skipped.append((record.path, str(error)))
        else:
            stable_records.append(record)

    fingerprint_groups: dict[str, list[VideoRecord]] = defaultdict(list)
    for record in stable_records:
        fingerprint = derived.get(record.byte_sha256)
        if fingerprint is not None:
            fingerprint_groups[fingerprint.digest].append(record)
    duplicate_groups = [
        group for group in fingerprint_groups.values() if len(group) > 1
    ]
    duplicate_groups.sort(
        key=lambda items: str(min(record.path for record in items)).casefold()
    )
    return duplicate_groups, skipped


def plan_video_moves(
    duplicate_groups: list[list[VideoRecord]],
    destination: Path,
    apply: bool,
    *,
    summary: bool = False,
) -> list[VideoMove]:
    move_plan: list[VideoMove] = []
    reserved_targets: set[str] = set()
    for group_number, group in enumerate(duplicate_groups, start=1):
        ordered = sorted(group, key=keep_sort_key)
        kept = ordered[0]
        if not summary:
            print(f"\nGroup {group_number}: keep {kept.path}")
        next_number = 1
        for duplicate in ordered[1:]:
            target, used_number = copy_target(
                destination,
                kept.path,
                duplicate.path,
                next_number,
                reserved_targets,
            )
            next_number = used_number + 1
            move_plan.append((kept, duplicate, target))
            if not summary:
                print(f"  duplicate: {duplicate.path}")
                print(f"  {'move to' if apply else 'would move to'}: {target}")
    return move_plan


def apply_video_moves(
    root: Path,
    duplicate_groups: list[list[VideoRecord]],
    move_plan: list[VideoMove],
) -> Path:
    layout = duplicate_layout(root, "video")
    current_records = {
        record.path: record for records in duplicate_groups for record in records
    }
    recheck_cached_video_hashes(root, list(current_records.values()))
    keepers = {kept.path: kept for kept, _, _ in move_plan}
    for record in current_records.values():
        require_current_video(record, "duplicate apply preflight")
    actions: list[Action] = []
    for _, duplicate, target in move_plan:
        action = Action.for_file(root, duplicate.path, target, "MOVE")
        require_current_video(duplicate, "duplicate apply preflight")
        actions.append(action)
    for record in current_records.values():
        require_current_video(record, "duplicate apply preflight")

    log = ActionLog(root)
    with log.transaction(ToolId.VIDEO_DUPLICATES) as transaction:
        for record in current_records.values():
            require_current_video(record, "duplicate apply preflight")
        for directory in (layout.review_root, layout.destination):
            if not directory.exists():
                transaction.perform(Action.create_directory(root, directory))
        for action, (kept, _, _) in zip(actions, move_plan, strict=True):
            require_current_video(kept, "duplicate apply preflight")
            transaction.perform(action)
        for record in keepers.values():
            require_current_video(record, "duplicate apply preflight")
        transaction.commit()
    return log.path


def verify_video_moves(move_plan: list[VideoMove]) -> list[tuple[Path, Path]]:
    return [
        (duplicate.path, target)
        for _, duplicate, target in move_plan
        if os.path.lexists(duplicate.path)
        or target.is_symlink()
        or not target.is_file()
    ]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find videos with exactly the same supported decoded playback. "
            "By default, only report what would happen."
        )
    )
    parser.add_argument(
        "folder", type=Path, help="organized collection root containing vids"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform duplicate moves after reporting them",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="do not read or update the disposable fingerprint cache",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        help=(
            "use this cache file instead of the collection-local default; its "
            "parent directory must already exist"
        ),
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help=(
            "reverse the newest active video duplicate-finder run; this is also "
            "a dry run unless --apply is supplied"
        ),
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="show aggregate path-private results without file or group details",
    )
    parser.add_argument("--ffmpeg", type=Path, help="explicit ffmpeg executable path")
    parser.add_argument("--ffprobe", type=Path, help="explicit ffprobe executable path")
    parser.add_argument(
        "--decode-timeout",
        type=int,
        help=(
            "maximum seconds allowed for each FFmpeg decode "
            "(default: configured video_duplicates.decode_timeout_seconds)"
        ),
    )
    add_config_argument(parser)
    add_show_ignored_argument(parser)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        message = "supplied collection path" if args.summary else str(root)
        print(f"Not a directory: {message}", file=sys.stderr)
        return 2
    if args.summary and args.show_ignored:
        print(
            "--summary cannot be combined with --show-ignored because summary "
            "output is path-private",
            file=sys.stderr,
        )
        return 2
    if args.decode_timeout is not None and args.decode_timeout <= 0:
        print("--decode-timeout must be a positive number", file=sys.stderr)
        return 2
    if args.no_cache and args.cache is not None:
        print("--no-cache cannot be combined with --cache", file=sys.stderr)
        return 2
    if args.undo:
        return undo_duplicate_run(root, args.apply, summary=args.summary)

    try:
        config = load_config(root, args.config)
        database = writable_cache_path(root, args.cache)
    except (ConfigError, VideoInspectionError) as error:
        detail = "rerun without --summary for details" if args.summary else str(error)
        print(f"Cannot use configuration: {detail}", file=sys.stderr)
        return 2
    decode_timeout = (
        args.decode_timeout
        if args.decode_timeout is not None
        else config.video_duplicates.decode_timeout_seconds
    )

    problems = layout_problems(root, config, "video")
    if problems:
        print("Collection is not ready for video duplicate scanning:", file=sys.stderr)
        if args.summary:
            print(f"  {len(problems)} layout problem(s).", file=sys.stderr)
            print(
                "Run pymo organize COLLECTION first so videos are directly in vids.",
                file=sys.stderr,
            )
        else:
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            print(
                f'Run pymo organize "{root}" first so videos are directly in vids.',
                file=sys.stderr,
            )
        return 2

    duplicate_paths = duplicate_layout(root, "video")
    vids = duplicate_paths.source
    destination = duplicate_paths.destination
    classifier = Classifier(config.classification)
    stage_timer = StageTimer(print)
    try:
        with stage_timer.measure("discovery"):
            paths, ignored = discover_videos(vids, root, classifier, config)
    except DiscoveryError as error:
        detail = "rerun without --summary for details" if args.summary else str(error)
        print(f"Video discovery stopped safely: {detail}", file=sys.stderr)
        return 1
    location = "" if args.summary else f" in {vids}"
    print(f"Scanning {len(paths)} video(s){location}")
    for message in ignored_messages(ignored, root, args.show_ignored):
        print(message)

    if len(paths) < 2:
        scanned_bytes = 0
        for path in paths:
            try:
                scanned_bytes += FileState.capture(path).size
            except FileChangedError:
                pass
        verb = "Moved" if args.apply else "Would move"
        print("Fewer than two videos; exact comparison is not required.")
        print(f"\n{verb} 0 duplicate(s) from 0 group(s).")
        print_storage_summary([], scanned_bytes)
        return 0

    try:
        ffmpeg = resolve_executable(args.ffmpeg, "ffmpeg")
        ffprobe = resolve_executable(args.ffprobe, "ffprobe")
        ffmpeg_release = ffmpeg_version(ffmpeg)
    except VideoInspectionError as error:
        detail = (
            "native video tools are unavailable; rerun without --summary for details"
            if args.summary
            else str(error)
        )
        print(detail, file=sys.stderr)
        return 2
    print(f"FFmpeg runtime: {ffmpeg_release}")

    try:
        with stage_timer.measure("probing"):
            records, scanned_bytes, skipped = inspect_video_paths(
                root,
                paths,
                ffprobe,
                config.performance.progress_interval_seconds,
                None if args.no_cache else database,
                config.performance.cache_publication_batch_size,
            )
    except VideoCacheError as error:
        detail = (
            "Whole-file hash cache cannot be used safely; rerun without --summary "
            "for details."
            if args.summary
            else str(error)
        )
        print(detail, file=sys.stderr)
        return 1
    candidate_records = candidate_video_records(records)
    try:
        with stage_timer.measure("fingerprinting"):
            derived, fingerprint_skips = derive_candidate_fingerprints(
                root,
                candidate_records,
                database,
                ffmpeg,
                ffmpeg_release,
                decode_timeout,
                config.performance.progress_interval_seconds,
                args.no_cache,
                args.summary,
            )
    except VideoCacheError as error:
        detail = (
            "Fingerprint cache cannot be used safely; rerun without --summary "
            "for details."
            if args.summary
            else str(error)
        )
        print(detail, file=sys.stderr)
        return 1
    skipped.extend(fingerprint_skips)
    with stage_timer.measure("planning"):
        duplicate_groups, group_skips = group_video_duplicates(
            candidate_records, derived
        )
        skipped.extend(group_skips)
        move_plan = plan_video_moves(
            duplicate_groups, destination, args.apply, summary=args.summary
        )

    if args.apply and move_plan:
        try:
            with stage_timer.measure("apply"):
                log_path = apply_video_moves(root, duplicate_groups, move_plan)
            print(
                "\nAction log updated." if args.summary else f"\nAction log: {log_path}"
            )
        except (
            ActionConflict,
            ActionLogError,
            FileChangedError,
            OSError,
        ) as error:
            detail = (
                "rerun without --summary for details" if args.summary else str(error)
            )
            print(f"Duplicate moves stopped safely: {detail}", file=sys.stderr)
            return 1
        with stage_timer.measure("verification"):
            verification_failures = verify_video_moves(move_plan)
        if verification_failures:
            print("\nVerification needs attention:", file=sys.stderr)
            if args.summary:
                print(
                    f"  {len(verification_failures)} move(s) failed verification.",
                    file=sys.stderr,
                )
            else:
                for source, target in verification_failures:
                    print(f"  {source} -> {target}", file=sys.stderr)
            return 1

    duplicate_count = len(move_plan)
    verb = "Moved" if args.apply else "Would move"
    print(
        f"\n{verb} {duplicate_count} duplicate(s) from "
        f"{len(duplicate_groups)} group(s)."
    )
    print_storage_summary(duplicate_groups, scanned_bytes)
    if not args.apply and duplicate_count:
        print("Dry run only. Add --apply after reviewing this list.")
    if skipped:
        suffix = "." if args.summary else ":"
        print(f"\nSkipped {len(skipped)} file(s){suffix}")
        if not args.summary:
            for path, reason in skipped:
                print(f"  {path}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
