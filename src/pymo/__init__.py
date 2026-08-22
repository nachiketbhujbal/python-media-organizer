"""Safe, local-first media organization tools."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("python-media-organizer")
except PackageNotFoundError:
    # Source-only execution can occur before the project has been installed.
    __version__ = "0+unknown"
