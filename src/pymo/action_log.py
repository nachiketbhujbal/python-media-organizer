#!/usr/bin/env python3
"""Shared append-only action history for reversible media operations."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Iterator, TextIO

from pymo.collection import CollectionLayout


# This constant identifies the current on-disk journal schema and must remain
# stable while collection-named action histories use it.
ACTION_LOG_SCHEMA_VERSION = 1


class ActionOperation(StrEnum):
    """Stable operation identifiers persisted in action records."""

    MOVE = "MOVE"
    RENAME = "RENAME"
    CREATE_DIRECTORY = "CREATE_DIR"
    REMOVE_DIRECTORY = "REMOVE_DIR"

    @property
    def is_file(self) -> bool:
        return self in (self.MOVE, self.RENAME)


class ToolId(StrEnum):
    """Stable tool identifiers persisted in the append-only action log."""

    ORGANIZE = "organize_media"
    RENAME = "rename_media"
    IMAGE_DUPLICATES = "find_image_duplicates"
    VIDEO_DUPLICATES = "find_video_duplicates"


class ActionLogError(RuntimeError):
    """Base exception for action-history problems."""


class ActionConflict(ActionLogError):
    """Raised when current filesystem state does not match recorded history."""


class NoUndoableRun(ActionLogError):
    """Raised when a tool has no active or interrupted run to reverse."""


def action_log_path(root: Path) -> Path:
    """Return the canonical action-log path for a media-collection root."""
    root = root.expanduser().resolve()
    return CollectionLayout(root).action_log


def is_action_log_path(root: Path, path: Path) -> bool:
    candidate = path.expanduser().resolve(strict=False)
    return candidate == action_log_path(root)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_identity(path: Path) -> dict[str, int | str]:
    if path.is_symlink() or not path.is_file():
        raise ActionConflict(f"not a regular file: {path}")
    stat = path.stat()
    return {
        "size": stat.st_size,
        "sha256": _sha256(path),
        "device": stat.st_dev,
        "inode": stat.st_ino,
    }


def _relative_path(root: Path, path: Path) -> str:
    root = root.resolve()
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve(strict=False)
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ActionLogError(f"path is outside the managed folder: {path}") from error
    if not relative.parts:
        raise ActionLogError("an action cannot target the managed folder itself")
    return relative.as_posix()


def _absolute_path(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise ActionLogError(f"invalid relative path in action log: {relative!r}")
    return root.joinpath(*pure.parts)


@dataclass(frozen=True)
class Action:
    operation: str
    before: str | None
    after: str | None
    entry_type: str
    identity: dict[str, int | str] | None = None

    def __post_init__(self) -> None:
        try:
            operation = ActionOperation(self.operation)
        except ValueError as error:
            raise ActionLogError(f"unsupported operation: {self.operation}")
        if operation.is_file:
            if not self.before or not self.after or self.entry_type != "file":
                raise ActionLogError("file actions require before and after paths")
            if not self.identity:
                raise ActionLogError("file actions require identity information")
        elif operation is ActionOperation.CREATE_DIRECTORY:
            if (
                self.before is not None
                or not self.after
                or self.entry_type != "directory"
            ):
                raise ActionLogError("CREATE_DIR requires only an after path")
        elif operation is ActionOperation.REMOVE_DIRECTORY:
            if (
                not self.before
                or self.after is not None
                or self.entry_type != "directory"
            ):
                raise ActionLogError("REMOVE_DIR requires only a before path")

    @classmethod
    def for_file(
        cls,
        root: Path,
        source: Path,
        target: Path,
        operation: str,
    ) -> Action:
        operation = operation.upper()
        try:
            parsed_operation = ActionOperation(operation)
        except ValueError as error:
            raise ActionLogError(f"not a file operation: {operation}") from error
        if not parsed_operation.is_file:
            raise ActionLogError(f"not a file operation: {operation}")
        return cls(
            operation=operation,
            before=_relative_path(root, source),
            after=_relative_path(root, target),
            entry_type="file",
            identity=file_identity(source),
        )

    @classmethod
    def create_directory(cls, root: Path, path: Path) -> Action:
        return cls(
            operation="CREATE_DIR",
            before=None,
            after=_relative_path(root, path),
            entry_type="directory",
        )

    @classmethod
    def remove_directory(cls, root: Path, path: Path) -> Action:
        return cls(
            operation="REMOVE_DIR",
            before=_relative_path(root, path),
            after=None,
            entry_type="directory",
        )

    def reversed(self) -> Action:
        if ActionOperation(self.operation).is_file:
            return Action(
                operation=self.operation,
                before=self.after,
                after=self.before,
                entry_type=self.entry_type,
                identity=self.identity,
            )
        if self.operation == ActionOperation.CREATE_DIRECTORY:
            return Action(
                operation="REMOVE_DIR",
                before=self.after,
                after=None,
                entry_type="directory",
            )
        return Action(
            operation="CREATE_DIR",
            before=None,
            after=self.before,
            entry_type="directory",
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "before": self.before,
            "after": self.after,
            "entry_type": self.entry_type,
            "identity": self.identity,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> Action:
        identity = value.get("identity")
        if identity is not None and not isinstance(identity, dict):
            raise ActionLogError("invalid identity in action log")
        return cls(
            operation=str(value.get("operation", "")),
            before=value.get("before") if isinstance(value.get("before"), str) else None,
            after=value.get("after") if isinstance(value.get("after"), str) else None,
            entry_type=str(value.get("entry_type", "")),
            identity=identity,
        )


@dataclass
class RunRecord:
    run_id: str
    tool: str
    mode: str
    started_index: int
    target_run_id: str | None = None
    actions: list[tuple[str, Action]] = field(default_factory=list)
    completed_action_ids: set[str] = field(default_factory=set)
    committed: bool = False


@dataclass(frozen=True)
class UndoPlan:
    target: RunRecord
    actions: tuple[Action, ...]


@dataclass(frozen=True)
class UndoResult:
    target_run_id: str
    undo_run_id: str
    action_count: int


class ActionTransaction:
    def __init__(
        self,
        log: ActionLog,
        handle: TextIO,
        tool: str,
        mode: str = "APPLY",
        target_run_id: str | None = None,
    ) -> None:
        self.log = log
        self.handle = handle
        self.tool = tool
        self.mode = mode
        self.target_run_id = target_run_id
        self.run_id = str(uuid.uuid4())
        self.committed = False
        self.action_count = 0
        self.log._append(
            handle,
            {
                "event": "RUN_STARTED",
                "run_id": self.run_id,
                "tool": tool,
                "mode": mode,
                "target_run_id": target_run_id,
            },
        )

    def perform(self, action: Action) -> None:
        action_id = str(uuid.uuid4())
        self.log._append(
            self.handle,
            {
                "event": "ACTION_PLANNED",
                "run_id": self.run_id,
                "action_id": action_id,
                "action": action.as_dict(),
            },
        )
        self.log._execute_action(action)
        self.log._append(
            self.handle,
            {
                "event": "ACTION_COMPLETED",
                "run_id": self.run_id,
                "action_id": action_id,
            },
        )
        self.action_count += 1

    def commit(self) -> None:
        if self.committed:
            raise ActionLogError("transaction is already committed")
        self.log._append(
            self.handle,
            {
                "event": "RUN_COMMITTED",
                "run_id": self.run_id,
                "action_count": self.action_count,
                "target_run_id": self.target_run_id,
            },
        )
        self.committed = True

    def mark_incomplete(self, reason: str) -> None:
        self.log._append(
            self.handle,
            {
                "event": "RUN_INCOMPLETE",
                "run_id": self.run_id,
                "reason": reason,
            },
        )


class ActionLog:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        if not self.root.is_dir():
            raise ActionLogError(f"not a directory: {self.root}")
        self.canonical_path = action_log_path(self.root)
        if self.canonical_path.is_symlink():
            raise ActionConflict(
                f"action log cannot be a symbolic link: {self.canonical_path}"
            )
        self.path = self.canonical_path

    @contextmanager
    def _locked(self, create: bool) -> Iterator[TextIO]:
        if not create and not self.path.exists():
            raise NoUndoableRun(f"no action log found in {self.root}")
        mode = "a+" if create else "r"
        with self.path.open(mode, encoding="utf-8", newline="") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield handle
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _append(self, handle: TextIO, event: dict[str, object]) -> None:
        value = {
            "schema_version": ACTION_LOG_SCHEMA_VERSION,
            "timestamp": _timestamp(),
            **event,
        }
        handle.seek(0, os.SEEK_END)
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    def _read(self, handle: TextIO) -> list[dict[str, object]]:
        handle.seek(0)
        events: list[dict[str, object]] = []
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ActionLogError(
                    f"invalid JSON on line {line_number} of {self.path}"
                ) from error
            if (
                not isinstance(event, dict)
                or event.get("schema_version") != ACTION_LOG_SCHEMA_VERSION
            ):
                raise ActionLogError(
                    f"unsupported action-log record on line {line_number}"
                )
            events.append(event)
        return events

    def _runs(self, events: list[dict[str, object]]) -> list[RunRecord]:
        runs: list[RunRecord] = []
        by_id: dict[str, RunRecord] = {}
        for index, event in enumerate(events):
            name = event.get("event")
            run_id = event.get("run_id")
            if not isinstance(run_id, str):
                raise ActionLogError(f"action-log event {index + 1} has no run ID")
            if name == "RUN_STARTED":
                if run_id in by_id:
                    raise ActionLogError(f"duplicate run ID in action log: {run_id}")
                run = RunRecord(
                    run_id=run_id,
                    tool=str(event.get("tool", "")),
                    mode=str(event.get("mode", "")),
                    target_run_id=(
                        event.get("target_run_id")
                        if isinstance(event.get("target_run_id"), str)
                        else None
                    ),
                    started_index=index,
                )
                runs.append(run)
                by_id[run_id] = run
                continue
            run = by_id.get(run_id)
            if run is None:
                raise ActionLogError(f"event references unknown run ID: {run_id}")
            if name == "ACTION_PLANNED":
                action_id = event.get("action_id")
                value = event.get("action")
                if not isinstance(action_id, str) or not isinstance(value, dict):
                    raise ActionLogError("invalid planned action in action log")
                run.actions.append((action_id, Action.from_dict(value)))
            elif name == "ACTION_COMPLETED":
                action_id = event.get("action_id")
                if not isinstance(action_id, str):
                    raise ActionLogError("completed action has no action ID")
                run.completed_action_ids.add(action_id)
            elif name == "RUN_COMMITTED":
                run.committed = True
        return runs

    def _active_and_unresolved_runs(self, runs: list[RunRecord]) -> list[RunRecord]:
        undone = {
            run.target_run_id
            for run in runs
            if run.mode == "UNDO" and run.committed and run.target_run_id
        }
        return [
            run
            for run in runs
            if run.mode == "APPLY" and run.run_id not in undone
        ]

    def _identity_key(self, action: Action) -> tuple[int, int] | None:
        if not action.identity:
            return None
        device = action.identity.get("device")
        inode = action.identity.get("inode")
        if isinstance(device, int) and isinstance(inode, int):
            return device, inode
        return None

    def _paths(self, run: RunRecord) -> set[str]:
        return {
            path
            for _, action in run.actions
            for path in (action.before, action.after)
            if path is not None
        }

    def _find_target(self, runs: list[RunRecord], tool: str) -> RunRecord:
        incomplete_undo = [run for run in runs if run.mode == "UNDO" and not run.committed]
        if incomplete_undo:
            raise ActionConflict(
                "the action log contains an interrupted undo run; no new undo "
                "can start until it is recovered"
            )
        candidates = [
            run
            for run in self._active_and_unresolved_runs(runs)
            if run.tool == tool
        ]
        if not candidates:
            raise NoUndoableRun(f"no active {tool} run to undo")
        return max(candidates, key=lambda run: run.started_index)

    def _later_blockers(self, runs: list[RunRecord], target: RunRecord) -> list[RunRecord]:
        target_paths = self._paths(target)
        target_identities = {
            key
            for _, action in target.actions
            if (key := self._identity_key(action)) is not None
        }
        blockers: list[RunRecord] = []
        for run in self._active_and_unresolved_runs(runs):
            if run.run_id == target.run_id or run.started_index <= target.started_index:
                continue
            identities = {
                key
                for _, action in run.actions
                if (key := self._identity_key(action)) is not None
            }
            if target_paths.intersection(self._paths(run)) or target_identities.intersection(
                identities
            ):
                blockers.append(run)
        return blockers

    def _identity_matches(self, path: Path, expected: dict[str, int | str]) -> bool:
        if path.is_symlink() or not path.is_file():
            return False
        stat = path.stat()
        if stat.st_size != expected.get("size"):
            return False
        return _sha256(path) == expected.get("sha256")

    def _execute_action(self, action: Action) -> None:
        before = _absolute_path(self.root, action.before) if action.before else None
        after = _absolute_path(self.root, action.after) if action.after else None
        if ActionOperation(action.operation).is_file:
            assert before is not None and after is not None and action.identity is not None
            if not self._identity_matches(before, action.identity):
                raise ActionConflict(f"source file is missing or changed: {action.before}")
            if os.path.lexists(after):
                raise ActionConflict(f"destination is occupied: {action.after}")
            if not after.parent.is_dir() or after.parent.is_symlink():
                raise ActionConflict(
                    f"destination parent is missing or unsafe: {after.parent}"
                )
            shutil.move(str(before), str(after))
            return
        if action.operation == ActionOperation.CREATE_DIRECTORY:
            assert after is not None
            if os.path.lexists(after):
                raise ActionConflict(f"directory destination is occupied: {action.after}")
            if not after.parent.is_dir() or after.parent.is_symlink():
                raise ActionConflict(
                    f"directory parent is missing or unsafe: {after.parent}"
                )
            after.mkdir()
            return
        assert before is not None
        if before.is_symlink() or not before.is_dir():
            raise ActionConflict(f"expected directory is missing: {action.before}")
        try:
            before.rmdir()
        except OSError as error:
            raise ActionConflict(f"directory is not empty: {action.before}") from error

    def _forward_state(self, action: Action) -> str:
        before = _absolute_path(self.root, action.before) if action.before else None
        after = _absolute_path(self.root, action.after) if action.after else None
        if ActionOperation(action.operation).is_file:
            assert before is not None and after is not None and action.identity is not None
            before_matches = self._identity_matches(before, action.identity)
            after_matches = self._identity_matches(after, action.identity)
            before_exists = os.path.lexists(before)
            after_exists = os.path.lexists(after)
            if before_matches and not after_exists:
                return "unapplied"
            if not before_exists and after_matches:
                return "applied"
            return "conflict"
        if action.operation == ActionOperation.CREATE_DIRECTORY:
            assert after is not None
            if after.is_dir() and not after.is_symlink():
                return "applied"
            if not os.path.lexists(after):
                return "unapplied"
            return "conflict"
        assert before is not None
        if not os.path.lexists(before):
            return "applied"
        if before.is_dir() and not before.is_symlink():
            return "unapplied"
        return "conflict"

    def _effective_actions(self, run: RunRecord) -> list[Action]:
        effective: list[Action] = []
        for action_id, action in run.actions:
            state = self._forward_state(action)
            if state == "conflict":
                raise ActionConflict(
                    f"filesystem state no longer matches {run.tool} run {run.run_id}"
                )
            if run.committed and action_id not in run.completed_action_ids:
                raise ActionLogError(
                    f"committed run {run.run_id} contains an incomplete action"
                )
            if run.committed and state != "applied":
                raise ActionConflict(
                    f"recorded result is missing for {run.tool} run {run.run_id}"
                )
            if state == "applied":
                effective.append(action)
        return effective

    def _snapshot(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for path in self.root.rglob("*"):
            relative = path.relative_to(self.root).as_posix()
            if path.is_symlink():
                result[relative] = "symlink"
            elif path.is_dir():
                result[relative] = "directory"
            elif path.is_file():
                result[relative] = "file"
            else:
                result[relative] = "other"
        return result

    def _simulate(self, actions: list[Action]) -> None:
        entries = self._snapshot()
        for action in actions:
            if ActionOperation(action.operation).is_file:
                assert action.before and action.after and action.identity
                if entries.get(action.before) != "file":
                    raise ActionConflict(f"expected file is missing: {action.before}")
                source = _absolute_path(self.root, action.before)
                if not self._identity_matches(source, action.identity):
                    raise ActionConflict(f"file identity changed: {action.before}")
                if action.after in entries:
                    raise ActionConflict(f"undo destination is occupied: {action.after}")
                parent = PurePosixPath(action.after).parent.as_posix()
                if parent != "." and entries.get(parent) != "directory":
                    raise ActionConflict(f"destination parent is missing: {parent}")
                del entries[action.before]
                entries[action.after] = "file"
            elif action.operation == ActionOperation.CREATE_DIRECTORY:
                assert action.after
                if action.after in entries:
                    raise ActionConflict(f"directory destination is occupied: {action.after}")
                parent = PurePosixPath(action.after).parent.as_posix()
                if parent != "." and entries.get(parent) != "directory":
                    raise ActionConflict(f"directory parent is missing: {parent}")
                entries[action.after] = "directory"
            else:
                assert action.before
                if entries.get(action.before) != "directory":
                    raise ActionConflict(f"expected directory is missing: {action.before}")
                prefix = action.before + "/"
                if any(path.startswith(prefix) for path in entries):
                    raise ActionConflict(f"directory is not empty: {action.before}")
                del entries[action.before]

    def _build_plan(self, events: list[dict[str, object]], tool: str) -> UndoPlan:
        runs = self._runs(events)
        target = self._find_target(runs, tool)
        blockers = self._later_blockers(runs, target)
        if blockers:
            summary = ", ".join(f"{run.tool} ({run.run_id})" for run in blockers)
            raise ActionConflict(
                f"cannot undo {target.tool}; later active run(s) touch the same "
                f"files or paths: {summary}"
            )
        effective = self._effective_actions(target)
        reversed_actions = [action.reversed() for action in reversed(effective)]
        self._simulate(reversed_actions)
        return UndoPlan(target=target, actions=tuple(reversed_actions))

    @contextmanager
    def transaction(self, tool: str) -> Iterator[ActionTransaction]:
        with self._locked(create=True) as handle:
            runs = self._runs(self._read(handle))
            unresolved = [
                run
                for run in self._active_and_unresolved_runs(runs)
                if not run.committed
            ]
            unresolved.extend(
                run for run in runs if run.mode == "UNDO" and not run.committed
            )
            if unresolved:
                run = unresolved[-1]
                raise ActionConflict(
                    f"unfinished {run.tool} {run.mode.lower()} run {run.run_id}; "
                    "undo or recover it before starting another operation"
                )
            transaction = ActionTransaction(self, handle, tool=tool)
            try:
                yield transaction
            except BaseException as error:
                if not transaction.committed:
                    transaction.mark_incomplete(str(error))
                raise
            else:
                if not transaction.committed:
                    transaction.mark_incomplete("transaction exited without commit")

    def plan_undo(self, tool: str) -> UndoPlan:
        with self._locked(create=False) as handle:
            return self._build_plan(self._read(handle), tool)

    def apply_undo(self, tool: str) -> UndoResult:
        if not self.path.exists():
            raise NoUndoableRun(f"no action log found in {self.root}")
        with self._locked(create=True) as handle:
            plan = self._build_plan(self._read(handle), tool)
            transaction = ActionTransaction(
                self,
                handle,
                tool=tool,
                mode="UNDO",
                target_run_id=plan.target.run_id,
            )
            try:
                for action in plan.actions:
                    transaction.perform(action)
                transaction.commit()
            except BaseException as error:
                if not transaction.committed:
                    transaction.mark_incomplete(str(error))
                raise
            return UndoResult(
                target_run_id=plan.target.run_id,
                undo_run_id=transaction.run_id,
                action_count=transaction.action_count,
            )
