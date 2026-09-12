from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from pymo import __version__, cli, migrate
from pymo.logging_config import configure_logging
from pymo.migration.outcome import OutcomeCategory, ResultKind, outcome_record
from pymo.migration.workflow import child_command

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
        timeout=60,
        check=False,
    )


def completed_child(
    command: list[str], status: int = 0
) -> subprocess.CompletedProcess[str]:
    commands = {
        "scan",
        "validate",
        "verify-migration",
        "correct-extensions",
        "organize",
        "rename",
        "find-image-duplicates",
        "find-video-duplicates",
    }
    child = next(item for item in command if item in commands)
    if child == "scan":
        category: OutcomeCategory = "scan"
        data: dict[str, object] = {
            "files": 0,
            "directories": 0,
            "bytes": 0,
            "pictures": 0,
            "videos": 0,
            "audio": 0,
            "other": 0,
            "unknown": 0,
            "ignored": 0,
            "symbolic_links": 0,
            "unreadable": 0,
            "changed": 0,
        }
    elif child == "validate":
        category = "validation"
        failed = status == 1
        data = {
            "media_files": int(failed),
            "media_bytes": 0,
            "pictures": int(failed),
            "videos": 0,
            "other_files": 0,
            "symbolic_links": 0,
            "unreadable": 0,
            "changed": 0,
            "healthy": 0,
            "warning_only": 0,
            "errors": int(failed),
            "findings": (
                [{"severity": "error", "code": "test-finding", "count": 1}]
                if failed
                else []
            ),
            "cache": {
                "enabled": False,
                "reused": 0,
                "computed": 0,
                "persisted": 0,
                "issue": None,
            },
        }
    elif child == "verify-migration":
        category = "verification"
        failed = status != 0
        data = {
            "source_files": int(failed),
            "source_bytes": 0,
            "source_unique_streams": int(failed),
            "accounted_unique_streams": 0,
            "accounted_source_files": 0,
            "unaccounted_unique_streams": int(failed),
            "unaccounted_source_files": int(failed),
            "unsupported_unique_streams": 0,
            "unsupported_source_files": 0,
            "destination_files": 0,
            "destination_bytes": 0,
            "review_files": 0,
            "review_bytes": 0,
            "verdict": "complete" if status == 0 else "unproven",
            "disposition": (
                "retain-source-and-resolve-findings"
                if failed
                else "eligible-for-human-signoff"
            ),
            "reasons": ["source-content-unaccounted"] if failed else [],
        }
    elif child in {"correct-extensions", "organize", "rename"}:
        category = "transformation"
        operations = {
            "correct-extensions": "extension-correction",
            "organize": "organization",
            "rename": "rename",
        }
        data = {
            "operation": operations[child],
            "files": 0,
            "directories_created": 0,
            "directories_removed": 0,
        }
    else:
        category = "duplicates"
        data = {
            "media_kind": "image" if child == "find-image-duplicates" else "video",
            "scanned_files": 0,
            "scanned_bytes": 0,
            "groups": 0,
            "extra_copies": 0,
            "duplicate_bytes": 0,
            "skipped": 0,
            "cache": {
                "enabled": False,
                "reused": 0,
                "computed": 0,
                "persisted": 0,
                "issue": None,
            },
        }
    result_kind: ResultKind = (
        "simulated"
        if "--simulate-without-dups" in command
        else (
            "observed"
            if "--apply" in command or category != "transformation"
            else "preview"
        )
    )
    if category == "duplicates" and "--apply" not in command:
        result_kind = "preview"
    if category == "verification" and result_kind == "simulated" and status == 0:
        data["disposition"] = "eligible-for-human-quarantine-review"
    path = Path(command[command.index("--migration-outcome") + 1])
    path.write_text(
        json.dumps(outcome_record(child, category, result_kind, status, data)) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return subprocess.CompletedProcess(command, status)


def collections(tmp_path: Path) -> tuple[Path, Path]:
    baseline = tmp_path / "baseline"
    working = tmp_path / "working"
    baseline.mkdir()
    working.mkdir()
    return baseline, working


def state_file(log_dir: Path) -> Path:
    return log_dir / "pymo-migration-state.json"


def test_zero_write_plan_requires_explicit_private_state(tmp_path: Path) -> None:
    baseline, working = collections(tmp_path)

    result = run_pymo("--no-timestamps", "migrate", baseline, working)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Guided single-collection migration plan" in result.stdout
    assert "Zero-write plan only" in result.stdout
    assert "extension-apply" in result.stdout
    assert "external-quarantine" in result.stdout
    assert list(baseline.iterdir()) == []
    assert list(working.iterdir()) == []
    assert sorted(path.name for path in tmp_path.iterdir()) == ["baseline", "working"]

    refused = run_pymo("--no-timestamps", "migrate", baseline, working, "--run")
    assert refused.returncode == 2
    assert "explicit --log-dir is required" in refused.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == ["baseline", "working"]


def test_collection_and_log_roots_use_filesystem_identity(tmp_path: Path) -> None:
    stored = tmp_path / "collection"
    alias = tmp_path / "COLLECTION"
    stored.mkdir()

    if alias.exists():
        same_root = run_pymo("--no-timestamps", "migrate", stored, alias)
        assert same_root.returncode == 2
        assert "distinct, non-nested" in same_root.stderr

        baseline = tmp_path / "baseline"
        baseline.mkdir()
        nested_log = run_pymo(
            "--no-timestamps",
            "migrate",
            baseline,
            stored,
            "--log-dir",
            alias / "private-logs",
            "--start",
        )
        assert nested_log.returncode == 2
        assert (
            "private log directory must be distinct and non-nested" in nested_log.stderr
        )
        assert not (stored / "private-logs").exists()
    else:
        alias.mkdir()
        distinct_roots = run_pymo("--no-timestamps", "migrate", stored, alias)
        assert distinct_roots.returncode == 0
        assert "Guided single-collection migration plan" in distinct_roots.stdout


def test_coordinator_setup_errors_use_status_two(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    working = tmp_path / "working"
    working.mkdir()

    result = run_pymo("--no-timestamps", "migrate", missing, working)

    assert result.returncode == 2
    assert "baseline is not a readable directory" in result.stderr


@pytest.mark.parametrize("looping_root_name", ("baseline", "working"))
def test_migrate_rejects_self_referential_collection_root_privately(
    tmp_path: Path,
    looping_root_name: str,
) -> None:
    baseline = tmp_path / "baseline"
    working = tmp_path / "working"
    looping_root = baseline if looping_root_name == "baseline" else working
    readable_root = working if looping_root_name == "baseline" else baseline
    readable_root.mkdir()
    looping_root.symlink_to(looping_root.name, target_is_directory=True)
    before_entries = sorted(entry.name for entry in tmp_path.iterdir())

    result = run_pymo("--no-timestamps", "migrate", baseline, working)

    assert result.returncode == 2
    output = result.stdout + result.stderr
    assert "Migration coordinator cannot safely continue" in output
    assert "Traceback" not in output
    assert str(tmp_path) not in output
    assert sorted(entry.name for entry in tmp_path.iterdir()) == before_entries
    assert looping_root.is_symlink()
    assert os.readlink(looping_root) == looping_root.name
    assert list(readable_root.iterdir()) == []


@pytest.mark.parametrize(
    "path_option", ("--log-dir", "--config", "--ffmpeg", "--ffprobe")
)
def test_migrate_rejects_self_referential_optional_path_before_writes(
    tmp_path: Path,
    path_option: str,
) -> None:
    baseline, working = collections(tmp_path)
    looping_path = tmp_path / "looping-path"
    looping_path.symlink_to(looping_path.name)
    log_dir = looping_path if path_option == "--log-dir" else tmp_path / "logs"
    arguments: list[object] = [
        "--no-timestamps",
        "migrate",
        baseline,
        working,
        "--log-dir",
        log_dir,
        "--start",
    ]
    if path_option != "--log-dir":
        arguments.extend((path_option, looping_path))
    before_entries = sorted(entry.name for entry in tmp_path.iterdir())

    result = run_pymo(*arguments)

    assert result.returncode == 2
    output = result.stdout + result.stderr
    assert "Migration coordinator cannot safely continue" in output
    assert "Traceback" not in output
    assert str(tmp_path) not in output
    assert sorted(entry.name for entry in tmp_path.iterdir()) == before_entries
    assert not (tmp_path / "logs").exists()
    assert list(baseline.iterdir()) == []
    assert list(working.iterdir()) == []


@pytest.mark.parametrize(
    "failing_path_name",
    ("baseline", "working", "log-dir", "config", "ffmpeg", "ffprobe"),
)
@pytest.mark.parametrize("error_type", (OSError, RuntimeError))
def test_migrate_contains_argument_path_resolution_errors_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_path_name: str,
    error_type: type[Exception],
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    optional_path = tmp_path / f"{failing_path_name}-argument"
    paths = {
        "baseline": baseline,
        "working": working,
        "log-dir": log_dir,
        "config": optional_path,
        "ffmpeg": optional_path,
        "ffprobe": optional_path,
    }
    failing_path = paths[failing_path_name]
    arguments = [
        str(baseline),
        str(working),
        "--log-dir",
        str(log_dir),
        "--start",
    ]
    if failing_path_name in {"config", "ffmpeg", "ffprobe"}:
        arguments.extend((f"--{failing_path_name}", str(optional_path)))
    before_entries = sorted(entry.name for entry in tmp_path.iterdir())
    real_resolve = Path.resolve

    def fail_selected_path(path: Path, *args, **kwargs) -> Path:
        if path == failing_path:
            raise error_type(f"sensitive path: {failing_path}")
        return real_resolve(path, *args, **kwargs)

    messages: list[tuple[str, object]] = []
    monkeypatch.setattr(Path, "resolve", fail_selected_path)
    monkeypatch.setattr(
        migrate,
        "print",
        lambda message, *, file=None: messages.append((message, file)),
    )

    assert migrate.main(arguments) == 2
    assert messages == [
        (
            "Migration coordinator cannot safely continue: "
            "a command-line path cannot be resolved safely.",
            sys.stderr,
        )
    ]
    assert str(tmp_path) not in messages[0][0]
    assert sorted(entry.name for entry in tmp_path.iterdir()) == before_entries
    assert not log_dir.exists()
    assert list(baseline.iterdir()) == []
    assert list(working.iterdir()) == []


def test_start_records_private_options_and_refuses_mismatched_reuse(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    config = tmp_path / "settings.toml"
    config.write_text("version = 1\n", encoding="utf-8")

    started = run_pymo(
        "--verbose",
        "--config",
        config,
        "--show-ignored",
        "migrate",
        baseline,
        working,
        "--log-dir",
        log_dir,
        "--start",
        "--no-cache",
        "--workers",
        "2",
        "--decode-timeout",
        "15",
    )

    assert started.returncode == 0, started.stdout + started.stderr
    assert "Run routine stages with --run" in started.stdout
    assert "Migration synopsis" in started.stdout
    assert "Workflow: not started" in started.stdout
    payload = json.loads(state_file(log_dir).read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["tool_version"] == __version__
    assert payload["baseline"] == str(baseline.resolve())
    assert payload["working"] == str(working.resolve())
    assert payload["options"] == {
        "config": str(config.resolve()),
        "decode_timeout": 15,
        "ffmpeg": None,
        "ffprobe": None,
        "no_cache": True,
        "quiet": False,
        "show_ignored": True,
        "show_files": False,
        "timestamps": True,
        "verbose": True,
        "workers": 2,
    }
    assert stat_mode(state_file(log_dir)) == 0o600
    assert stat_mode(log_dir / "pymo-migration-state.lock") == 0o600
    assert list(baseline.iterdir()) == []
    assert list(working.iterdir()) == []

    status = run_pymo(
        "migrate", baseline, working, "--log-dir", log_dir, "--workers", "3"
    )
    assert status.returncode == 2
    assert "workers differs from the recorded" in status.stderr
    assert (
        json.loads(state_file(log_dir).read_text(encoding="utf-8"))["next_stage"] == 0
    )


def test_resume_status_recovers_recorded_collections_and_options(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 4)
    before = state_file(log_dir).read_bytes()

    result = run_pymo("migrate", "--resume", log_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Migration progress: 4/24 stage(s) complete" in result.stdout
    assert "Next checkpoint: initial-verification" in result.stdout
    assert "Migration synopsis" in result.stdout
    assert str(baseline) not in result.stdout + result.stderr
    assert str(working) not in result.stdout + result.stderr
    assert state_file(log_dir).read_bytes() == before


def test_resume_run_dispatches_saved_context_and_stops_at_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 4)
    state = migrate._load_state(state_file(log_dir))
    saved_probe = tmp_path / "saved-ffprobe"
    saved_options = migrate.CoordinatorOptions(
        False,
        False,
        True,
        None,
        False,
        True,
        None,
        str(saved_probe),
        17,
        None,
        False,
    )
    migrate._write_state(
        state_file(log_dir),
        migrate.MigrationState(
            state.tool_version,
            state.baseline,
            state.working,
            saved_options,
            state.next_stage,
            state.attempts,
            state.created_at,
            state.updated_at,
        ),
    )
    observed: list[list[str]] = []

    def completed(
        command: list[str], *, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        observed.append(command)
        return completed_child(command)

    monkeypatch.setattr(migrate.subprocess, "run", completed)

    assert migrate.main(["--resume", str(log_dir), "--run"]) == 0

    state = migrate._load_state(state_file(log_dir))
    assert state.next_stage == 6
    assert len(observed) == 2
    assert str(baseline.resolve()) in observed[0]
    assert all(str(working.resolve()) in command for command in observed)
    assert all("--apply" not in command for command in observed)
    assert "--show-files" in observed[0]
    assert str(saved_probe) in observed[0]
    assert "17" in observed[0]
    assert str(saved_probe) in observed[1]


def test_resume_supports_the_existing_reviewed_apply_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 6)
    observed: list[list[str]] = []

    def completed(
        command: list[str], *, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        observed.append(command)
        return completed_child(command)

    monkeypatch.setattr(migrate.subprocess, "run", completed)

    assert migrate.main(["--resume", str(log_dir), "--run-next", "--apply"]) == 0
    assert len(observed) == 1
    assert "correct-extensions" in observed[0]
    assert observed[0][-1] == "--apply"
    assert migrate._load_state(state_file(log_dir)).next_stage == 7


@pytest.mark.parametrize(
    "arguments",
    (
        ("--resume", "{log}", "{baseline}"),
        ("--resume", "{log}", "--log-dir", "{other}"),
        ("--resume", "{log}", "--start"),
        ("{baseline}",),
        (),
    ),
)
def test_resume_and_collection_locator_forms_are_unambiguous(
    tmp_path: Path,
    arguments: tuple[str, ...],
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    before = state_file(log_dir).read_bytes()
    values = {
        "{log}": str(log_dir),
        "{baseline}": str(baseline),
        "{other}": str(tmp_path / "other"),
    }

    result = migrate.main([values.get(argument, argument) for argument in arguments])

    assert result == 2
    assert state_file(log_dir).read_bytes() == before


def test_resume_accepts_only_matching_recorded_option_repetitions(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    before = state_file(log_dir).read_bytes()

    assert migrate.main(["--resume", str(log_dir), "--timestamps"]) == 0
    assert migrate.main(["--resume", str(log_dir), "--workers", "2"]) == 2
    assert state_file(log_dir).read_bytes() == before


def test_resume_requires_existing_state_without_creating_a_lock(tmp_path: Path) -> None:
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()

    assert migrate.main(["--resume", str(log_dir)]) == 2
    assert list(log_dir.iterdir()) == []


def test_resume_supports_validation_acknowledgement(tmp_path: Path) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 2)
    state = migrate._load_state(state_file(log_dir))
    failed = _failed_validation_attempt(
        log_dir, baseline, working, state, "baseline-validation"
    )
    migrate._write_state(
        state_file(log_dir), migrate._updated_state(state, failed, advance=False)
    )

    assert migrate.main(["--resume", str(log_dir), "--accept-status"]) == 0
    resumed = migrate._load_state(state_file(log_dir))
    assert resumed.next_stage == 3
    assert resumed.attempts[-1].action == "acknowledge-status"


def test_resume_supports_external_quarantine_confirmation(tmp_path: Path) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 21)

    assert migrate.main(["--resume", str(log_dir), "--confirm-quarantine"]) == 0
    resumed = migrate._load_state(state_file(log_dir))
    assert resumed.next_stage == 22
    assert resumed.attempts[-1].action == "confirm-quarantine"


def test_resume_interactive_decline_preserves_the_pending_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 6)
    before = state_file(log_dir).read_bytes()
    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput("n\n"))

    assert migrate.main(["--resume", str(log_dir), "--interactive"]) == 0
    assert state_file(log_dir).read_bytes() == before


def test_resume_rejects_linked_locator_and_changed_recorded_root_privately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    before = state_file(log_dir).read_bytes()
    linked_log = tmp_path / "linked-private-logs"
    linked_log.symlink_to(log_dir, target_is_directory=True)
    messages: list[tuple[str, object]] = []
    observed: list[list[str]] = []
    monkeypatch.setattr(
        migrate,
        "print",
        lambda message, *, file=None: messages.append((message, file)),
    )
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: observed.append(command),
    )

    assert migrate.main(["--resume", str(linked_log), "--run-next"]) == 2
    assert "symbolic link" in messages[-1][0]
    assert str(tmp_path) not in messages[-1][0]

    displaced = tmp_path / "displaced-baseline"
    baseline.rename(displaced)
    baseline.symlink_to(displaced, target_is_directory=True)
    assert migrate.main(["--resume", str(log_dir), "--run-next"]) == 2
    assert "no longer resolve to their saved paths" in messages[-1][0]
    assert str(tmp_path) not in messages[-1][0]
    assert observed == []
    assert state_file(log_dir).read_bytes() == before


def test_child_options_are_forwarded_only_to_applicable_stages(tmp_path: Path) -> None:
    baseline, working = collections(tmp_path)
    options = migrate.CoordinatorOptions(
        verbose=True,
        quiet=False,
        timestamps=False,
        config=str(tmp_path / "settings.toml"),
        show_ignored=True,
        show_files=True,
        ffmpeg=str(tmp_path / "ffmpeg"),
        ffprobe=str(tmp_path / "ffprobe"),
        decode_timeout=30,
        workers=2,
        no_cache=True,
    )
    commands = {
        stage.identifier: child_command(
            baseline, working, options, stage, tmp_path / f"{stage.identifier}.log"
        )
        for stage in migrate._stages()
        if stage.command is not None
    }

    assert "--workers" in commands["baseline-scan"]
    assert "--show-files" not in commands["baseline-scan"]
    assert "--show-files" in commands["baseline-validation"]
    assert "--no-cache" in commands["baseline-validation"]
    assert "--show-files" in commands["initial-verification"]
    assert "--ffmpeg" in commands["initial-verification"]
    assert "--ffprobe" in commands["extension-preview"]
    assert "--ffmpeg" not in commands["extension-preview"]
    assert "--no-cache" in commands["image-duplicates-preview"]
    assert "--decode-timeout" in commands["video-duplicates-preview"]
    assert "--simulate-without-dups" in commands["without-dups-simulation"]
    assert commands["extension-apply"][-1] == "--apply"
    assert "--apply" not in commands["extension-preview"]


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def _state_at(log_dir: Path, baseline: Path, working: Path, next_stage: int) -> None:
    now = "2026-08-29T12:00:00-04:00"
    options = migrate.CoordinatorOptions(
        False, False, True, None, False, False, None, None, None, None, False
    )
    attempts: list[migrate.Attempt] = []
    for index, stage in enumerate(migrate._stages()[:next_stage], start=1):
        if stage.mode == "checkpoint":
            attempts.append(
                migrate.Attempt(
                    stage.identifier,
                    "confirm-quarantine",
                    0,
                    now,
                    None,
                    False,
                )
            )
            continue
        log_name = f"{index}.log"
        outcome_name = f"{index}.outcome.json"
        command = child_command(
            baseline.resolve(),
            working.resolve(),
            options,
            stage,
            log_dir / log_name,
            log_dir / outcome_name,
        )
        completed_child(command)
        attempts.append(
            migrate.Attempt(
                stage.identifier,
                "run",
                0,
                now,
                log_name,
                stage.mode == "apply",
                0,
                outcome_name,
            )
        )
    state = migrate.MigrationState(
        __version__,
        baseline.resolve(),
        working.resolve(),
        options,
        next_stage,
        tuple(attempts),
        now,
        now,
    )
    migrate._write_state(state_file(log_dir), state)


def _create_private_state_lock(log_dir: Path) -> Path:
    lock = log_dir / "pymo-migration-state.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)
    return lock


def _tree_contents(root: Path) -> dict[str, tuple[str, bytes | None, int]]:
    return {
        str(path.relative_to(root)): (
            "directory" if path.is_dir() else "file",
            None if path.is_dir() else path.read_bytes(),
            stat_mode(path),
        )
        for path in sorted(root.rglob("*"))
    }


def _failed_validation_attempt(
    log_dir: Path,
    baseline: Path,
    working: Path,
    state: migrate.MigrationState,
    stage_name: str,
) -> migrate.Attempt:
    stage = next(item for item in migrate._stages() if item.identifier == stage_name)
    log_name = "failed.log"
    outcome_name = "failed.outcome.json"
    command = child_command(
        baseline.resolve(),
        working.resolve(),
        state.options,
        stage,
        log_dir / log_name,
        log_dir / outcome_name,
    )
    completed_child(command, 1)
    return migrate.Attempt(
        stage_name,
        "run",
        1,
        "2026-08-29T12:00:01-04:00",
        log_name,
        False,
        0,
        outcome_name,
    )


def test_stable_report_is_deterministic_path_private_and_read_only(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, len(migrate._stages()))
    _create_private_state_lock(log_dir)
    before = {
        "baseline": _tree_contents(baseline),
        "working": _tree_contents(working),
        "logs": _tree_contents(log_dir),
    }
    common = ["migrate", baseline, working, "--log-dir", log_dir, "--json"]

    first = run_pymo(*common)
    second = run_pymo("migrate", "--resume", log_dir, "--json")

    assert first.returncode == second.returncode == 0
    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    report = json.loads(first.stdout)
    assert report["schema_version"] == 1
    assert report["report_type"] == "pymo-migration-report"
    assert report["tool_version"] == __version__
    assert report["workflow"] == {
        "completed_stages": len(migrate._stages()),
        "external_quarantine_confirmed": True,
        "human_signoff_recorded": False,
        "latest_exit_status": None,
        "next_stage": None,
        "status": "complete",
        "status_one_validations_acknowledged": 0,
        "stopped_stage": None,
        "total_stages": len(migrate._stages()),
        "validation_reviews_recorded": 0,
    }
    assert report["observed_child_work"] == {
        "attempts": len(migrate._stages()) - 1,
        "duration_milliseconds": 0,
    }
    assert report["inventory"]["baseline"]["files"] == 0
    assert report["inventory"]["baseline"]["result_kind"] == "observed"
    assert report["health"]["latest_working"]["errors"] == 0
    assert report["health"]["latest_working"]["result_kind"] == "observed"
    assert all(
        item["result_kind"] == "observed" for item in report["applied_transformations"]
    )
    assert [item["result_kind"] for item in report["exact_duplicates"]["analyses"]] == [
        "observed",
        "observed",
    ]
    assert report["exact_duplicates"]["review_storage"]["state"] == (
        "external-retention-confirmed-unverified"
    )
    assert report["preservation"]["result_kind"] == "observed"
    assert report["preservation"]["verdict"] == "complete"
    assert report["scope"] == {
        "action_history_writes": False,
        "basis": "validated-private-stage-outcomes",
        "collection_writes": False,
        "deletion_authority": False,
        "fresh_evidence": False,
        "whole_device_recovery": False,
    }
    assert str(tmp_path) not in first.stdout
    assert ".log" not in first.stdout
    assert ".outcome.json" not in first.stdout
    assert "2026-" not in first.stdout
    assert before == {
        "baseline": _tree_contents(baseline),
        "working": _tree_contents(working),
        "logs": _tree_contents(log_dir),
    }


def test_stable_report_distinguishes_stopped_and_simulated_evidence(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 22)
    _create_private_state_lock(log_dir)
    state = migrate._load_state(state_file(log_dir))
    failed = _failed_validation_attempt(
        log_dir, baseline, working, state, "final-working-validation"
    )
    migrate._write_state(
        state_file(log_dir), migrate._updated_state(state, failed, advance=False)
    )

    result = run_pymo("migrate", "--resume", log_dir, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["workflow"]["status"] == "stopped"
    assert report["workflow"]["stopped_stage"] == "final-working-validation"
    assert report["workflow"]["latest_exit_status"] == 1
    assert report["health"]["latest_working"]["status"] == 1
    assert report["preservation"]["result_kind"] == "simulated"
    assert report["preservation"]["disposition"] == (
        "eligible-for-human-quarantine-review"
    )


def test_stable_report_distinguishes_completed_signoff(tmp_path: Path) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, len(migrate._stages()))
    _create_private_state_lock(log_dir)
    state = migrate._load_state(state_file(log_dir))
    migrate._record_signoff(state_file(log_dir), state)

    result = run_pymo("migrate", "--resume", log_dir, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["workflow"]["status"] == "complete"
    assert report["workflow"]["human_signoff_recorded"] is True
    assert report["preservation"]["result_kind"] == "observed"


@pytest.mark.parametrize(
    "action",
    (
        "--start",
        "--run-next",
        "--run",
        "--interactive",
        "--accept-status",
        "--confirm-quarantine",
    ),
)
def test_stable_report_rejects_workflow_actions_before_any_write(
    tmp_path: Path, action: str
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    before = sorted(path.name for path in tmp_path.iterdir())

    result = run_pymo(
        "migrate", baseline, working, "--log-dir", log_dir, "--json", action
    )

    assert result.returncode == 2
    assert "--json cannot be combined with a workflow action" in result.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_stable_report_requires_the_existing_private_lock_without_creating_it(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    before = _tree_contents(log_dir)

    result = run_pymo("migrate", "--resume", log_dir, "--json")

    assert result.returncode == 2
    assert "migration state lock is unsafe" in result.stderr
    assert _tree_contents(log_dir) == before
    assert not (log_dir / "pymo-migration-state.lock").exists()


def test_stable_report_rejects_an_unsafe_outcome_without_output_or_write(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 1)
    _create_private_state_lock(log_dir)
    state = migrate._load_state(state_file(log_dir))
    outcome = log_dir / str(state.attempts[-1].outcome_file)
    outcome.chmod(0o644)
    before = _tree_contents(log_dir)

    result = run_pymo("migrate", "--resume", log_dir, "--json")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "cannot trust a private stage outcome" in result.stderr
    assert str(tmp_path) not in result.stderr
    assert _tree_contents(log_dir) == before


def test_stable_report_rejects_a_path_bearing_finding_code(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 2)
    _create_private_state_lock(log_dir)
    state = migrate._load_state(state_file(log_dir))
    failed = _failed_validation_attempt(
        log_dir, baseline, working, state, "baseline-validation"
    )
    migrate._write_state(
        state_file(log_dir), migrate._updated_state(state, failed, advance=False)
    )
    outcome = log_dir / str(failed.outcome_file)
    payload = json.loads(outcome.read_text(encoding="utf-8"))
    payload["data"]["findings"][0]["code"] = str(tmp_path)
    outcome.write_text(json.dumps(payload), encoding="utf-8")
    outcome.chmod(0o600)
    before = _tree_contents(log_dir)

    result = run_pymo("migrate", "--resume", log_dir, "--json")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "unsafe finding code" in result.stderr
    assert str(tmp_path) not in result.stderr
    assert _tree_contents(log_dir) == before


def test_stable_report_revalidates_state_and_collections_before_emitting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    _create_private_state_lock(log_dir)
    real_build_report = migrate.build_report
    displaced = tmp_path / "displaced-working"
    calls = 0

    def replace_collection(path: Path, state: migrate.MigrationState):
        nonlocal calls
        report = real_build_report(path, state)
        calls += 1
        if calls == 1:
            working.rename(displaced)
            working.mkdir()
        return report

    monkeypatch.setattr(migrate, "build_report", replace_collection)
    messages: list[tuple[str, object]] = []
    monkeypatch.setattr(
        migrate,
        "print",
        lambda message, *, file=None: messages.append((message, file)),
    )

    assert migrate.main(["--resume", str(log_dir), "--json"]) == 2
    assert len(messages) == 1
    assert "collection identity changed" in messages[0][0]
    assert messages[0][1] is sys.stderr
    assert str(tmp_path) not in messages[0][0]


def test_stable_report_rejects_lifecycle_or_outcome_change_before_emitting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    _create_private_state_lock(log_dir)
    real_load_state = migrate._load_state
    load_calls = 0

    def changed_lifecycle(path: Path) -> migrate.MigrationState:
        nonlocal load_calls
        load_calls += 1
        state = real_load_state(path)
        if load_calls == 2:
            return migrate.MigrationState(
                state.tool_version,
                state.baseline,
                state.working,
                state.options,
                state.next_stage,
                state.attempts,
                state.created_at,
                "2026-08-29T12:00:01-04:00",
            )
        return state

    messages: list[tuple[str, object]] = []
    monkeypatch.setattr(migrate, "_load_state", changed_lifecycle)
    monkeypatch.setattr(
        migrate,
        "print",
        lambda message, *, file=None: messages.append((message, file)),
    )

    assert migrate.main(["--resume", str(log_dir), "--json"]) == 2
    assert len(messages) == 1
    assert "restart lifecycle changed" in messages[0][0]

    monkeypatch.setattr(migrate, "_load_state", real_load_state)
    real_build_report = migrate.build_report
    report_calls = 0

    def changed_outcome(path: Path, state: migrate.MigrationState):
        nonlocal report_calls
        report_calls += 1
        report = real_build_report(path, state)
        if report_calls == 2:
            report = json.loads(json.dumps(report))
            report["scope"]["fresh_evidence"] = True
        return report

    messages.clear()
    monkeypatch.setattr(migrate, "build_report", changed_outcome)

    assert migrate.main(["--resume", str(log_dir), "--json"]) == 2
    assert len(messages) == 1
    assert "outcome history changed" in messages[0][0]


class TerminalInput(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_interactive_requires_terminal_input_without_state_write(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 6)
    before = state_file(log_dir).read_bytes()
    before_entries = sorted(path.name for path in log_dir.iterdir())

    result = run_pymo(
        "migrate", baseline, working, "--log-dir", log_dir, "--interactive"
    )

    assert result.returncode == 2
    assert "--interactive requires terminal input" in result.stderr
    assert state_file(log_dir).read_bytes() == before
    assert sorted(path.name for path in log_dir.iterdir()) == before_entries


@pytest.mark.parametrize(("response", "status"), [("\n", 0), ("maybe\n", 2), ("", 2)])
def test_interactive_apply_decline_and_ambiguous_input_are_zero_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: str,
    status: int,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 6)
    before = state_file(log_dir).read_bytes()
    observed: list[list[str]] = []
    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput(response))
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: observed.append(command),
    )

    result = migrate.main(
        [str(baseline), str(working), "--log-dir", str(log_dir), "--interactive"]
    )

    assert result == status
    assert observed == []
    assert state_file(log_dir).read_bytes() == before
    assert len(list(log_dir.glob("*.log"))) == 0


def test_interactive_yes_authorizes_only_the_current_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 6)
    observed: list[list[str]] = []

    def completed(
        command: list[str], *, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        observed.append(command)
        return completed_child(command)

    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput("yes\nno\n"))
    monkeypatch.setattr(migrate.subprocess, "run", completed)

    assert (
        migrate.main(
            [
                str(baseline),
                str(working),
                "--log-dir",
                str(log_dir),
                "--interactive",
            ]
        )
        == 0
    )

    state = migrate._load_state(state_file(log_dir))
    assert state.next_stage == 9
    assert len(observed) == 3
    assert "--apply" in observed[0]
    assert all("--apply" not in command for command in observed[1:])
    assert state.attempts[6].stage == "extension-apply"
    assert state.attempts[6].apply is True
    assert all(attempt.stage != "organize-apply" for attempt in state.attempts)


def test_interactive_records_successful_validation_review_for_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 2)
    observed: list[list[str]] = []

    def completed(
        command: list[str], *, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        observed.append(command)
        return completed_child(command)

    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput("y\nn\n"))
    monkeypatch.setattr(migrate.subprocess, "run", completed)

    assert (
        migrate.main(
            [str(baseline), str(working), "--log-dir", str(log_dir), "--interactive"]
        )
        == 0
    )

    state = migrate._load_state(state_file(log_dir))
    assert state.next_stage == 4
    assert len(observed) == 2
    assert [attempt.action for attempt in state.attempts[-3:]] == [
        "run",
        "acknowledge-review",
        "run",
    ]
    assert state.attempts[-2].stage == "baseline-validation"


def test_interactive_accepts_pending_status_one_without_rerunning_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 2)
    current = migrate._load_state(state_file(log_dir))
    failed = _failed_validation_attempt(
        log_dir, baseline, working, current, "baseline-validation"
    )
    migrate._write_state(
        state_file(log_dir), migrate._updated_state(current, failed, advance=False)
    )
    observed: list[list[str]] = []

    def completed(
        command: list[str], *, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        observed.append(command)
        return completed_child(command)

    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput("yes\nno\n"))
    monkeypatch.setattr(migrate.subprocess, "run", completed)

    assert (
        migrate.main(
            [str(baseline), str(working), "--log-dir", str(log_dir), "--interactive"]
        )
        == 0
    )

    state = migrate._load_state(state_file(log_dir))
    assert len(observed) == 1
    assert "working-validation" in " ".join(observed[0])
    assert state.attempts[-2].action == "acknowledge-status"
    assert state.attempts[-2].stage == "baseline-validation"


