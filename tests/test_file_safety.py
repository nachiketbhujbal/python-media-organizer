from __future__ import annotations

import os
from pathlib import Path

import pytest

from pymo.file_safety import FileChangedError, FileState, open_stable_file


def test_file_state_accepts_an_unchanged_regular_file(tmp_path: Path) -> None:
    path = tmp_path / "stable.bin"
    path.write_bytes(b"stable")
    state = FileState.capture(path)

    state.require_unchanged(path, "test analysis")


def test_file_state_rejects_content_change_and_replacement(tmp_path: Path) -> None:
    path = tmp_path / "changing.bin"
    path.write_bytes(b"first")
    changed = FileState.capture(path)
    path.write_bytes(b"second")

    with pytest.raises(FileChangedError, match="changed during test analysis"):
        changed.require_unchanged(path, "test analysis")

    replaced = FileState.capture(path)
    path.unlink()
    path.write_bytes(b"second")
    with pytest.raises(FileChangedError, match="changed during test analysis"):
        replaced.require_unchanged(path, "test analysis")


def test_file_state_rejects_symbolic_links(tmp_path: Path) -> None:
    target = tmp_path / "target.bin"
    target.write_bytes(b"target")
    link = tmp_path / "link.bin"
    link.symlink_to(target)

    with pytest.raises(FileChangedError, match="not a regular file"):
        FileState.capture(link)


def test_stable_file_descriptor_pins_content_during_path_swap(tmp_path: Path) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    path = root / "stable.bin"
    path.write_bytes(b"original")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    state = FileState.capture(path)

    with pytest.raises(FileChangedError, match="changed during test read"):
        with open_stable_file(root, path, state, "test read") as descriptor:
            path.unlink()
            path.symlink_to(outside)
            assert os.pread(descriptor, state.size, 0) == b"original"


def test_stable_file_descriptor_rejects_symlinked_parent(tmp_path: Path) -> None:
    root = tmp_path / "media-collection"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    target = outside / "media.bin"
    target.write_bytes(b"outside")
    linked_directory = root / "linked"
    linked_directory.symlink_to(outside, target_is_directory=True)
    path = linked_directory / target.name
    state = FileState.capture(path)

    with pytest.raises(FileChangedError, match="changed during test read"):
        with open_stable_file(root, path, state, "test read"):
            pytest.fail("a symlinked parent must never be opened")
