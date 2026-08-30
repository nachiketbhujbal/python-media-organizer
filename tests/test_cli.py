from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

from pymo import cli

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


def test_cli_help_and_argument_errors_remain_unprefixed(tmp_path: Path) -> None:
    help_result = run_pymo("--help")
    conflict_result = run_pymo(
        "--timestamps",
        "--no-timestamps",
        "organize",
        tmp_path / "collection",
    )

    assert help_result.returncode == 0
    assert "--timestamps" in help_result.stdout
    assert "--no-timestamps" in help_result.stdout
    assert "verify-migration" in help_result.stdout
    assert "correct-extensions" in help_result.stdout
    assert "migrate" in help_result.stdout
    assert help_result.stdout.startswith("usage: pymo")
    assert conflict_result.returncode == 2
    assert conflict_result.stderr.startswith("usage: pymo")


def test_dispatched_help_and_argument_errors_remain_unprefixed(
    tmp_path: Path,
) -> None:
    help_result = run_pymo("cache", "--help")
    refresh_help = run_pymo("cache", "refresh", "--help")
    error_result = run_pymo("cache", "unknown", tmp_path / "collection")

    assert help_result.returncode == 0
    assert help_result.stdout.startswith("usage: pymo cache")
    assert "inspect cache health without writing state" in help_result.stdout
    assert "deliberately populate reusable cache evidence" in help_result.stdout
    assert "recompute selected cache evidence" in help_result.stdout
    assert "Completed cache" not in help_result.stdout
    assert "Stopped cache" not in help_result.stdout
    assert help_result.stderr == ""
    assert refresh_help.returncode == 0
    assert "validation-standard" in refresh_help.stdout
    assert "validation-full" in refresh_help.stdout
    assert "Completed cache" not in refresh_help.stdout
    assert refresh_help.stderr == ""
    assert error_result.returncode == 2
    assert error_result.stdout == ""
    assert error_result.stderr.startswith("usage: pymo cache")
    assert "Stopped cache" not in error_result.stderr


