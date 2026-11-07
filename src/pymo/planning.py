"""Explicit read interface for deterministic namespace planning.

Logical names drive policy; all content reads remain anchored to the unchanged
physical source. The virtual implementation has no filesystem mutation API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pymo.classification import Classifier


class PlanningView(Protocol):
    def paths(self) -> list[Path]: ...

    def exists(self, path: Path) -> bool: ...

    def classify(self, path: Path, classifier: Classifier) -> tuple[str, str]: ...

    def timestamp(self, path: Path) -> str | None: ...
