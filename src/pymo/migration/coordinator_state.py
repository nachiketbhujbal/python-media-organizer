"""Private, fail-closed restart state for guided migration."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pymo.migration.workflow import CoordinatorOptions, _stages

# This identifies the private restart-state compatibility contract.
MIGRATION_STATE_SCHEMA_VERSION = 1


class MigrationCoordinatorError(RuntimeError):
    """The guided workflow cannot safely continue."""


@dataclass(frozen=True)
class Attempt:
    stage: str
    action: Literal["run", "acknowledge-status", "confirm-quarantine"]
    exit_status: int
    completed_at: str
    log_file: str | None
    apply: bool

    def as_json(self) -> dict[str, bool | int | str | None]:
        return {
            "stage": self.stage,
            "action": self.action,
            "exit_status": self.exit_status,
            "completed_at": self.completed_at,
            "log_file": self.log_file,
            "apply": self.apply,
        }


@dataclass(frozen=True)
class MigrationState:
    tool_version: str
    baseline: Path
    working: Path
    options: CoordinatorOptions
    next_stage: int
    attempts: tuple[Attempt, ...]
    created_at: str
    updated_at: str

    def as_json(self) -> dict[str, Any]:
        return {
            "schema_version": MIGRATION_STATE_SCHEMA_VERSION,
            "tool_version": self.tool_version,
            "baseline": str(self.baseline),
            "working": str(self.working),
            "options": self.options.as_json(),
            "next_stage": self.next_stage,
            "attempts": [attempt.as_json() for attempt in self.attempts],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _state_path(log_dir: Path) -> Path:
    return log_dir / "pymo-migration-state.json"


def _lock_path(log_dir: Path) -> Path:
    return log_dir / "pymo-migration-state.lock"


def _prepare_log_dir(log_dir: Path, *, create: bool) -> None:
    if log_dir.is_symlink():
        raise MigrationCoordinatorError(
            "private log directory must not be a symbolic link"
        )
    if create:
        try:
            log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as error:
            raise MigrationCoordinatorError(
                "private log directory could not be created"
            ) from error
    if not log_dir.is_dir():
        raise MigrationCoordinatorError("private log directory does not exist")


@contextmanager
def _state_lock(log_dir: Path) -> Iterator[None]:
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(_lock_path(log_dir), flags, 0o600)
    except OSError as error:
        raise MigrationCoordinatorError("migration state lock is unsafe") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise MigrationCoordinatorError(
                "migration state lock is not a regular file"
            )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise MigrationCoordinatorError(
                "another migration coordinator is using this private log directory"
            ) from error
        yield
    finally:
        os.close(descriptor)


def _read_regular_file(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise MigrationCoordinatorError(
            "migration restart state cannot be read"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MigrationCoordinatorError(
                "migration restart state is not a regular file"
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > 16 * 1024 * 1024:
                raise MigrationCoordinatorError("migration restart state is too large")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _write_state(path: Path, state: MigrationState) -> None:
    payload = (
        json.dumps(state.as_json(), sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
    )
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written == 0:
                raise OSError("short migration state write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        raise MigrationCoordinatorError(
            "migration restart state could not be saved"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _require_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise MigrationCoordinatorError(f"migration restart state has invalid {field}")
    return value


def _require_optional_int(value: object, field: str) -> int | None:
    if value is not None and (type(value) is not int or value <= 0):
        raise MigrationCoordinatorError(f"migration restart state has invalid {field}")
    return value


def _require_optional_str(value: object, field: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value):
        raise MigrationCoordinatorError(f"migration restart state has invalid {field}")
    return value


def _options_from_json(value: object) -> CoordinatorOptions:
    expected = {
        "verbose",
        "quiet",
        "timestamps",
        "config",
        "show_ignored",
        "show_files",
        "ffmpeg",
        "ffprobe",
        "decode_timeout",
        "workers",
        "no_cache",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise MigrationCoordinatorError("migration restart options are malformed")
    return CoordinatorOptions(
        verbose=_require_bool(value["verbose"], "verbose"),
        quiet=_require_bool(value["quiet"], "quiet"),
        timestamps=_require_bool(value["timestamps"], "timestamps"),
        config=_require_optional_str(value["config"], "config"),
        show_ignored=_require_bool(value["show_ignored"], "show_ignored"),
        show_files=_require_bool(value["show_files"], "show_files"),
        ffmpeg=_require_optional_str(value["ffmpeg"], "ffmpeg"),
        ffprobe=_require_optional_str(value["ffprobe"], "ffprobe"),
        decode_timeout=_require_optional_int(value["decode_timeout"], "decode_timeout"),
        workers=_require_optional_int(value["workers"], "workers"),
        no_cache=_require_bool(value["no_cache"], "no_cache"),
    )


def _attempt_from_json(value: object) -> Attempt:
    expected = {"stage", "action", "exit_status", "completed_at", "log_file", "apply"}
    if not isinstance(value, dict) or set(value) != expected:
        raise MigrationCoordinatorError("migration restart attempt is malformed")
    stage = value["stage"]
    action = value["action"]
    exit_status = value["exit_status"]
    completed_at = value["completed_at"]
    if not isinstance(stage, str) or not stage:
        raise MigrationCoordinatorError("migration restart attempt has invalid stage")
    if action not in {"run", "acknowledge-status", "confirm-quarantine"}:
        raise MigrationCoordinatorError("migration restart attempt has invalid action")
    if type(exit_status) is not int or not 0 <= exit_status <= 255:
        raise MigrationCoordinatorError("migration restart attempt has invalid status")
    if not isinstance(completed_at, str) or not completed_at:
        raise MigrationCoordinatorError(
            "migration restart attempt has invalid timestamp"
        )
    log_file = _require_optional_str(value["log_file"], "attempt log file")
    apply = _require_bool(value["apply"], "attempt apply flag")
    return Attempt(stage, action, exit_status, completed_at, log_file, apply)


def _validate_attempt_order(attempts: tuple[Attempt, ...], next_stage: int) -> None:
    stages = _stages()
    expected = 0
    previous: Attempt | None = None
    validation_stages = {
        "baseline-validation",
        "working-validation",
        "final-working-validation",
    }
    for attempt in attempts:
        if expected >= len(stages) or attempt.stage != stages[expected].identifier:
            raise MigrationCoordinatorError(
                "migration restart attempts are out of order"
            )
        stage = stages[expected]
        if attempt.action == "run":
            if stage.mode == "checkpoint" or attempt.apply != (stage.mode == "apply"):
                raise MigrationCoordinatorError(
                    "migration restart attempt is inconsistent"
                )
            if attempt.exit_status == 0:
                expected += 1
        elif attempt.action == "acknowledge-status":
            if (
                stage.identifier not in validation_stages
                or attempt.exit_status != 1
                or previous is None
                or previous.stage != stage.identifier
                or previous.action != "run"
                or previous.exit_status != 1
            ):
                raise MigrationCoordinatorError(
                    "migration status acknowledgement is invalid"
                )
            expected += 1
        else:
            if stage.mode != "checkpoint" or attempt.exit_status != 0:
                raise MigrationCoordinatorError(
                    "migration quarantine confirmation is invalid"
                )
            expected += 1
        previous = attempt
    if expected != next_stage:
        raise MigrationCoordinatorError(
            "migration restart stage does not match its history"
        )


def _load_state(path: Path) -> MigrationState:
    try:
        value = json.loads(_read_regular_file(path))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise MigrationCoordinatorError(
            "migration restart state is malformed"
        ) from error
    expected = {
        "schema_version",
        "tool_version",
        "baseline",
        "working",
        "options",
        "next_stage",
        "attempts",
        "created_at",
        "updated_at",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise MigrationCoordinatorError("migration restart state is malformed")
    if value["schema_version"] != MIGRATION_STATE_SCHEMA_VERSION:
        raise MigrationCoordinatorError("migration restart state schema is unsupported")
    tool_version = _require_optional_str(value["tool_version"], "tool version")
    baseline = _require_optional_str(value["baseline"], "baseline")
    working = _require_optional_str(value["working"], "working collection")
    next_stage = value["next_stage"]
    attempts_value = value["attempts"]
    created_at = value["created_at"]
    updated_at = value["updated_at"]
    if tool_version is None or baseline is None or working is None:
        raise MigrationCoordinatorError("migration restart roots are malformed")
    if type(next_stage) is not int or not 0 <= next_stage <= len(_stages()):
        raise MigrationCoordinatorError("migration restart stage is invalid")
    if not isinstance(attempts_value, list):
        raise MigrationCoordinatorError("migration restart attempts are malformed")
    if not isinstance(created_at, str) or not created_at:
        raise MigrationCoordinatorError("migration restart creation time is invalid")
    if not isinstance(updated_at, str) or not updated_at:
        raise MigrationCoordinatorError("migration restart update time is invalid")
    attempts = tuple(_attempt_from_json(item) for item in attempts_value)
    _validate_attempt_order(attempts, next_stage)
    return MigrationState(
        tool_version=tool_version,
        baseline=Path(baseline),
        working=Path(working),
        options=_options_from_json(value["options"]),
        next_stage=next_stage,
        attempts=attempts,
        created_at=created_at,
        updated_at=updated_at,
    )


def _updated_state(
    state: MigrationState, attempt: Attempt, *, advance: bool
) -> MigrationState:
    return MigrationState(
        tool_version=state.tool_version,
        baseline=state.baseline,
        working=state.working,
        options=state.options,
        next_stage=state.next_stage + int(advance),
        attempts=(*state.attempts, attempt),
        created_at=state.created_at,
        updated_at=_now(),
    )