@pytest.mark.parametrize("answer", ("n\n", "\n"))
def test_interactive_declines_pending_status_one_with_original_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: str
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 2)
    current = migrate._load_state(state_file(log_dir))
    failed = _failed_validation_attempt(
        log_dir, baseline, working, current, "baseline-validation"
    )
    migrate._write_state(
        state_file(log_dir), migrate._updated_state(current, failed, advance=False)
    )
    expected = state_file(log_dir).read_bytes()

    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput(answer))

    assert (
        migrate.main(
            [str(baseline), str(working), "--log-dir", str(log_dir), "--interactive"]
        )
        == 1
    )
    assert state_file(log_dir).read_bytes() == expected


def test_interactive_quarantine_confirmation_remains_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 21)
    (working / "dups").mkdir()
    before = state_file(log_dir).read_bytes()
    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput("yes\n"))

    assert (
        migrate.main(
            [str(baseline), str(working), "--log-dir", str(log_dir), "--interactive"]
        )
        == 1
    )
    assert state_file(log_dir).read_bytes() == before


def test_interactive_records_final_signoff_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, len(migrate._stages()))
    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput("yes\n"))

    arguments = [
        str(baseline),
        str(working),
        "--log-dir",
        str(log_dir),
        "--interactive",
    ]
    assert migrate.main(arguments) == 0
    signed = migrate._load_state(state_file(log_dir))
    assert signed.attempts[-1].action == "signoff"
    assert signed.next_stage == len(migrate._stages())

    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput(""))
    assert migrate.main(arguments) == 0
    resumed = migrate._load_state(state_file(log_dir))
    assert resumed == signed