def test_cli_does_not_create_persistent_logs_by_default(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    collection.mkdir()

    result = run_pymo("organize", collection)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Dry run" in result.stdout
    assert not list(tmp_path.rglob("*.log"))


def test_migrate_rejects_the_single_global_log_file(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    working = tmp_path / "working"
    baseline.mkdir()
    working.mkdir()
    log_file = tmp_path / "unexpected.log"

    result = run_pymo("--log-file", log_file, "migrate", baseline, working)

    assert result.returncode == 2
    assert "migrate uses --log-dir" in result.stderr
    assert not log_file.exists()


def test_cli_explicit_log_file_and_verbose_mode(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    collection.mkdir()
    log_file = tmp_path / "private" / "pymo.log"

    result = run_pymo("--verbose", "--log-file", log_file, "organize", collection)

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


def test_cli_reports_elapsed_runtime_with_default_and_explicit_timestamps(
    tmp_path: Path,
) -> None:
    collection = tmp_path / "collection"
    collection.mkdir()

    default = run_pymo("organize", collection)
    explicit = run_pymo("--timestamps", "organize", collection)

    for result in (default, explicit):
        assert result.returncode == 0, result.stdout + result.stderr
        lines = result.stdout.splitlines()
        assert lines
        assert all(
            re.match(
                r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} ",
                line,
            )
            for line in lines
        )
        assert "Completed organize in " in result.stdout


def test_cli_can_omit_default_console_timestamps(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    collection.mkdir()

    result = run_pymo("--no-timestamps", "organize", collection)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Completed organize in " in result.stdout
    assert not any(
        re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} ", line)
        for line in result.stdout.splitlines()
    )


def test_log_file_timestamps_every_physical_line(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    collection.mkdir()
    log_file = tmp_path / "pymo.log"

    result = run_pymo("--no-timestamps", "--log-file", log_file, "organize", collection)

    assert result.returncode == 0
    assert result.stdout.startswith("Classifying")
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert lines
    assert all(
        re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} "
            r"(?:INFO|WARNING|ERROR|DEBUG) pymo ",
            line,
        )
        for line in lines
    )


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

    result = run_pymo(
        "--config",
        config,
        "--show-ignored",
        "--no-timestamps",
        "organize",
        collection,
        "--apply",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ignored by configuration: 1 path(s)." in result.stdout
    assert "Ignored paths:\n  incoming/notes.txt" in result.stdout
    assert protected.read_text(encoding="utf-8") == "keep in place"


def test_verbose_does_not_reveal_ignored_paths_without_opt_in(
    tmp_path: Path,
) -> None:
    collection = tmp_path / "collection"
    pics = collection / "pics"
    vids = collection / "vids"
    pics.mkdir(parents=True)
    vids.mkdir()
    (pics / ".DS_Store").write_bytes(b"view state")

    result = run_pymo("--verbose", "organize", collection)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ignored by configuration: 1 path(s)." in result.stdout
    assert ".DS_Store" not in result.stdout
    assert ".DS_Store" not in result.stderr


def test_scan_json_stays_machine_readable_with_global_output_flags(
    tmp_path: Path,
) -> None:
    collection = tmp_path / "media-collection"
    collection.mkdir()

    for output_flags in (
        (),
        ("--verbose",),
        ("--quiet",),
        ("--timestamps",),
        ("--no-timestamps",),
    ):
        result = run_pymo(*output_flags, "scan", collection, "--json")

        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["schema_version"] == 1


def test_validate_json_stays_machine_readable_with_global_output_flags(
    tmp_path: Path,
) -> None:
    collection = tmp_path / "media-collection"
    collection.mkdir()

    for output_flags in (
        (),
        ("--verbose",),
        ("--quiet",),
        ("--timestamps",),
        ("--no-timestamps",),
    ):
        result = run_pymo(*output_flags, "validate", collection, "--json")

        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["schema_version"] == 2


def test_cache_status_json_stays_machine_readable_and_read_only(
    tmp_path: Path,
) -> None:
    collection = tmp_path / "media-collection"
    collection.mkdir()

    for output_flags in (
        (),
        ("--verbose",),
        ("--quiet",),
        ("--timestamps",),
        ("--no-timestamps",),
    ):
        result = run_pymo(*output_flags, "cache", "status", collection, "--json")

        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads(result.stdout)
        assert report["schema_version"] == 1
        assert report["cache"]["state"] == "missing"
        assert result.stderr == ""
        assert list(collection.iterdir()) == []


def test_cache_status_human_output_is_read_only_and_reports_runtime(
    tmp_path: Path,
) -> None:
    collection = tmp_path / "media-collection"
    collection.mkdir()

    result = run_pymo("--no-timestamps", "cache", "status", collection)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "State: missing" in result.stdout
    assert "no cache, lock, media, or action state was written" in result.stdout
    assert "Completed cache in " in result.stdout
    assert result.stderr == ""
    assert list(collection.iterdir()) == []


def test_cache_status_rejects_irrelevant_global_configuration(tmp_path: Path) -> None:
    collection = tmp_path / "media-collection"
    collection.mkdir()

    result = run_pymo(
        "--config", tmp_path / "settings.toml", "cache", "status", collection
    )

    assert result.returncode == 2
    assert "not used by cache status" in result.stderr
    assert list(collection.iterdir()) == []


def test_cache_warm_receives_relevant_global_configuration(tmp_path: Path) -> None:
    collection = tmp_path / "media-collection"
    (collection / "vids").mkdir(parents=True)
    config = tmp_path / "settings.toml"
    config.write_text("version = 1\n", encoding="utf-8")

    result = run_pymo(
        "--config",
        config,
        "--show-ignored",
        "--no-timestamps",
        "cache",
        "warm",
        "videos",
        collection,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "No selected media content required cache warming" in result.stdout
    assert list(collection.iterdir()) == [collection / "vids"]


def test_cache_refresh_receives_relevant_global_configuration(tmp_path: Path) -> None:
    collection = tmp_path / "media-collection"
    (collection / "pics").mkdir(parents=True)
    config = tmp_path / "settings.toml"
    config.write_text("version = 1\n", encoding="utf-8")

    result = run_pymo(
        "--config",
        config,
        "--show-ignored",
        "--no-timestamps",
        "cache",
        "refresh",
        "images",
        collection,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "No selected media content required cache refresh" in result.stdout
    assert list(collection.iterdir()) == [collection / "pics"]


def test_cli_returns_130_and_reports_runtime_after_keyboard_interrupt(
    monkeypatch, capsys
) -> None:
    def interrupt(_arguments) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_commands", lambda: {"scan": interrupt})

    assert cli.main(["scan"]) == 130
    captured = capsys.readouterr()
    assert "Interrupted by user" in captured.err
    assert "Interrupted scan in " in captured.out
    assert "exit 130" in captured.out
    assert re.match(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} ",
        captured.err,
    )
    assert re.match(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} ",
        captured.out,
    )


def test_cli_reports_runtime_before_propagating_unexpected_errors(
    monkeypatch, capsys
) -> None:
    def fail(_arguments) -> int:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(cli, "_commands", lambda: {"scan": fail})

    with pytest.raises(RuntimeError, match="synthetic failure"):
        cli.main(["scan"])
    assert "Stopped scan in " in capsys.readouterr().out
