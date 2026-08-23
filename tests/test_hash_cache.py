from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import pytest
from PIL import Image

from pymo import scan
from pymo.action_log import action_log_path
from pymo.collection import CollectionLayout
from pymo.config import load_config
from pymo.duplicates import videos as video_duplicates
from pymo.duplicates.videos import ProbeInfo, VideoRecord
from pymo.file_safety import FileChangedError, FileState
from pymo.hash_cache import (
    HashCacheError,
    load_cached_hashes,
    save_cached_hash,
    save_cached_hashes,
)


def _probe() -> ProbeInfo:
    return ProbeInfo(
        display_width=64,
        display_height=48,
        duration_us=1_000_000,
        video_start_us=0,
        audio_start_us=None,
        audio_sample_rate=None,
        audio_channels=None,
        audio_layout=None,
        has_audio=False,
    )


def test_hash_cache_reuses_only_an_exact_current_file_identity(tmp_path: Path) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    path = root / "leaf.bin"
    path.write_bytes(b"first content")
    state = FileState.capture(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    database = tmp_path / "derived" / "cache.sqlite3"
    database.parent.mkdir()

    save_cached_hash(root, database, path, state, digest)

    assert load_cached_hashes(root, database, {path: state}, coordinated=True) == {
        path: digest
    }
    path.write_bytes(b"replacement content")
    assert (
        load_cached_hashes(
            root, database, {path: FileState.capture(path)}, coordinated=True
        )
        == {}
    )


def test_hash_cache_batch_preserves_collection_scope_and_relative_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    first = root / "first.bin"
    second = root / "nested" / "second.bin"
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    values = tuple(
        (
            path,
            FileState.capture(path),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in (first, second)
    )
    database = tmp_path / "cache.sqlite3"

    save_cached_hashes(root, database, values)

    states = {path: state for path, state, _ in values}
    assert load_cached_hashes(root, database, states, coordinated=False) == {
        path: digest for path, _, digest in values
    }


def test_hash_cache_concurrent_writers_serialize_without_losing_records(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    paths = [root / "first.bin", root / "second.bin"]
    for number, path in enumerate(paths):
        path.write_bytes(f"content {number}".encode())
    database = tmp_path / "cache.sqlite3"
    started = [threading.Event(), threading.Event()]
    finished = [threading.Event(), threading.Event()]
    errors: list[BaseException] = []

    def save(number: int) -> None:
        path = paths[number]
        started[number].set()
        try:
            save_cached_hash(
                root,
                database,
                path,
                FileState.capture(path),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        except BaseException as error:
            errors.append(error)
        finally:
            finished[number].set()

    threads = [threading.Thread(target=save, args=(number,)) for number in range(2)]
    for thread in threads:
        thread.start()
    assert all(event.wait(1) for event in started)
    for thread in threads:
        thread.join(timeout=5)

    assert not errors, (
        repr(errors[0].__cause__.__cause__)
        if errors and errors[0].__cause__ is not None
        else ""
    )
    assert all(event.is_set() for event in finished)
    states = {path: FileState.capture(path) for path in paths}
    assert set(load_cached_hashes(root, database, states, coordinated=True)) == set(
        paths
    )


def test_hash_cache_read_only_lookup_creates_no_missing_state(tmp_path: Path) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    path = root / "leaf.bin"
    path.write_bytes(b"content")
    absent = tmp_path / "absent" / "cache.sqlite3"

    assert (
        load_cached_hashes(
            root,
            absent,
            {path: FileState.capture(path)},
            coordinated=False,
        )
        == {}
    )

    assert not absent.parent.exists()


def test_hash_cache_rejects_corrupt_sqlite_without_rewriting_it(tmp_path: Path) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    path = root / "leaf.bin"
    path.write_bytes(b"content")
    database = tmp_path / "cache.sqlite3"
    database.write_bytes(b"not sqlite")
    original = database.read_bytes()

    with pytest.raises(HashCacheError, match="cannot be read safely"):
        load_cached_hashes(
            root,
            database,
            {path: FileState.capture(path)},
            coordinated=False,
        )

    assert database.read_bytes() == original
    assert not database.with_name(f"{database.name}.lock").exists()


def test_video_inspection_reuses_hash_and_persists_a_new_hash(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    vids = root / "vids"
    vids.mkdir(parents=True)
    path = vids / "clip.mp4"
    path.write_bytes(b"video bytes")
    database = tmp_path / "external" / "cache.sqlite3"
    database.parent.mkdir()
    monkeypatch.setattr(video_duplicates, "probe_video", lambda *_: _probe())

    first, _, first_skips = video_duplicates.inspect_video_paths(
        root, [path], "ffprobe", 15, database, 32
    )
    assert not first_skips
    assert first[0].byte_sha256_cached is False

    monkeypatch.setattr(
        video_duplicates,
        "sha256_descriptor",
        lambda *_: pytest.fail("a current cached hash must avoid the repeated read"),
    )
    second, _, second_skips = video_duplicates.inspect_video_paths(
        root, [path], "ffprobe", 15, database, 32
    )

    assert not second_skips
    assert second[0].byte_sha256 == first[0].byte_sha256
    assert second[0].byte_sha256_cached is True
    assert not CollectionLayout(root).video_cache.exists()
    assert not action_log_path(root).exists()


def test_video_hash_batches_survive_interruption_after_publication(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    vids = root / "vids"
    vids.mkdir(parents=True)
    paths = [vids / f"clip-{number}.mp4" for number in range(3)]
    for number, path in enumerate(paths):
        path.write_bytes(f"video bytes {number}".encode())
    database = tmp_path / "cache.sqlite3"
    calls = 0

    def interrupt_third(*_args) -> ProbeInfo:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise KeyboardInterrupt
        return _probe()

    monkeypatch.setattr(video_duplicates, "probe_video", interrupt_third)

    with pytest.raises(KeyboardInterrupt):
        video_duplicates.inspect_video_paths(root, paths, "ffprobe", 15, database, 2)

    states = {path: FileState.capture(path) for path in paths}
    assert set(load_cached_hashes(root, database, states, coordinated=True)) == set(
        paths[:2]
    )


def test_video_apply_rehashes_cached_records_before_creating_state(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    vids = root / "vids"
    vids.mkdir(parents=True)
    first_path = vids / "first.mp4"
    second_path = vids / "second.mp4"
    first_path.write_bytes(b"same")
    second_path.write_bytes(b"same")
    digest = hashlib.sha256(b"same").hexdigest()
    records = [
        VideoRecord(
            path=path,
            byte_sha256=digest,
            state=FileState.capture(path),
            probe=_probe(),
            byte_sha256_cached=True,
        )
        for path in (first_path, second_path)
    ]
    target = root / "dups" / "vids" / "duplicate.mp4"
    monkeypatch.setattr(video_duplicates, "sha256_descriptor", lambda _: "0" * 64)

    with pytest.raises(FileChangedError, match="cached video hash recheck"):
        video_duplicates.apply_video_moves(
            root, [records], [(records[0], records[1], target)]
        )

    assert first_path.is_file()
    assert second_path.is_file()
    assert not (root / "dups").exists()
    assert not action_log_path(root).exists()


def test_checksum_scan_reuses_external_hashes_without_writing_collection_state(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    first = root / "first.png"
    second = root / "second.png"
    Image.new("RGB", (2, 2), "green").save(first)
    Image.new("RGB", (2, 2), "green").save(second)
    database = tmp_path / "external" / "cache.sqlite3"
    database.parent.mkdir()
    values = tuple(
        (
            path,
            FileState.capture(path),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in (first, second)
    )
    save_cached_hashes(root, database, values)
    monkeypatch.setattr(
        scan,
        "_stable_sha256",
        lambda *_: pytest.fail("scan should reuse both current hashes"),
    )

    report = scan.build_report(root, load_config(root), 1, True, False, False, database)

    exact = report["duplicate_potential"]["exact_bytes"]
    assert exact["groups"] == 1
    assert exact["cache_hits"] == 2
    assert exact["computed_hashes"] == 0
    assert not CollectionLayout(root).video_cache.exists()
    assert not action_log_path(root).exists()
