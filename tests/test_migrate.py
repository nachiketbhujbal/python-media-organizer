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
    assert status.returncode == 2
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
            stage.identifier,
            "confirm-quarantine" if stage.mode == "checkpoint" else "run",
            0,
            now,
            None if stage.mode == "checkpoint" else f"{index}.log",
            stage.mode == "apply",
        )
        for index, stage in enumerate(migrate._stages()[:next_stage], start=1)
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

    result = run_pymo(
        "migrate", baseline, working, "--log-dir", log_dir, "--interactive"
    )

    assert result.returncode == 2
    assert "--interactive requires terminal input" in result.stderr
    assert state_file(log_dir).read_bytes() == before
    assert len(list(log_dir.iterdir())) == 1


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
        return subprocess.CompletedProcess(command, 0)

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
        return subprocess.CompletedProcess(command, 0)

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
    failed = migrate.Attempt(
        "baseline-validation",
        "run",
        1,
        "2026-08-29T12:00:01-04:00",
        "failed.log",
        False,
    )
    current = migrate._load_state(state_file(log_dir))
    migrate._write_state(
        state_file(log_dir), migrate._updated_state(current, failed, advance=False)
    )
    observed: list[list[str]] = []

    def completed(
        command: list[str], *, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        observed.append(command)
        return subprocess.CompletedProcess(command, 0)

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
        return subprocess.CompletedProcess(command, 0)

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
        return subprocess.CompletedProcess(command, 0)

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
        return subprocess.CompletedProcess(command, next(statuses))

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
        return subprocess.CompletedProcess(command, 0)

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
            observed.append(command) or subprocess.CompletedProcess(command, 0)
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
            observed.append(command) or subprocess.CompletedProcess(command, 0)
        ),
    )

    arguments = [str(baseline), str(working), "--log-dir", str(log_dir), "--run"]
    assert migrate.main(arguments) == 2
    assert len(observed) == 1
    assert real_load_state(state_file(log_dir)).next_stage == 1


def test_safe_operator_loop_pauses_after_successful_validation_for_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collections(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    _state_at(log_dir, baseline, working, 2)
    observed: list[list[str]] = []
    messages: list[tuple[str, object]] = []
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda command, *, check: (
            observed.append(command) or subprocess.CompletedProcess(command, 0)
        ),
    )
    monkeypatch.setattr(
        migrate,
        "print",
        lambda message, *, file=None: messages.append((message, file)),
    )

    arguments = [str(baseline), str(working), "--log-dir", str(log_dir), "--run"]
    assert migrate.main(arguments) == 0
    assert len(observed) == 1
    assert migrate._load_state(state_file(log_dir)).next_stage == 3
    assert any("paused for validation review" in message for message, _ in messages)


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
        lambda command, *, check: subprocess.CompletedProcess(command, 1),
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
        lambda command, *, check: subprocess.CompletedProcess(command, 0),
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
