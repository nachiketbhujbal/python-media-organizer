"""Canonical paths for one media collection.

The directory and state-file names here are product invariants rather than
user preferences. Making them configurable would weaken cross-tool ownership,
portable undo, and compatibility with existing collections.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CollectionLayout:
    """Resolve every pymo-owned path from a single collection root."""

    root: Path

    @property
    def pics(self) -> Path:
        return self.root / "pics"

    @property
    def vids(self) -> Path:
        return self.root / "vids"

    @property
    def dups(self) -> Path:
        return self.root / "dups"

    @property
    def duplicate_pics(self) -> Path:
        return self.dups / "pics"

    @property
    def duplicate_vids(self) -> Path:
        return self.dups / "vids"

    @property
    def config(self) -> Path:
        return self.root / ".pymo.toml"

    @property
    def video_cache(self) -> Path:
        return self.root / ".pymo.sqlite3"

    @property
    def action_log(self) -> Path:
        collection_name = self.root.name or "media-collection"
        return self.root / f"{collection_name}-actions-log.jsonl"

    @property
    def legacy_action_log(self) -> Path:
        return self.root / "media_actions.jsonl"

    def is_in_duplicates(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            return False
        return bool(relative.parts) and relative.parts[0] == self.dups.name
