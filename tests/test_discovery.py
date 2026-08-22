from __future__ import annotations

import errno
from pathlib import Path

import pytest

from pymo import discovery
from pymo.discovery import DiscoveryError


def test_complete_walk_rejects_a_partial_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocked = tmp_path / "closed"

    def incomplete_walk(_root: Path, *, topdown: bool, onerror):
        assert topdown
        yield str(tmp_path), [], ["visible.txt"]
        onerror(OSError(errno.EACCES, "permission denied", str(blocked)))

    monkeypatch.setattr(discovery.os, "walk", incomplete_walk)

    with pytest.raises(DiscoveryError, match="1 location could not be read"):
        list(discovery.walk_complete(tmp_path))


def test_complete_directory_listing_never_returns_partial_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def inaccessible_scandir(_directory: Path):
        raise OSError(errno.EACCES, "permission denied")

    monkeypatch.setattr(discovery.os, "scandir", inaccessible_scandir)

    with pytest.raises(DiscoveryError, match="filesystem discovery was incomplete"):
        discovery.list_directory_complete(tmp_path)


def test_enumerated_entry_must_still_resolve() -> None:
    with pytest.raises(DiscoveryError, match="1 location could not be read"):
        discovery.entry_kind_complete(Path("media-collection/vanished.jpg"))


def test_walk_entry_rejects_a_changed_category(tmp_path: Path) -> None:
    directory = tmp_path / "became-a-directory"
    directory.mkdir()

    with pytest.raises(DiscoveryError, match="discovery changed"):
        discovery.walk_entry_kind_complete(directory, listed_as_directory=False)