def test_interactive_interrupt_retains_status_130_and_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 6)
    before = state_file(log_dir).read_bytes()
    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput("yes\n"))

    def interrupt(question: str) -> bool:
        del question
        raise KeyboardInterrupt

    monkeypatch.setattr(migrate, "_prompt_yes_no", interrupt)

    assert (
        cli.main(
            [
                "migrate",
                str(baseline),
                str(working),
                "--log-dir",
                str(log_dir),
                "--interactive",
            ]
        )
        == 130
    )
    assert state_file(log_dir).read_bytes() == before


def test_interactive_revalidates_root_identity_after_an_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 6)
    displaced = tmp_path / "displaced-working"
    observed: list[list[str]] = []

    def replace_root(
        command: list[str], *, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        observed.append(command)
        working.rename(displaced)
        working.mkdir()
        return completed_child(command)

    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput("yes\n"))
    monkeypatch.setattr(migrate.subprocess, "run", replace_root)

    assert (
        migrate.main(
            [str(baseline), str(working), "--log-dir", str(log_dir), "--interactive"]
        )
        == 2
    )
    assert len(observed) == 1
    assert migrate._load_state(state_file(log_dir)).next_stage == 7


def test_interactive_reloads_state_after_the_operator_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 6)
    observed: list[list[str]] = []

    def substitute_state(question: str) -> bool:
        del question
        state = migrate._load_state(state_file(log_dir))
        injected = migrate.Attempt(
            "extension-apply",
            "run",
            7,
            "2026-08-29T12:00:01-04:00",
            "injected.log",
            True,
        )
        migrate._write_state(
            state_file(log_dir),
            migrate._updated_state(state, injected, advance=False),
        )
        return True

    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput("yes\n"))
    monkeypatch.setattr(migrate, "_prompt_yes_no", substitute_state)
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: observed.append(command),
    )

    assert (
        migrate.main(
            [str(baseline), str(working), "--log-dir", str(log_dir), "--interactive"]
        )
        == 2
    )
    assert observed == []
    state = migrate._load_state(state_file(log_dir))
    assert state.next_stage == 6
    assert state.attempts[-1].exit_status == 7


