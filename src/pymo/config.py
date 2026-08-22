"""Structured, local-only configuration and shared ignore rules."""

from __future__ import annotations

import argparse
import fnmatch
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


CONFIG_FILENAME = ".pymo.toml"
CONFIG_VERSION = 1


class ConfigError(ValueError):
    """Raised when a pymo configuration cannot be used safely."""


@dataclass(frozen=True)
class PymoConfig:
    file_patterns: tuple[str, ...]
    directory_patterns: tuple[str, ...]
    custom_path: Path | None = None

    @staticmethod
    def _matches(path: Path, root: Path, patterns: tuple[str, ...]) -> bool:
        try:
            relative = path.relative_to(root).as_posix().casefold()
        except ValueError:
            return False
        basename = path.name.casefold()
        return any(
            fnmatch.fnmatchcase(basename, pattern.casefold())
            or fnmatch.fnmatchcase(relative, pattern.casefold())
            for pattern in patterns
        )

    def ignores_directory(self, path: Path, root: Path) -> bool:
        current = path
        while current != root:
            if self._matches(current, root, self.directory_patterns):
                return True
            if root not in current.parents:
                return False
            current = current.parent
        return False

    def ignores_file(self, path: Path, root: Path) -> bool:
        if self.custom_path is not None and path.absolute() == self.custom_path:
            return True
        if self._matches(path, root, self.file_patterns):
            return True
        return self.ignores_directory(path.parent, root)


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        help=(
            f"alternate TOML configuration (default: COLLECTION/{CONFIG_FILENAME})"
        ),
    )


def _patterns(value: Any, key: str, source: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{source}: ignore.{key} must be an array of strings")

    result: list[str] = []
    for original in value:
        pattern = original.strip().replace("\\", "/")
        if not pattern:
            raise ConfigError(f"{source}: ignore.{key} contains an empty pattern")
        has_drive = (
            len(pattern) >= 2
            and pattern[0].isalpha()
            and pattern[1] == ":"
        )
        if pattern.startswith("/") or has_drive or ".." in pattern.split("/"):
            raise ConfigError(
                f"{source}: ignore.{key} patterns must stay collection-relative: "
                f"{original!r}"
            )
        result.append(pattern)
    return tuple(result)


def _parse(
    document: dict[str, Any], source: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    unknown = set(document).difference({"version", "ignore"})
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigError(f"{source}: unknown top-level key(s): {names}")
    if document.get("version") != CONFIG_VERSION:
        raise ConfigError(f"{source}: version must be {CONFIG_VERSION}")

    ignore = document.get("ignore", {})
    if not isinstance(ignore, dict):
        raise ConfigError(f"{source}: ignore must be a TOML table")
    unknown_ignore = set(ignore).difference({"files", "directories"})
    if unknown_ignore:
        raise ConfigError(
            f"{source}: unknown ignore key(s): {', '.join(sorted(unknown_ignore))}"
        )
    return (
        _patterns(ignore.get("files"), "files", source),
        _patterns(ignore.get("directories"), "directories", source),
    )


def _read_file(path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if path.is_symlink() or not path.is_file():
        raise ConfigError(f"configuration is not a regular file: {path}")
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"cannot read configuration {path}: {error}") from error
    return _parse(document, str(path))


def _deduplicate(patterns: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        key = pattern.casefold()
        if key not in seen:
            seen.add(key)
            result.append(pattern)
    return tuple(result)


def load_config(root: Path, explicit_path: Path | None = None) -> PymoConfig:
    try:
        default_resource = resources.files("pymo").joinpath("default_config.toml")
        with default_resource.open("rb") as handle:
            defaults = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"cannot read packaged defaults: {error}") from error
    default_files, default_directories = _parse(defaults, "packaged defaults")

    custom_path: Path | None
    if explicit_path is not None:
        custom_path = explicit_path.expanduser().resolve()
    else:
        candidate = root / CONFIG_FILENAME
        custom_path = (
            candidate if candidate.exists() or candidate.is_symlink() else None
        )

    custom_files: tuple[str, ...] = ()
    custom_directories: tuple[str, ...] = ()
    if custom_path is not None:
        custom_files, custom_directories = _read_file(custom_path)

    return PymoConfig(
        file_patterns=_deduplicate(default_files + custom_files),
        directory_patterns=_deduplicate(default_directories + custom_directories),
        custom_path=custom_path,
    )


def ignored_summary(paths: list[Path]) -> str | None:
    if not paths:
        return None
    return f"Ignored by configuration: {len(paths)} path(s)."
