from __future__ import annotations

from pathlib import Path

import pytest

from pymo.config import CONFIG_FILENAME, ConfigError, load_config


def write_config(path: Path, body: str) -> None:
    path.write_text(f"version = 1\n\n[ignore]\n{body}", encoding="utf-8")


def test_packaged_defaults_cover_common_local_system_metadata(
    tmp_path: Path,
) -> None:
    config = load_config(tmp_path)

    assert config.ignores_file(tmp_path / ".DS_Store", tmp_path)
    assert config.ignores_file(tmp_path / "THUMBS.DB", tmp_path)
    assert config.ignores_file(tmp_path / "._photo.jpg", tmp_path)
    assert config.ignores_directory(tmp_path / ".Spotlight-V100", tmp_path)
    assert config.ignores_directory(tmp_path / ".git" / "objects", tmp_path)
    assert not config.ignores_file(tmp_path / "photo.jpg", tmp_path)


def test_collection_config_extends_defaults_and_protects_itself(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / CONFIG_FILENAME
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
    write_config(tmp_path / CONFIG_FILENAME, 'files = ["local.tmp"]\n')
    explicit = tmp_path / "settings.toml"
    write_config(explicit, 'files = ["selected.tmp"]\n')

    config = load_config(tmp_path, explicit)

    assert config.ignores_file(tmp_path / ".DS_Store", tmp_path)
    assert config.ignores_file(tmp_path / "selected.tmp", tmp_path)
    assert config.ignores_file(explicit, tmp_path)
    assert not config.ignores_file(tmp_path / "local.tmp", tmp_path)


@pytest.mark.parametrize(
    "document",
    [
        "version = 2\n",
        "version = 1\nunknown = true\n",
        'version = 1\n[ignore]\nfiles = "*.tmp"\n',
        'version = 1\n[ignore]\ndirectories = ["../outside"]\n',
        'version = 1\n[ignore]\ndirectories = ["C:\\\\outside"]\n',
        "version = 1\n[ignore]\nfiles = [\n",
    ],
)
def test_invalid_configuration_is_rejected(
    tmp_path: Path, document: str
) -> None:
    path = tmp_path / CONFIG_FILENAME
    path.write_text(document, encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(tmp_path)