def test_interactive_revalidates_root_identity_after_the_operator_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 6)
    displaced = tmp_path / "displaced-working"
    observed: list[list[str]] = []

    def replace_root(question: str) -> bool:
        del question
        working.rename(displaced)
        working.mkdir()
        return True

    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput("yes\n"))
    monkeypatch.setattr(migrate, "_prompt_yes_no", replace_root)
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: observed.append(command),
    )

    assert (
        migrate.main(
            [str(baseline), str(working), "--log-dir", str(log_dir), "--interactive"]
        )
        == 2
    )
    assert observed == []
    assert migrate._load_state(state_file(log_dir)).next_stage == 6


def test_interactive_prompt_remains_visible_in_quiet_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 6)
    monkeypatch.setattr(migrate.sys, "stdin", TerminalInput("no\n"))
    configure_logging(quiet=True, timestamps=False)
    try:
        assert (
            migrate.main(
                [
                    str(baseline),
                    str(working),
                    "--log-dir",
                    str(log_dir),
                    "--interactive",
                ]
            )
            == 0
        )
        assert "Apply the reviewed mutation" in capsys.readouterr().err
    finally:
        configure_logging(timestamps=False)


def test_interactive_selector_is_exclusive_and_never_accepts_apply() -> None:
    with pytest.raises(SystemExit) as conflict:
        migrate.parse_args(["baseline", "working", "--run", "--interactive"])
    assert conflict.value.code == 2

    assert migrate.main(["baseline", "working", "--interactive", "--apply"]) == 2


