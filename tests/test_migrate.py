from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from pymo import __version__, migrate
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
    payload = json.loads(state_file(log_dir).read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
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
    assert status.returncode == 1
    assert "workers differs from the recorded" in status.stderr
    assert (
        json.loads(state_file(log_dir).read_text(encoding="utf-8"))["next_stage"] == 0
    )


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
    attempts = tuple(
        migrate.Attempt(
            stage.identifier, "run", 0, now, f"{index}.log", stage.mode == "apply"
        )
        for index, stage in enumerate(migrate._stages()[:next_stage], start=1)
        if stage.mode != "checkpoint"
    )
    state = migrate.MigrationState(
        __version__,
        baseline.resolve(),
        working.resolve(),
        migrate.CoordinatorOptions(
            False, False, True, None, False, False, None, None, None, None, False
        ),
        next_stage,
        attempts,
        now,
        now,
    )
    migrate._write_state(state_file(log_dir), state)


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
        return subprocess.CompletedProcess(command, 0)

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
                "--run-next",
                "--apply",
            ]
        )
        == 0
    )
    assert observed and observed[0][-1] == "--apply"
    assert "correct-extensions" in observed[0]
    assert migrate._load_state(state_file(log_dir)).next_stage == 7


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
        lambda command, *, check: subprocess.CompletedProcess(command, 1),
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

    assert result.returncode == 1
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
    assert state_result.returncode == 1
    assert "restart state is not private" in state_result.stderr

    state_file(log_dir).chmod(0o600)
    (log_dir / "pymo-migration-state.lock").chmod(0o644)
    lock_result = run_pymo(*common)
    assert lock_result.returncode == 1
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
