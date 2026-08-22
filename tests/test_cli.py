from __future__ import annotations

import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"


def run_pymo(*arguments: object) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(SOURCE_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "pymo", *(str(item) for item in arguments)],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_cli_reports_package_version() -> None:
    result = run_pymo("--version")

    assert result.returncode == 0
    assert result.stdout.strip() == f"pymo {version('python-media-organizer')}"
    assert result.stderr == ""


def test_cli_does_not_create_persistent_logs_by_default(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    collection.mkdir()

    result = run_pymo("organize", collection)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Dry run" in result.stdout
    assert not list(tmp_path.rglob("*.log"))


def test_cli_explicit_log_file_and_verbose_mode(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    collection.mkdir()
    log_file = tmp_path / "private" / "pymo.log"

    result = run_pymo(
        "--verbose", "--log-file", log_file, "organize", collection
    )

    assert result.returncode == 0, result.stdout + result.stderr
    contents = log_file.read_text(encoding="utf-8")
    assert "DEBUG pymo Dispatching pymo command: organize" in contents
    assert "Dry run" in contents


def test_cli_quiet_mode_suppresses_informational_output(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    collection.mkdir()

    result = run_pymo("--quiet", "organize", collection)

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_cli_forwards_global_config_to_subcommand(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    nested = collection / "incoming"
    nested.mkdir(parents=True)
    protected = nested / "notes.txt"
    protected.write_text("keep in place", encoding="utf-8")
    config = tmp_path / "settings.toml"
    config.write_text(
        'version = 1\n\n[ignore]\nfiles = ["notes.txt"]\n',
        encoding="utf-8",
    )

    result = run_pymo("--config", config, "organize", collection, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ignored by configuration: 1 path(s)." in result.stdout
    assert protected.read_text(encoding="utf-8") == "keep in place"