def test_apply_checkpoint_requires_second_explicit_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 6)
    observed: list[list[str]] = []

    def completed(
        command: list[str], *, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        observed.append(command)
        return completed_child(command)

    monkeypatch.setattr(migrate.subprocess, "run", completed)

    assert (
        migrate.main(
            [str(baseline), str(working), "--log-dir", str(log_dir), "--run-next"]
        )
        == 2
    )
    assert observed == []
    assert migrate._load_state(state_file(log_dir)).next_stage == 6

    assert (
        migrate.main(
            [
                str(baseline),
                str(working),
                "--log-dir",
                str(log_dir),
                "--run",
                "--apply",
            ]
        )
        == 2
    )
    assert observed == []
    assert migrate._load_state(state_file(log_dir)).next_stage == 6

    assert (
        migrate.main(
            [
                str(baseline),
                str(working),
                "--log-dir",
                str(log_dir),
                "--run-next",
                "--apply",
            ]
        )
        == 0
    )
    assert observed and observed[0][-1] == "--apply"
    assert "correct-extensions" in observed[0]
    assert migrate._load_state(state_file(log_dir)).next_stage == 7


def test_safe_operator_loop_advances_routine_stages_and_pauses_before_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 4)
    observed: list[list[str]] = []

    def completed(
        command: list[str], *, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        observed.append(command)
        return completed_child(command)

    messages: list[tuple[str, object]] = []
    monkeypatch.setattr(migrate.subprocess, "run", completed)
    monkeypatch.setattr(
        migrate,
        "print",
        lambda message, *, file=None: messages.append((message, file)),
    )

    arguments = [str(baseline), str(working), "--log-dir", str(log_dir), "--run"]
    assert migrate.main(arguments) == 0

    state = migrate._load_state(state_file(log_dir))
    assert state.next_stage == 6
    assert [attempt.stage for attempt in state.attempts] == [
        stage.identifier for stage in migrate._stages()[:6]
    ]
    assert len(observed) == 2
    assert all("--apply" not in command for command in observed)
    assert any("paused at an operator checkpoint" in message for message, _ in messages)
    assert any("--run-next --apply" in message for message, _ in messages)


@pytest.mark.parametrize("next_stage", (6, 21))
def test_safe_operator_loop_runs_nothing_at_an_operator_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    next_stage: int,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, next_stage)
    observed: list[list[str]] = []
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: observed.append(command),
    )

    arguments = [str(baseline), str(working), "--log-dir", str(log_dir), "--run"]
    assert migrate.main(arguments) == 0
    assert observed == []
    assert migrate._load_state(state_file(log_dir)).next_stage == next_stage


