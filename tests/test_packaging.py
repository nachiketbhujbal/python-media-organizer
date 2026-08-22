from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

import pymo


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_version_matches_installed_distribution() -> None:
    assert pymo.__version__ == importlib.metadata.version("python-media-organizer")


def test_project_uses_standard_vcs_versioning() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as project_file:
        configuration = tomllib.load(project_file)

    assert configuration["build-system"]["build-backend"] == "hatchling.build"
    assert configuration["project"]["dynamic"] == ["version"]
    assert "version" not in configuration["project"]
    assert configuration["tool"]["hatch"]["version"]["source"] == "vcs"
