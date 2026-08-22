from __future__ import annotations

from pathlib import Path

import pytest

from pymo.file_safety import FileChangedError, FileState


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
