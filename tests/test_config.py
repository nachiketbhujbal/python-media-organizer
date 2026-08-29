from __future__ import annotations

from pathlib import Path

import pytest

from pymo.collection import CollectionLayout
from pymo.config import ConfigError, ignored_messages, load_config


def write_config(path: Path, body: str) -> None:
    path.write_text(f"version = 1\n\n[ignore]\n{body}", encoding="utf-8")


def test_packaged_defaults_cover_common_local_system_metadata(
    tmp_path: Path,
) -> None:
    config = load_config(tmp_path)

    assert config.ignores_file(tmp_path / ".DS_Store", tmp_path)
    assert config.ignores_file(tmp_path / "THUMBS.DB", tmp_path)
    assert config.ignores_file(tmp_path / "._photo.jpg", tmp_path)
    assert config.ignores_file(tmp_path / ".pymo.sqlite3.lock", tmp_path)
    assert config.ignores_file(
        tmp_path / ".pymo.sqlite3.new.0123456789abcdef", tmp_path
    )
    assert config.ignores_directory(tmp_path / ".Spotlight-V100", tmp_path)
    assert config.ignores_directory(tmp_path / ".git" / "objects", tmp_path)
    assert not config.ignores_file(tmp_path / "photo.jpg", tmp_path)
    assert ".jpg" in config.classification.image_extensions
    assert ".mp4" in config.classification.video_extensions
    assert "application/octet-stream" in config.classification.generic_mime_types
    assert "photo" in config.rename.noise_tokens
    assert ".png" in config.image_duplicates.extensions
    assert config.video_duplicates.decode_timeout_seconds == 3600
    assert set(config.validation.container_families) == set(
        config.classification.video_extensions
    )
    assert config.validation.container_families[".mp4"] == {"3g2,3gp,m4a,mj2,mov,mp4"}
    assert config.validation.container_families[".mpg"] == {"mpeg", "mpegvideo"}
    assert config.validation.container_families[".wmv"] == {"asf", "asf_o"}
    assert config.extension_correction.image_formats["JPEG"] == (
        ".jpg",
        ".jpeg",
        ".jpe",
        ".jfif",
    )
    assert config.extension_correction.video_families["mpegts"] == (
        ".ts",
        ".mts",
        ".m2ts",
    )
    assert "3g2,3gp,m4a,mj2,mov,mp4" not in (config.extension_correction.video_families)
    assert not config.extension_correction.protected_custom_extensions
    assert config.performance.scan_workers == 4
    assert config.performance.progress_interval_seconds == 15
    assert config.performance.cache_publication_batch_size == 32


def test_collection_config_extends_defaults_and_protects_itself(
    tmp_path: Path,
) -> None:
    config_path = CollectionLayout(tmp_path).config
    write_config(
        config_path,
        'files = ["notes.tmp"]\ndirectories = ["archive"]\n',
    )

    config = load_config(tmp_path)

    assert config.ignores_file(tmp_path / ".DS_Store", tmp_path)
    assert config.ignores_file(tmp_path / "notes.tmp", tmp_path)
    assert config.ignores_file(config_path, tmp_path)
    assert config.ignores_directory(tmp_path / "archive" / "year", tmp_path)


def test_explicit_config_selects_one_custom_file_and_keeps_defaults(
    tmp_path: Path,
) -> None:
    write_config(CollectionLayout(tmp_path).config, 'files = ["local.tmp"]\n')
    explicit = tmp_path / "settings.toml"
    write_config(explicit, 'files = ["selected.tmp"]\n')

    config = load_config(tmp_path, explicit)

    assert config.ignores_file(tmp_path / ".DS_Store", tmp_path)
    assert config.ignores_file(tmp_path / "selected.tmp", tmp_path)
    assert config.ignores_file(explicit, tmp_path)
    assert not config.ignores_file(tmp_path / "local.tmp", tmp_path)


