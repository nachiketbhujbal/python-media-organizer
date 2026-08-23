"""Validated, local-only configuration for pymo policy."""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from pymo.collection import CollectionLayout

# This bootstraps validation before any configuration can be trusted. It is an
# on-disk compatibility identifier, not a user-configurable preference.
CONFIG_SCHEMA_VERSION = 1


class ConfigError(ValueError):
    """Raised when a pymo configuration cannot be used safely."""


@dataclass(frozen=True)
class IgnoreConfig:
    files: tuple[str, ...]
    directories: tuple[str, ...]


@dataclass(frozen=True)
class ClassificationConfig:
    image_extensions: frozenset[str]
    video_extensions: frozenset[str]
    video_application_mime_types: frozenset[str]
    generic_mime_types: frozenset[str]


@dataclass(frozen=True)
class RenameConfig:
    noise_tokens: frozenset[str]


@dataclass(frozen=True)
class ImageDuplicateConfig:
    extensions: frozenset[str]


@dataclass(frozen=True)
class VideoDuplicateConfig:
    decode_timeout_seconds: int


@dataclass(frozen=True)
class PerformanceConfig:
    scan_workers: int
    progress_interval_seconds: int
    cache_publication_batch_size: int


@dataclass(frozen=True)
class PymoConfig:
    ignore: IgnoreConfig
    classification: ClassificationConfig
    rename: RenameConfig
    image_duplicates: ImageDuplicateConfig
    video_duplicates: VideoDuplicateConfig
    performance: PerformanceConfig
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
            if self._matches(current, root, self.ignore.directories):
                return True
            if root not in current.parents:
                return False
            current = current.parent
        return False

    def ignores_file(self, path: Path, root: Path) -> bool:
        if self.custom_path is not None and path.absolute() == self.custom_path:
            return True
        if self._matches(path, root, self.ignore.files):
            return True
        return self.ignores_directory(path.parent, root)


@dataclass(frozen=True)
class _ConfigLayer:
    ignore_files: tuple[str, ...] = ()
    ignore_directories: tuple[str, ...] = ()
    image_extensions: tuple[str, ...] = ()
    video_extensions: tuple[str, ...] = ()
    video_application_mime_types: tuple[str, ...] = ()
    generic_mime_types: tuple[str, ...] = ()
    rename_noise_tokens: tuple[str, ...] = ()
    image_duplicate_extensions: tuple[str, ...] = ()
    decode_timeout_seconds: int | None = None
    scan_workers: int | None = None
    progress_interval_seconds: int | None = None
    cache_publication_batch_size: int | None = None


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        help="alternate TOML configuration (default: COLLECTION/.pymo.toml)",
    )


def add_show_ignored_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--show-ignored",
        action="store_true",
        help="list ignored paths relative to the collection root",
    )


def _table(
    document: dict[str, Any],
    name: str,
    allowed_keys: frozenset[str],
    source: str,
) -> dict[str, Any]:
    value = document.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: {name} must be a TOML table")
    unknown = set(value).difference(allowed_keys)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigError(f"{source}: unknown {name} key(s): {names}")
    return value