def test_safe_operator_loop_returns_exact_child_failure_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    statuses = iter((0, 7))
    observed: list[list[str]] = []

    def completed(
        command: list[str], *, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        observed.append(command)
        return completed_child(command, next(statuses))

    monkeypatch.setattr(migrate.subprocess, "run", completed)

    arguments = [str(baseline), str(working), "--log-dir", str(log_dir), "--run"]
    assert migrate.main(arguments) == 7

    state = migrate._load_state(state_file(log_dir))
    assert state.next_stage == 1
    assert [attempt.exit_status for attempt in state.attempts] == [0, 7]
    assert len(observed) == 2


def test_safe_operator_loop_stops_if_a_collection_root_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    original_working = tmp_path / "original-working"
    observed: list[list[str]] = []

    def replace_after_first_child(
        command: list[str], *, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        observed.append(command)
        working.rename(original_working)
        working.mkdir()
        return completed_child(command)

    messages: list[tuple[str, object]] = []
    monkeypatch.setattr(migrate.subprocess, "run", replace_after_first_child)
    monkeypatch.setattr(
        migrate,
        "print",
        lambda message, *, file=None: messages.append((message, file)),
    )

    arguments = [str(baseline), str(working), "--log-dir", str(log_dir), "--run"]
    assert migrate.main(arguments) == 2

    state = migrate._load_state(state_file(log_dir))
    assert state.next_stage == 1
    assert len(observed) == 1
    assert messages[-1] == (
        "Migration coordinator cannot safely continue: collection identity "
        "changed during the safe operator loop.",
        sys.stderr,
    )
    assert str(tmp_path) not in messages[-1][0]


def test_safe_operator_loop_stops_if_restart_binding_is_substituted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    real_load_state = migrate._load_state
    load_count = 0

    def substituted_binding(path: Path) -> migrate.MigrationState:
        nonlocal load_count
        load_count += 1
        state = real_load_state(path)
        if load_count == 2:
            return migrate.MigrationState(
                "substituted-version",
                state.baseline,
                state.working,
                state.options,
                state.next_stage,
                state.attempts,
                state.created_at,
                state.updated_at,
            )
        return state

    observed: list[list[str]] = []
    monkeypatch.setattr(migrate, "_load_state", substituted_binding)
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: (
            observed.append(command) or completed_child(command)
        ),
    )

    arguments = [str(baseline), str(working), "--log-dir", str(log_dir), "--run"]
    assert migrate.main(arguments) == 2
    assert len(observed) == 1
    assert real_load_state(state_file(log_dir)).next_stage == 1


def test_safe_operator_loop_rejects_same_binding_lifecycle_jump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    real_load_state = migrate._load_state
    load_count = 0

    def substituted_lifecycle(path: Path) -> migrate.MigrationState:
        nonlocal load_count
        load_count += 1
        state = real_load_state(path)
        if load_count != 2:
            return state
        now = "2026-08-29T12:00:01-04:00"
        skipped = tuple(
            migrate.Attempt(
                stage.identifier,
                "run",
                0,
                now,
                f"substituted-{index}.log",
                stage.mode == "apply",
            )
            for index, stage in enumerate(migrate._stages()[1:7], start=2)
        )
        return migrate.MigrationState(
            state.tool_version,
            state.baseline,
            state.working,
            state.options,
            7,
            (*state.attempts, *skipped),
            state.created_at,
            now,
        )

    observed: list[list[str]] = []
    monkeypatch.setattr(migrate, "_load_state", substituted_lifecycle)
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: (
            observed.append(command) or completed_child(command)
        ),
    )

    arguments = [str(baseline), str(working), "--log-dir", str(log_dir), "--run"]
    assert migrate.main(arguments) == 2
    assert len(observed) == 1
    assert real_load_state(state_file(log_dir)).next_stage == 1