def test_collection_policy_extends_defaults_and_timeout_overrides(
    tmp_path: Path,
) -> None:
    CollectionLayout(tmp_path).config.write_text(
        "version = 1\n"
        "[classification]\n"
        'image_extensions = [".garden"]\n'
        'video_extensions = [".city"]\n'
        'video_application_mime_types = ["application/x-city"]\n'
        'generic_mime_types = ["application/x-generic"]\n'
        "[rename]\n"
        'noise_tokens = ["planter"]\n'
        "[image_duplicates]\n"
        'extensions = [".flower"]\n'
        "[video_duplicates]\n"
        "decode_timeout_seconds = 45\n"
        "[performance]\n"
        "scan_workers = 2\n"
        "progress_interval_seconds = 5\n"
        "cache_publication_batch_size = 8\n",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert {".jpg", ".garden"}.issubset(config.classification.image_extensions)
    assert {".mp4", ".city"}.issubset(config.classification.video_extensions)
    assert "application/x-city" in config.classification.video_application_mime_types
    assert "application/x-generic" in config.classification.generic_mime_types
    assert {"photo", "planter"}.issubset(config.rename.noise_tokens)
    assert {".png", ".flower"}.issubset(config.image_duplicates.extensions)
    assert config.video_duplicates.decode_timeout_seconds == 45
    assert config.performance.scan_workers == 2
    assert config.performance.progress_interval_seconds == 5
    assert config.performance.cache_publication_batch_size == 8
    assert ".city" not in config.validation.container_families


def test_collection_configuration_cannot_redefine_packaged_validation_policy(
    tmp_path: Path,
) -> None:
    CollectionLayout(tmp_path).config.write_text(
        "version = 1\n"
        "[validation.container_families]\n"
        '".mp4" = ["matroska,webm"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"unknown top-level key.*validation"):
        load_config(tmp_path)


def test_collection_configuration_cannot_redefine_extension_correction_policy(
    tmp_path: Path,
) -> None:
    CollectionLayout(tmp_path).config.write_text(
        "version = 1\n" "[extension_correction.image_formats]\n" 'JPEG = [".garden"]\n',
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError, match=r"unknown top-level key.*extension_correction"
    ):
        load_config(tmp_path)


def test_custom_classification_extensions_are_marked_correction_protected(
    tmp_path: Path,
) -> None:
    CollectionLayout(tmp_path).config.write_text(
        "version = 1\n"
        "[classification]\n"
        'image_extensions = [".garden"]\n'
        'video_extensions = [".cinema"]\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.extension_correction.protected_custom_extensions == {
        ".garden",
        ".cinema",
    }


def test_packaged_validation_policy_is_immutable(tmp_path: Path) -> None:
    config = load_config(tmp_path)

    with pytest.raises(TypeError):
        config.validation.container_families[".mp4"] = frozenset({"matroska"})  # type: ignore[index]

    with pytest.raises(TypeError):
        config.extension_correction.image_formats["JPEG"] = (".garden",)  # type: ignore[index]


@pytest.mark.parametrize(
    "document",
    [
        "version = 2\n",
        "version = true\n",
        "version = 1\nunknown = true\n",
        'version = 1\n[ignore]\nfiles = "*.tmp"\n',
        'version = 1\n[ignore]\ndirectories = ["../outside"]\n',
        'version = 1\n[ignore]\ndirectories = ["C:\\\\outside"]\n',
        'version = 1\n[classification]\nimage_extensions = ["jpg"]\n',
        'version = 1\n[classification]\ngeneric_mime_types = ["invalid"]\n',
        'version = 1\n[rename]\nnoise_tokens = ["two words"]\n',
        "version = 1\n[video_duplicates]\ndecode_timeout_seconds = 0\n",
        "version = 1\n[video_duplicates]\ndecode_timeout_seconds = true\n",
        "version = 1\n[performance]\nscan_workers = 0\n",
        "version = 1\n[performance]\nscan_workers = true\n",
        "version = 1\n[performance]\nprogress_interval_seconds = 0\n",
        "version = 1\n[performance]\nprogress_interval_seconds = true\n",
        "version = 1\n[performance]\ncache_publication_batch_size = 0\n",
        "version = 1\n[performance]\ncache_publication_batch_size = true\n",
        "version = 1\n[image_duplicates]\nunknown = []\n",
        "version = 1\n[ignore]\nfiles = [\n",
    ],
)
def test_invalid_configuration_is_rejected(tmp_path: Path, document: str) -> None:
    path = CollectionLayout(tmp_path).config
    path.write_text(document, encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_symbolic_link_configuration_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "settings.toml"
    target.write_text("version = 1\n", encoding="utf-8")
    link = tmp_path / "settings-link.toml"
    link.symlink_to(target)

    with pytest.raises(ConfigError, match="not a regular file"):
        load_config(tmp_path, link)


def test_ignored_messages_are_private_by_default_and_relative_when_requested(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / "vids" / ".DS_Store", tmp_path / "pics" / "Thumbs.db"]

    assert ignored_messages(paths, tmp_path, False) == (
        "Ignored by configuration: 2 path(s).",
    )
    assert ignored_messages(paths, tmp_path, True) == (
        "Ignored by configuration: 2 path(s).",
        "Ignored paths:",
        "  pics/Thumbs.db",
        "  vids/.DS_Store",
    )