def _strings(
    value: Any,
    qualified_key: str,
    source: str,
    normalize: Callable[[str], str],
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{source}: {qualified_key} must be an array of strings")
    result: list[str] = []
    for original in value:
        try:
            normalized = normalize(original)
        except ConfigError as error:
            raise ConfigError(f"{source}: {qualified_key}: {error}") from error
        if not normalized:
            raise ConfigError(f"{source}: {qualified_key} contains an empty value")
        result.append(normalized)
    return tuple(result)


def _ignore_pattern(value: str) -> str:
    pattern = value.strip().replace("\\", "/")
    has_drive = len(pattern) >= 2 and pattern[0].isalpha() and pattern[1] == ":"
    if pattern.startswith("/") or has_drive or ".." in pattern.split("/"):
        raise ConfigError(f"ignore patterns must stay collection-relative: {value!r}")
    return pattern


def _extension(value: str) -> str:
    extension = value.strip().casefold()
    if not re.fullmatch(r"\.[a-z0-9][a-z0-9.+-]*", extension):
        raise ConfigError(f"invalid media extension: {value!r}")
    return extension


def _mime_type(value: str) -> str:
    mime_type = value.strip().casefold()
    if not re.fullmatch(r"[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*", mime_type):
        raise ConfigError(f"invalid MIME type: {value!r}")
    return mime_type


def _noise_token(value: str) -> str:
    token = value.strip().casefold()
    if not re.fullmatch(r"[a-z0-9]+", token):
        raise ConfigError(f"invalid rename noise token: {value!r}")
    return token


def _parse(document: dict[str, Any], source: str) -> _ConfigLayer:
    sections = frozenset(
        {
            "version",
            "ignore",
            "classification",
            "rename",
            "image_duplicates",
            "video_duplicates",
            "performance",
        }
    )
    unknown = set(document).difference(sections)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigError(f"{source}: unknown top-level key(s): {names}")
    version = document.get("version")
    if isinstance(version, bool) or version != CONFIG_SCHEMA_VERSION:
        raise ConfigError(f"{source}: version must be {CONFIG_SCHEMA_VERSION}")

    ignore = _table(document, "ignore", frozenset({"files", "directories"}), source)
    classification = _table(
        document,
        "classification",
        frozenset(
            {
                "image_extensions",
                "video_extensions",
                "video_application_mime_types",
                "generic_mime_types",
            }
        ),
        source,
    )
    rename = _table(document, "rename", frozenset({"noise_tokens"}), source)
    image_duplicates = _table(
        document, "image_duplicates", frozenset({"extensions"}), source
    )
    video_duplicates = _table(
        document,
        "video_duplicates",
        frozenset({"decode_timeout_seconds"}),
        source,
    )
    performance = _table(
        document,
        "performance",
        frozenset(
            {
                "scan_workers",
                "progress_interval_seconds",
                "cache_publication_batch_size",
            }
        ),
        source,
    )

    timeout = video_duplicates.get("decode_timeout_seconds")
    if timeout is not None:
        if isinstance(timeout, bool) or not isinstance(timeout, int):
            raise ConfigError(
                f"{source}: video_duplicates.decode_timeout_seconds must be an integer"
            )
        if not 1 <= timeout <= 86_400:
            raise ConfigError(
                f"{source}: video_duplicates.decode_timeout_seconds must be "
                "between 1 and 86400"
            )

    scan_workers = performance.get("scan_workers")
    if scan_workers is not None:
        if isinstance(scan_workers, bool) or not isinstance(scan_workers, int):
            raise ConfigError(f"{source}: performance.scan_workers must be an integer")
        if not 1 <= scan_workers <= 32:
            raise ConfigError(
                f"{source}: performance.scan_workers must be between 1 and 32"
            )

    progress_interval = performance.get("progress_interval_seconds")
    if progress_interval is not None:
        if isinstance(progress_interval, bool) or not isinstance(
            progress_interval, int
        ):
            raise ConfigError(
                f"{source}: performance.progress_interval_seconds must be an integer"
            )
        if not 1 <= progress_interval <= 3_600:
            raise ConfigError(
                f"{source}: performance.progress_interval_seconds must be "
                "between 1 and 3600"
            )

    cache_batch_size = performance.get("cache_publication_batch_size")
    if cache_batch_size is not None:
        if isinstance(cache_batch_size, bool) or not isinstance(cache_batch_size, int):
            raise ConfigError(
                f"{source}: performance.cache_publication_batch_size must be "
                "an integer"
            )
        if not 1 <= cache_batch_size <= 1_000:
            raise ConfigError(
                f"{source}: performance.cache_publication_batch_size must be "
                "between 1 and 1000"
            )

    return _ConfigLayer(
        ignore_files=_strings(
            ignore.get("files"), "ignore.files", source, _ignore_pattern
        ),
        ignore_directories=_strings(
            ignore.get("directories"),
            "ignore.directories",
            source,
            _ignore_pattern,
        ),
        image_extensions=_strings(
            classification.get("image_extensions"),
            "classification.image_extensions",
            source,
            _extension,
        ),
        video_extensions=_strings(
            classification.get("video_extensions"),
            "classification.video_extensions",
            source,
            _extension,
        ),
        video_application_mime_types=_strings(
            classification.get("video_application_mime_types"),
            "classification.video_application_mime_types",
            source,
            _mime_type,
        ),
        generic_mime_types=_strings(
            classification.get("generic_mime_types"),
            "classification.generic_mime_types",
            source,
            _mime_type,
        ),
        rename_noise_tokens=_strings(
            rename.get("noise_tokens"),
            "rename.noise_tokens",
            source,
            _noise_token,
        ),
        image_duplicate_extensions=_strings(
            image_duplicates.get("extensions"),
            "image_duplicates.extensions",
            source,
            _extension,
        ),
        decode_timeout_seconds=timeout,
        scan_workers=scan_workers,
        progress_interval_seconds=progress_interval,
        cache_publication_batch_size=cache_batch_size,
    )


def _read_file(path: Path) -> _ConfigLayer:
    if path.is_symlink() or not path.is_file():
        raise ConfigError(f"configuration is not a regular file: {path}")
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"cannot read configuration {path}: {error}") from error
    return _parse(document, str(path))