def test_safe_operator_loop_pauses_after_successful_validation_for_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 2)
    observed: list[list[str]] = []
    messages: list[tuple[str, object]] = []
    synopses: list[tuple[Path, migrate.MigrationState]] = []
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: (
            observed.append(command) or completed_child(command)
        ),
    )
    monkeypatch.setattr(
        migrate,
        "print",
        lambda message, *, file=None: messages.append((message, file)),
    )
    monkeypatch.setattr(
        migrate,
        "print_synopsis",
        lambda path, state: synopses.append((path, state)),
    )

    arguments = [str(baseline), str(working), "--log-dir", str(log_dir), "--run"]
    assert migrate.main(arguments) == 0
    assert len(observed) == 1
    assert migrate._load_state(state_file(log_dir)).next_stage == 3
    assert any("paused for validation review" in message for message, _ in messages)
    assert len(synopses) == 1
    assert synopses[0][0] == log_dir
    assert synopses[0][1].next_stage == 3


def test_safe_operator_loop_preserves_validation_acknowledgement_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 2)
    arguments = [str(baseline), str(working), "--log-dir", str(log_dir)]

    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: completed_child(command, 1),
    )
    assert migrate.main([*arguments, "--run"]) == 1
    stopped = migrate._load_state(state_file(log_dir))
    assert stopped.next_stage == 2
    assert stopped.attempts[-1].stage == "baseline-validation"
    assert stopped.attempts[-1].exit_status == 1

    assert migrate.main([*arguments, "--accept-status"]) == 0
    assert migrate._load_state(state_file(log_dir)).next_stage == 3


def test_safe_operator_loop_finishes_with_human_signoff_still_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    stages = migrate._stages()
    _state_at(log_dir, baseline, working, 22)
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: completed_child(command),
    )
    messages: list[tuple[str, object]] = []
    monkeypatch.setattr(
        migrate,
        "print",
        lambda message, *, file=None: messages.append((message, file)),
    )

    arguments = [str(baseline), str(working), "--log-dir", str(log_dir), "--run"]
    assert migrate.main(arguments) == 0
    assert migrate._load_state(state_file(log_dir)).next_stage == 23
    assert any("paused for validation review" in message for message, _ in messages)

    assert migrate.main(arguments) == 0
    assert migrate._load_state(state_file(log_dir)).next_stage == len(stages)
    assert any("final sign-off boundary" in message for message, _ in messages)
    assert any("eligible for human sign-off only" in message for message, _ in messages)


def test_safe_operator_loop_runs_real_children_until_validation_review(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    common = ["migrate", baseline, working, "--log-dir", log_dir]
    started = run_pymo(*common, "--start", "--no-cache", "--no-timestamps")
    assert started.returncode == 0, started.stdout + started.stderr

    result = run_pymo(*common, "--run")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Running one migration stage: baseline-scan" in result.stdout
    assert "Stage complete: baseline-validation" in result.stdout
    assert "Safe operator loop paused for validation review" in result.stdout
    assert "Next checkpoint: working-validation" in result.stdout
    state = migrate._load_state(state_file(log_dir))
    assert state.next_stage == 3
    assert len(state.attempts) == 3
    assert len(list(log_dir.glob("*.log"))) == 3
    assert list(baseline.iterdir()) == []
    assert list(working.iterdir()) == []


def test_safe_operator_loop_does_not_cross_warning_only_validation(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    (baseline / "note.jpg").write_text("not image content\n", encoding="utf-8")
    (working / "note.jpg").write_text("not image content\n", encoding="utf-8")
    log_dir = tmp_path / "private-logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 2)

    result = run_pymo("migrate", baseline, working, "--log-dir", log_dir, "--run")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "WARNING extension_content_mismatch" in result.stdout
    assert "Safe operator loop paused for validation review" in result.stdout
    state = migrate._load_state(state_file(log_dir))
    assert state.next_stage == 3
    assert state.attempts[-1].stage == "baseline-validation"
    assert len(list(log_dir.glob("*.log"))) == 1


def test_real_child_status_stops_and_only_validation_one_can_be_acknowledged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 2)

    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: completed_child(command, 1),
    )
    arguments = [str(baseline), str(working), "--log-dir", str(log_dir)]

    assert migrate.main([*arguments, "--run-next"]) == 1
    stopped = migrate._load_state(state_file(log_dir))
    assert stopped.next_stage == 2
    assert stopped.attempts[-1].exit_status == 1
    assert migrate.main([*arguments, "--accept-status"]) == 0
    accepted = migrate._load_state(state_file(log_dir))
    assert accepted.next_stage == 3
    assert accepted.attempts[-1].action == "acknowledge-status"
    assert accepted.attempts[-1].exit_status == 1

    _state_at(log_dir, baseline, working, 4)
    assert migrate.main([*arguments, "--run-next"]) == 1
    assert migrate.main([*arguments, "--accept-status"]) == 2
    assert migrate._load_state(state_file(log_dir)).next_stage == 4


def test_external_quarantine_confirmation_requires_absent_dups_path(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 21)
    dups = working / "dups"
    dups.mkdir()
    arguments = [
        str(baseline),
        str(working),
        "--log-dir",
        str(log_dir),
        "--confirm-quarantine",
    ]

    assert migrate.main(arguments) == 1
    assert migrate._load_state(state_file(log_dir)).next_stage == 21
    dups.rmdir()
    assert migrate.main(arguments) == 0
    state = migrate._load_state(state_file(log_dir))
    assert state.next_stage == 22
    assert state.attempts[-1].action == "confirm-quarantine"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(schema_version=99), "schema is unsupported"),
        (lambda value: value.update(tool_version="0.0.0"), "different pymo version"),
        (lambda value: value.update(next_stage=1), "does not match its history"),
        (lambda value: value["options"].pop("no_cache"), "options are malformed"),
        (
            lambda value: value["options"].update(verbose=True, quiet=True),
            "output options conflict",
        ),
        (lambda value: value["options"].update(workers=33), "workers are out of range"),
        (lambda value: value.update(created_at="not-a-time"), "invalid creation time"),
        (lambda value: value.update(baseline="relative"), "non-absolute baseline"),
    ],
)
def test_restart_state_fails_closed(tmp_path: Path, mutation, message: str) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    started = run_pymo("migrate", baseline, working, "--log-dir", log_dir, "--start")
    assert started.returncode == 0
    payload = json.loads(state_file(log_dir).read_text(encoding="utf-8"))
    mutation(payload)
    state_file(log_dir).write_text(json.dumps(payload), encoding="utf-8")

    result = run_pymo("migrate", baseline, working, "--log-dir", log_dir)

    assert result.returncode == 2
    assert message in result.stderr
    assert list(baseline.iterdir()) == []
    assert list(working.iterdir()) == []


