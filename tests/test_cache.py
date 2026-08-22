from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from pymo.cache import CacheError, create_cache_stage, locked_cache_directory


def test_cache_lock_is_anchored_to_cache_directory_not_media_root(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    cache_directory = tmp_path / "derived-state"
    media_root.mkdir()
    cache_directory.mkdir()
    lock = cache_directory / "cache.lock"

    with locked_cache_directory(cache_directory, lock, exclusive=False) as locked:
        assert locked.directory == cache_directory
        assert locked.descriptor >= 0

    assert lock.is_file()
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    assert list(media_root.iterdir()) == []


def test_cache_lock_rejects_a_path_outside_its_directory(tmp_path: Path) -> None:
    cache_directory = tmp_path / "derived-state"
    cache_directory.mkdir()
    outside = tmp_path / "outside.lock"

    with pytest.raises(CacheError, match="unexpected SQLite cache lock path"):
        with locked_cache_directory(cache_directory, outside, exclusive=True):
            pytest.fail("an outside lock path must not be opened")

    assert not outside.exists()


def test_cache_stage_is_private_and_created_in_the_pinned_directory(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "cache.lock"

    with locked_cache_directory(tmp_path, lock, exclusive=True) as locked:
        name, descriptor = create_cache_stage(locked.descriptor)
        try:
            state = os.fstat(descriptor)
            assert stat.S_ISREG(state.st_mode)
            assert stat.S_IMODE(state.st_mode) == 0o600
            assert state.st_nlink == 1
            assert (tmp_path / name).is_file()
        finally:
            os.close(descriptor)
            os.unlink(name, dir_fd=locked.descriptor)

    assert not list(tmp_path.glob(".pymo.sqlite3.new.*"))
