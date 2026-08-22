from __future__ import annotations

from pathlib import Path

from pymo.collection import CollectionLayout


def test_collection_layout_centralizes_owned_paths(tmp_path: Path) -> None:
    root = tmp_path / "media-collection"
    layout = CollectionLayout(root)

    assert layout.pics == root / "pics"
    assert layout.vids == root / "vids"
    assert layout.dups == root / "dups"
    assert layout.duplicate_pics == root / "dups" / "pics"
    assert layout.duplicate_vids == root / "dups" / "vids"
    assert layout.config == root / ".pymo.toml"
    assert layout.derived_cache == root / ".pymo.sqlite3"
    assert layout.derived_cache_lock == root / ".pymo.sqlite3.lock"
    assert layout.video_cache == layout.derived_cache
    assert layout.video_cache_lock == layout.derived_cache_lock
    assert layout.action_log == root / "media-collection-actions-log.jsonl"


def test_collection_layout_recognizes_only_its_duplicates_tree(
    tmp_path: Path,
) -> None:
    layout = CollectionLayout(tmp_path / "collection")

    assert layout.is_in_duplicates(layout.dups)
    assert layout.is_in_duplicates(layout.duplicate_pics / "copy.png")
    assert not layout.is_in_duplicates(layout.pics / "photo.png")
    assert not layout.is_in_duplicates(tmp_path / "other" / "dups")
