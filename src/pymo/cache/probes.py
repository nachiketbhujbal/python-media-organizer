"""Versioned exact-video structure evidence in the shared cache."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from pymo.cache import service as cache_service
from pymo.cache.hashes import build_hash_observations
from pymo.file_safety import FileState
from pymo.video import ProbeInfo

# These values identify persisted derived evidence. Changing the normalized
# payload or its meaning requires a new algorithm identifier.
VIDEO_PROBE_EVIDENCE_TYPE = "video-probe"
VIDEO_PROBE_ALGORITHM = "ffprobe-structure-v1"


class ProbeCacheError(RuntimeError):
    """Cached video structure evidence cannot be used safely."""


def _payload(probe: ProbeInfo) -> dict[str, object]:
    return {
        "audio_channels": probe.audio_channels,
        "audio_layout": probe.audio_layout,
        "audio_sample_rate": probe.audio_sample_rate,
        "audio_start_us": probe.audio_start_us,
        "display_height": probe.display_height,
        "display_width": probe.display_width,
        "duration_us": probe.duration_us,
        "has_audio": probe.has_audio,
        "video_start_us": probe.video_start_us,
    }


def encode_probe(probe: ProbeInfo) -> str:
    """Return the canonical persisted payload for normalized probe facts."""

    return json.dumps(_payload(probe), sort_keys=True, separators=(",", ":"))


def _required_int(payload: dict[str, object], name: str, *, positive: bool) -> int:
    value = payload[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProbeCacheError("cached video probe contains invalid evidence")
    if positive and value <= 0:
        raise ProbeCacheError("cached video probe contains invalid evidence")
    return value


def decode_probe_payload(payload_json: str) -> ProbeInfo:
    """Validate and decode one normalized probe payload."""

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise ProbeCacheError("cached video probe contains invalid evidence") from error
    expected = {
        "audio_channels",
        "audio_layout",
        "audio_sample_rate",
        "audio_start_us",
        "display_height",
        "display_width",
        "duration_us",
        "has_audio",
        "video_start_us",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ProbeCacheError("cached video probe contains invalid evidence")
    has_audio = payload["has_audio"]
    if not isinstance(has_audio, bool):
        raise ProbeCacheError("cached video probe contains invalid evidence")
    display_width = _required_int(payload, "display_width", positive=True)
    display_height = _required_int(payload, "display_height", positive=True)
    duration_us = _required_int(payload, "duration_us", positive=True)
    video_start_us = _required_int(payload, "video_start_us", positive=False)

    audio_fields = (
        payload["audio_start_us"],
        payload["audio_sample_rate"],
        payload["audio_channels"],
        payload["audio_layout"],
    )
    if not has_audio:
        if any(value is not None for value in audio_fields):
            raise ProbeCacheError("cached video probe contains invalid evidence")
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

    audio_start_us = _required_int(payload, "audio_start_us", positive=False)
    audio_sample_rate = _required_int(payload, "audio_sample_rate", positive=True)
    audio_channels = _required_int(payload, "audio_channels", positive=True)
    audio_layout = payload["audio_layout"]
    if not isinstance(audio_layout, str) or not audio_layout:
        raise ProbeCacheError("cached video probe contains invalid evidence")
    return ProbeInfo(
        display_width=display_width,
        display_height=display_height,
        duration_us=duration_us,
        video_start_us=video_start_us,
        audio_start_us=audio_start_us,
        audio_sample_rate=audio_sample_rate,
        audio_channels=audio_channels,
        audio_layout=audio_layout,
        has_audio=True,
    )


def decode_probe_evidence(
    records: list[cache_service.DerivedEvidence],
) -> dict[str, ProbeInfo]:
    """Decode validated records, rejecting duplicate content identities."""

    decoded: dict[str, ProbeInfo] = {}
    for record in records:
        if record.file_sha256 in decoded:
            raise ProbeCacheError("cached video probe contains duplicate evidence")
        decoded[record.file_sha256] = decode_probe_payload(record.payload_json)
    return decoded


def load_cached_probes(database: Path, runtime: str) -> dict[str, ProbeInfo]:
    """Load compatible normalized probes through coordinated cache access."""

    try:
        contents = cache_service.read_coordinated_cache(database)
        if contents is None:
            return {}
        records = [
            record
            for record in contents.evidence
            if record.evidence_type == VIDEO_PROBE_EVIDENCE_TYPE
            and record.algorithm == VIDEO_PROBE_ALGORITHM
            and record.runtime == runtime
        ]
        return decode_probe_evidence(records)
    except (cache_service.CacheError, sqlite3.Error, OSError) as error:
        raise ProbeCacheError("video probe cache cannot be read safely") from error


def build_probe_evidence(
    runtime: str, values: dict[str, ProbeInfo]
) -> tuple[cache_service.DerivedEvidence, ...]:
    """Build normalized probe records for one atomic cache publication."""

    return tuple(
        cache_service.DerivedEvidence(
            file_sha256=file_hash,
            evidence_type=VIDEO_PROBE_EVIDENCE_TYPE,
            algorithm=VIDEO_PROBE_ALGORITHM,
            runtime=runtime,
            payload_json=encode_probe(probe),
        )
        for file_hash, probe in sorted(values.items())
    )


def save_cached_probes(
    database: Path,
    runtime: str,
    values: dict[str, ProbeInfo],
) -> None:
    """Atomically publish normalized probe facts for content identities."""

    records = build_probe_evidence(runtime, values)
    if not records:
        return
    try:
        cache_service.publish_cache_update(
            database,
            lambda connection: cache_service.upsert_derived_evidence(
                connection, records
            ),
        )
    except cache_service.CacheError as error:
        raise ProbeCacheError("video probe cache cannot be updated safely") from error


def publish_video_inspection_batch(
    root: Path,
    database: Path,
    runtime: str,
    hashes: Iterable[tuple[Path, FileState, str]],
    probes: dict[str, ProbeInfo],
) -> None:
    """Publish hash observations and probe evidence in one cache transaction."""

    observations = build_hash_observations(root, hashes)
    evidence = build_probe_evidence(runtime, probes)
    if not observations and not evidence:
        return

    def update(connection: sqlite3.Connection) -> None:
        cache_service.upsert_file_observations(connection, observations)
        cache_service.upsert_derived_evidence(connection, evidence)

    try:
        cache_service.publish_cache_update(database, update)
    except cache_service.CacheError as error:
        raise ProbeCacheError(
            "video inspection cache cannot be updated safely"
        ) from error