def test_restart_state_and_lock_require_private_regular_files(tmp_path: Path) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    common = ["migrate", baseline, working, "--log-dir", log_dir]
    assert run_pymo(*common, "--start").returncode == 0

    state_file(log_dir).chmod(0o644)
    state_result = run_pymo(*common)
    assert state_result.returncode == 2
    assert "restart state is not private" in state_result.stderr

    state_file(log_dir).chmod(0o600)
    (log_dir / "pymo-migration-state.lock").chmod(0o644)
    lock_result = run_pymo(*common)
    assert lock_result.returncode == 2
    assert "state lock is not private" in lock_result.stderr


def test_complete_empty_collection_sequence_is_restartable_and_stage_logged(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "private-logs"
    common = ["migrate", baseline, working, "--log-dir", log_dir]
    started = run_pymo(*common, "--start", "--no-cache", "--no-timestamps")
    assert started.returncode == 0, started.stdout + started.stderr

    apply_stages = {
        "extension-apply",
        "organize-apply",
        "rename-apply",
        "image-duplicates-apply",
        "video-duplicates-apply",
    }
    while True:
        payload = json.loads(state_file(log_dir).read_text(encoding="utf-8"))
        next_stage = payload["next_stage"]
        if next_stage == len(migrate._stages()):
            break
        stage = migrate._stages()[next_stage]
        if stage.identifier == "external-quarantine":
            result = run_pymo(*common, "--confirm-quarantine")
        else:
            arguments: list[object] = [*common, "--run-next"]
            if stage.identifier in apply_stages:
                arguments.append("--apply")
            result = run_pymo(*arguments)
        assert result.returncode == 0, result.stdout + result.stderr

    status = run_pymo(*common)
    assert status.returncode == 0, status.stdout + status.stderr
    assert "Migration sequence complete" in status.stdout
    final_state = json.loads(state_file(log_dir).read_text(encoding="utf-8"))
    assert final_state["next_stage"] == len(migrate._stages())
    assert len(final_state["attempts"]) == len(migrate._stages())
    logs = sorted(log_dir.glob("*.log"))
    assert len(logs) == len(migrate._stages()) - 1
    assert all(stat_mode(path) == 0o600 for path in logs)
    outcomes = sorted(log_dir.glob("*.outcome.json"))
    assert len(outcomes) == len(migrate._stages()) - 1
    assert all(stat_mode(path) == 0o600 for path in outcomes)
    assert all(
        attempt["outcome_file"] is not None
        for attempt in final_state["attempts"]
        if attempt["action"] == "run"
    )
    assert all(
        isinstance(attempt["duration_milliseconds"], int)
        and attempt["duration_milliseconds"] >= 0
        for attempt in final_state["attempts"]
    )
    assert list(baseline.iterdir()) == []
    assert (working / "pics").is_dir()
    assert (working / "vids").is_dir()
    assert not (working / "dups").exists()


def test_complete_media_sequence_preserves_bytes_through_external_quarantine(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    source = baseline / "first.jpg"
    Image.new("RGB", (4, 3), (20, 40, 60)).save(source, format="PNG")
    shutil.copyfile(source, baseline / "second.jpg")
    shutil.copytree(baseline, working, dirs_exist_ok=True)
    original_bytes = source.read_bytes()
    log_dir = tmp_path / "private-logs"
    quarantine = tmp_path / "retained-quarantine"
    common = ["migrate", baseline, working, "--log-dir", log_dir]
    started = run_pymo(*common, "--start", "--no-cache", "--no-timestamps")
    assert started.returncode == 0, started.stdout + started.stderr

    while True:
        payload = json.loads(state_file(log_dir).read_text(encoding="utf-8"))
        next_stage = payload["next_stage"]
        if next_stage == len(migrate._stages()):
            break
        stage = migrate._stages()[next_stage]
        if stage.identifier == "external-quarantine":
            review = working / "dups"
            assert len(list((review / "pics").iterdir())) == 1
            review.rename(quarantine)
            result = run_pymo(*common, "--confirm-quarantine")
        else:
            arguments: list[object] = [*common, "--run-next"]
            if stage.mode == "apply":
                arguments.append("--apply")
            result = run_pymo(*arguments)
        assert result.returncode == 0, result.stdout + result.stderr

    assert source.read_bytes() == original_bytes
    assert (baseline / "second.jpg").read_bytes() == original_bytes
    retained = list((working / "pics").iterdir())
    reviewed = list((quarantine / "pics").iterdir())
    assert len(retained) == len(reviewed) == 1
    assert retained[0].suffix == ".png"
    assert retained[0].read_bytes() == reviewed[0].read_bytes() == original_bytes
    assert not (working / "dups").exists()
    assert any(working.glob("*-actions-log.jsonl"))
    assert "Migration synopsis" in result.stdout
    synopsis = result.stdout.split("Migration synopsis", maxsplit=1)[1]
    assert "Workflow: complete; human sign-off pending" in synopsis
    assert "Baseline: 2 file(s)" in synopsis
    assert "2 extension corrections" in synopsis
    assert "2 organization moves" in synopsis
    assert "2 canonical renames" in synopsis
    assert "1 duplicate copy of image content isolated across 1 group" in synopsis
    assert "Duplicate review storage before external retention: 1 file(s)" in synopsis
    assert "confirmed by the operator" in synopsis
    assert "did not inspect the retained destination" in synopsis
    assert "Observed preservation: COMPLETE; 1/1" in synopsis
    assert str(tmp_path) not in synopsis

    status = run_pymo(*common)
    assert status.returncode == 0, status.stdout + status.stderr
    assert "Migration synopsis" in status.stdout
    assert str(tmp_path) not in status.stdout


def test_successful_child_without_typed_outcome_fails_before_state_advance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    before = state_file(log_dir).read_bytes()
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: subprocess.CompletedProcess(command, 0),
    )

    result = migrate.main(
        [str(baseline), str(working), "--log-dir", str(log_dir), "--run-next"]
    )

    assert result == 2
    assert state_file(log_dir).read_bytes() == before


def test_status_fails_closed_if_recorded_outcome_becomes_unsafe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 0)
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: completed_child(command),
    )
    common = [str(baseline), str(working), "--log-dir", str(log_dir)]
    assert migrate.main([*common, "--run-next"]) == 0
    state = migrate._load_state(state_file(log_dir))
    outcome = log_dir / str(state.attempts[-1].outcome_file)
    outcome.chmod(0o644)

    messages: list[tuple[str, object]] = []
    monkeypatch.setattr(
        migrate,
        "print",
        lambda message, *, file=None: messages.append((message, file)),
    )
    assert migrate.main(common) == 2
    assert messages[-1] == (
        "Migration coordinator cannot safely continue: migration synopsis cannot "
        "trust a private stage outcome.",
        sys.stderr,
    )
    assert str(tmp_path) not in messages[-1][0]


def test_state_rejects_successful_attempt_without_outcome_reference(
    tmp_path: Path,
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 1)
    payload = json.loads(state_file(log_dir).read_text(encoding="utf-8"))
    payload["attempts"][0]["outcome_file"] = None
    state_file(log_dir).write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        migrate.MigrationCoordinatorError,
        match="migration restart attempt is inconsistent",
    ):
        migrate._load_state(state_file(log_dir))


def test_resume_validates_prior_outcomes_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 1)
    payload = json.loads(state_file(log_dir).read_text(encoding="utf-8"))
    outcome = log_dir / payload["attempts"][0]["outcome_file"]
    outcome.chmod(0o644)
    observed: list[list[str]] = []
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: observed.append(command),
    )

    result = migrate.main(
        [str(baseline), str(working), "--log-dir", str(log_dir), "--run-next"]
    )

    assert result == 2
    assert observed == []
    assert (
        json.loads(state_file(log_dir).read_text(encoding="utf-8"))["next_stage"] == 1
    )
