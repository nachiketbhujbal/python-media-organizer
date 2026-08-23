from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from pymo.cache import service as cache_service
from pymo.cache.probes import (
    ProbeCacheError,
    decode_probe_payload,
    encode_probe,
    load_cached_probes,
    save_cached_probes,
)
from pymo.collection import CollectionLayout
from pymo.duplicates import videos as video_duplicates
from pymo.video import ProbeInfo


def _probe(*, has_audio: bool = False) -> ProbeInfo:
    return ProbeInfo(
        display_width=64,
        display_height=48,
        duration_us=1_000_000,
        video_start_us=-20_000,
        audio_start_us=0 if has_audio else None,
        audio_sample_rate=48_000 if has_audio else None,
        audio_channels=2 if has_audio else None,
        audio_layout="stereo" if has_audio else None,
        has_audio=has_audio,
    )


@pytest.mark.parametrize("probe", [_probe(), _probe(has_audio=True)])
def test_probe_payload_round_trip(probe: ProbeInfo) -> None:
    assert decode_probe_payload(encode_probe(probe)) == probe


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "{}",
        '{"audio_channels":null,"audio_layout":null,"audio_sample_rate":null,'
        '"audio_start_us":null,"display_height":48,"display_width":64,'
        '"duration_us":1000000,"has_audio":true,"video_start_us":0}',
        '{"audio_channels":null,"audio_layout":null,"audio_sample_rate":null,'
        '"audio_start_us":null,"display_height":48,"display_width":0,'
        '"duration_us":1000000,"has_audio":false,"video_start_us":0}',
    ],
)
def test_probe_payload_rejects_malformed_evidence(payload: str) -> None:
    with pytest.raises(ProbeCacheError, match="invalid evidence"):
        decode_probe_payload(payload)


def test_probe_cache_requires_exact_runtime(tmp_path: Path) -> None:
    database = CollectionLayout(tmp_path).derived_cache
    file_hash = "a" * 64
    probe = _probe()

    save_cached_probes(database, "ffprobe-runtime-a", {file_hash: probe})

    assert load_cached_probes(database, "ffprobe-runtime-a") == {file_hash: probe}
    assert load_cached_probes(database, "ffprobe-runtime-b") == {}


def test_video_inspection_reuses_probe_for_unchanged_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    path = vids / "garden.mp4"
    path.write_bytes(b"synthetic video bytes")
    database = CollectionLayout(tmp_path).derived_cache
    calls = 0
    publications = 0
    publish = cache_service.publish_cache_update

    def probe_once(*_args: object) -> ProbeInfo:
        nonlocal calls
        calls += 1
        return _probe()

    def count_publication(
        database_path: Path, updater: Callable[[sqlite3.Connection], None]
    ) -> None:
        nonlocal publications
        publications += 1
        publish(database_path, updater)

    monkeypatch.setattr(video_duplicates, "probe_video", probe_once)
    monkeypatch.setattr(cache_service, "publish_cache_update", count_publication)
    first, _, first_skips = video_duplicates.inspect_video_paths(
        tmp_path,
        [path],
        "ffprobe",
        15,
        database,
        32,
        "ffprobe-runtime",
    )
    second, _, second_skips = video_duplicates.inspect_video_paths(
        tmp_path,
        [path],
        "ffprobe",
        15,
        database,
        32,
        "ffprobe-runtime",
    )

    assert first_skips == second_skips == []
    assert calls == 1
    assert publications == 1
    assert first[0].probe_cached is False
    assert second[0].probe_cached is True
    assert second[0].byte_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_video_inspection_reprobes_for_a_different_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    path = vids / "garden.mp4"
    path.write_bytes(b"synthetic video bytes")
    database = CollectionLayout(tmp_path).derived_cache
    calls = 0

    def count_probe(*_args: object) -> ProbeInfo:
        nonlocal calls
        calls += 1
        return _probe()

    monkeypatch.setattr(video_duplicates, "probe_video", count_probe)
    for runtime in ("ffprobe-runtime-a", "ffprobe-runtime-b"):
        records, _, skipped = video_duplicates.inspect_video_paths(
            tmp_path, [path], "ffprobe", 15, database, 32, runtime
        )
        assert skipped == []
        assert records[0].probe_cached is False

    assert calls == 2