def _deduplicate(*groups: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in (item for group in groups for item in group):
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def _packaged_defaults() -> _ConfigLayer:
    try:
        resource = resources.files("pymo").joinpath("default_config.toml")
        with resource.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"cannot read packaged defaults: {error}") from error
    defaults = _parse(document, "packaged defaults")
    required_arrays = {
        "ignore.files": defaults.ignore_files,
        "ignore.directories": defaults.ignore_directories,
        "classification.image_extensions": defaults.image_extensions,
        "classification.video_extensions": defaults.video_extensions,
        "classification.video_application_mime_types": (
            defaults.video_application_mime_types
        ),
        "classification.generic_mime_types": defaults.generic_mime_types,
        "rename.noise_tokens": defaults.rename_noise_tokens,
        "image_duplicates.extensions": defaults.image_duplicate_extensions,
    }
    missing = [name for name, values in required_arrays.items() if not values]
    if missing:
        raise ConfigError(
            "packaged defaults: required array(s) are empty: " + ", ".join(missing)
        )
    if defaults.decode_timeout_seconds is None:
        raise ConfigError(
            "packaged defaults: video_duplicates.decode_timeout_seconds is required"
        )
    if defaults.scan_workers is None:
        raise ConfigError("packaged defaults: performance.scan_workers is required")
    if defaults.progress_interval_seconds is None:
        raise ConfigError(
            "packaged defaults: performance.progress_interval_seconds is required"
        )
    if defaults.cache_publication_batch_size is None:
        raise ConfigError(
            "packaged defaults: performance.cache_publication_batch_size is required"
        )
    return defaults


def load_config(root: Path, explicit_path: Path | None = None) -> PymoConfig:
    defaults = _packaged_defaults()
    layout = CollectionLayout(root)
    custom_path: Path | None
    if explicit_path is not None:
        custom_path = Path(os.path.abspath(explicit_path.expanduser()))
    else:
        candidate = layout.config
        custom_path = (
            candidate if candidate.exists() or candidate.is_symlink() else None
        )
    custom = _read_file(custom_path) if custom_path is not None else _ConfigLayer()

    timeout = (
        custom.decode_timeout_seconds
        if custom.decode_timeout_seconds is not None
        else defaults.decode_timeout_seconds
    )
    if timeout is None:
        raise ConfigError(
            "packaged defaults: video_duplicates.decode_timeout_seconds is required"
        )
    scan_workers = (
        custom.scan_workers
        if custom.scan_workers is not None
        else defaults.scan_workers
    )
    if scan_workers is None:
        raise ConfigError("packaged defaults: performance.scan_workers is required")
    progress_interval = (
        custom.progress_interval_seconds
        if custom.progress_interval_seconds is not None
        else defaults.progress_interval_seconds
    )
    if progress_interval is None:
        raise ConfigError(
            "packaged defaults: performance.progress_interval_seconds is required"
        )
    cache_batch_size = (
        custom.cache_publication_batch_size
        if custom.cache_publication_batch_size is not None
        else defaults.cache_publication_batch_size
    )
    if cache_batch_size is None:
        raise ConfigError(
            "packaged defaults: performance.cache_publication_batch_size is required"
        )

    return PymoConfig(
        ignore=IgnoreConfig(
            files=_deduplicate(defaults.ignore_files, custom.ignore_files),
            directories=_deduplicate(
                defaults.ignore_directories, custom.ignore_directories
            ),
        ),
        classification=ClassificationConfig(
            image_extensions=frozenset(
                _deduplicate(defaults.image_extensions, custom.image_extensions)
            ),
            video_extensions=frozenset(
                _deduplicate(defaults.video_extensions, custom.video_extensions)
            ),
            video_application_mime_types=frozenset(
                _deduplicate(
                    defaults.video_application_mime_types,
                    custom.video_application_mime_types,
                )
            ),
            generic_mime_types=frozenset(
                _deduplicate(defaults.generic_mime_types, custom.generic_mime_types)
            ),
        ),
        rename=RenameConfig(
            noise_tokens=frozenset(
                _deduplicate(defaults.rename_noise_tokens, custom.rename_noise_tokens)
            )
        ),
        image_duplicates=ImageDuplicateConfig(
            extensions=frozenset(
                _deduplicate(
                    defaults.image_duplicate_extensions,
                    custom.image_duplicate_extensions,
                )
            )
        ),
        video_duplicates=VideoDuplicateConfig(decode_timeout_seconds=timeout),
        performance=PerformanceConfig(
            scan_workers=scan_workers,
            progress_interval_seconds=progress_interval,
            cache_publication_batch_size=cache_batch_size,
        ),
        custom_path=custom_path,
    )


def ignored_messages(
    paths: list[Path], root: Path, show_paths: bool
) -> tuple[str, ...]:
    if not paths:
        return ()
    messages = [f"Ignored by configuration: {len(paths)} path(s)."]
    if show_paths:
        messages.append("Ignored paths:")
        for path in sorted(paths, key=lambda item: str(item).casefold()):
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                relative = path.name
            messages.append(f"  {relative}")
    return tuple(messages)
