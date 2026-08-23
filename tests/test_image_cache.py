from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image
from PIL import __version__ as PILLOW_VERSION

from pymo.action_log import action_log_path
from pymo.cache import service as cache_service
from pymo.cache.hashes import observation_scope
from pymo.cache.images import (
    IMAGE_PIXEL_ALGORITHM,
    IMAGE_PIXEL_EVIDENCE_TYPE,
    ImageCacheError,
    decode_pixel_payload,
    encode_pixel_hash,
    load_cached_pixel_hashes,
    publish_image_analysis_batch,
)
from pymo.collection import CollectionLayout
from pymo.duplicates import images as image_duplicates
from pymo.file_safety import FileState


def test_displayed_pixel_payload_round_trip() -> None:
    digest = "a" * 64
    assert decode_pixel_payload(encode_pixel_hash(digest)) == digest


@pytest.mark.parametrize(
    "payload",
    ["not-json", "{}", '{"digest":"short"}', '{"digest":1}'],
)
def test_displayed_pixel_payload_rejects_malformed_evidence(payload: str) -> None:
    with pytest.raises(ImageCacheError, match="invalid evidence"):
        decode_pixel_payload(payload)


def test_displayed_pixel_cache_requires_exact_runtime(tmp_path: Path) -> None:
    path = tmp_path / "garden.png"
    Image.new("RGB", (2, 2), "green").save(path)
    state = FileState.capture(path)
    database = CollectionLayout(tmp_path).derived_cache
    publish_image_analysis_batch(
        tmp_path,
        database,
        "Pillow runtime-a",
        [(path, state, "a" * 64)],
        {"a" * 64: "b" * 64},
    )

    assert load_cached_pixel_hashes(database, "Pillow runtime-a") == {
        "a" * 64: "b" * 64
    }
    assert load_cached_pixel_hashes(database, "Pillow runtime-b") == {}


def test_image_analysis_reuses_unchanged_hash_and_pixel_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pics = tmp_path / "pics"
    pics.mkdir()
    path = pics / "garden.png"
    Image.new("RGB", (2, 2), "green").save(path)
    database = CollectionLayout(tmp_path).derived_cache
    calls = 0
    publications = 0
    pixel_hash = image_duplicates.displayed_pixel_hash
    publish = cache_service.publish_cache_update

    def count_pixels(descriptor: int) -> str:
        nonlocal calls
        calls += 1
        return pixel_hash(descriptor)

    def count_publication(
        database_path: Path, updater: Callable[[sqlite3.Connection], None]
    ) -> None:
        nonlocal publications
        publications += 1
        publish(database_path, updater)

    monkeypatch.setattr(image_duplicates, "displayed_pixel_hash", count_pixels)
    monkeypatch.setattr(cache_service, "publish_cache_update", count_publication)
    first = image_duplicates.analyze_images(
        tmp_path, [path], 15, database, 32, "Pillow runtime"
    )
    second = image_duplicates.analyze_images(
        tmp_path, [path], 15, database, 32, "Pillow runtime"
    )

    assert first[2] == second[2] == []
    assert calls == 1
    assert publications == 1
    first_record = next(iter(first[0]), None)
    assert first_record is None
    assert load_cached_pixel_hashes(database, "Pillow runtime")


def test_image_apply_rechecks_a_cached_byte_identity_before_state_creation(
    tmp_path: Path,
) -> None:
    pics = tmp_path / "pics"
    pics.mkdir()
    first = pics / "garden.png"
    second = pics / "harbor.png"
    Image.new("RGB", (2, 2), "green").save(first)
    Image.new("RGB", (2, 2), "green").save(second)
    layout = CollectionLayout(tmp_path)
    wrong_hash = "a" * 64
    connection = sqlite3.connect(layout.derived_cache)
    cache_service.initialize_schema(connection)
    cache_service.upsert_file_observations(
        connection,
        [
            cache_service.FileObservation(
                scope=observation_scope(tmp_path),
                relative_path=path.relative_to(tmp_path).as_posix(),
                device=(state := FileState.capture(path)).device,
                inode=state.inode,
                size=state.size,
                modified_ns=state.modified_ns,
                changed_ns=state.changed_ns,
                byte_sha256=wrong_hash,
            )
            for path in (first, second)
        ],
    )
    cache_service.upsert_derived_evidence(
        connection,
        [
            cache_service.DerivedEvidence(
                file_sha256=wrong_hash,
                evidence_type=IMAGE_PIXEL_EVIDENCE_TYPE,
                algorithm=IMAGE_PIXEL_ALGORITHM,
                runtime=f"Pillow {PILLOW_VERSION}",
                payload_json=encode_pixel_hash("b" * 64),
            )
        ],
    )
    connection.commit()
    connection.close()

    assert image_duplicates.main([str(tmp_path), "--apply"]) == 1
    assert first.is_file()
    assert second.is_file()
    assert not layout.dups.exists()
    assert not action_log_path(tmp_path).exists()
