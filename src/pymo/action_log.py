#!/usr/bin/env python3
"""Shared append-only action history for reversible media operations."""

from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import json
import os
import stat
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import TextIO, cast

from pymo.collection import CollectionLayout
from pymo.discovery import walk_complete, walk_entry_kind_complete

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


def _tool_value(tool: str) -> str:
    try:
        return ToolId(tool).value
    except ValueError as error:
        raise ActionLogError(f"unsupported tool: {tool}") from error


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
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stat_signature(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def file_identity(path: Path) -> dict[str, int | str]:
    if path.is_symlink() or not path.is_file():
        raise ActionConflict(f"not a regular file: {path}")
    before = path.stat()
    digest = _sha256(path)
    if path.is_symlink() or not path.is_file():
        raise ActionConflict(f"file changed while identity was calculated: {path}")
    after = path.stat()
    if _stat_signature(before) != _stat_signature(after):
        raise ActionConflict(f"file changed while identity was calculated: {path}")
    return {
        "size": after.st_size,
        "sha256": digest,
        "device": after.st_dev,
        "inode": after.st_ino,
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
            raise ActionLogError(f"unsupported operation: {self.operation}") from error
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
                or self.identity is not None
            ):
                raise ActionLogError("CREATE_DIR requires only an after path")
        elif operation is ActionOperation.REMOVE_DIRECTORY:
            if (
                not self.before
                or self.after is not None
                or self.entry_type != "directory"
                or self.identity is not None
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
        expected_keys = {"operation", "before", "after", "entry_type", "identity"}
        if set(value) != expected_keys:
            raise ActionLogError("invalid action fields in action log")
        identity_value = value.get("identity")
        identity: dict[str, int | str] | None = None
        if identity_value is not None:
            if not isinstance(identity_value, dict) or set(identity_value) != {
                "size",
                "sha256",
                "device",
                "inode",
            }:
                raise ActionLogError("invalid identity in action log")
            size = identity_value.get("size")
            sha256 = identity_value.get("sha256")
            device = identity_value.get("device")
            inode = identity_value.get("inode")
            if (
                isinstance(size, bool)
                or not isinstance(size, int)
                or size < 0
                or not isinstance(sha256, str)
                or len(sha256) != 64
                or any(character not in "0123456789abcdef" for character in sha256)
                or isinstance(device, bool)
                or not isinstance(device, int)
                or isinstance(inode, bool)
                or not isinstance(inode, int)
            ):
                raise ActionLogError("invalid identity in action log")
            identity = {
                "size": size,
                "sha256": sha256,
                "device": device,
                "inode": inode,
            }
        before_value = value.get("before")
        after_value = value.get("after")
        before = before_value if isinstance(before_value, str) else None
        after = after_value if isinstance(after_value, str) else None
        return cls(
            operation=str(value.get("operation", "")),
            before=before,
            after=after,
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
    incomplete: bool = False


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
        flags = os.O_RDWR | os.O_APPEND | os.O_CREAT if create else os.O_RDONLY
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except FileNotFoundError as error:
            raise NoUndoableRun(f"no action log found in {self.root}") from error
        except OSError as error:
            raise ActionConflict(
                f"cannot open action log safely: {self.path}"
            ) from error
        mode = "a+" if create else "r"
        with os.fdopen(descriptor, mode, encoding="utf-8", newline="") as handle:
            file_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
                raise ActionConflict(
                    f"action log is not a private regular file: {self.path}"
                )
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield cast(TextIO, handle)
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
            schema_version = (
                event.get("schema_version") if isinstance(event, dict) else None
            )
            if (
                not isinstance(event, dict)
                or isinstance(schema_version, bool)
                or schema_version != ACTION_LOG_SCHEMA_VERSION
            ):
                raise ActionLogError(
                    f"unsupported action-log record on line {line_number}"
                )
            if not isinstance(event.get("timestamp"), str):
                raise ActionLogError(
                    f"action-log record on line {line_number} has no timestamp"
                )
            events.append(event)
        return events

    @staticmethod
    def _require_event_fields(
        event: dict[str, object], required: set[str], index: int
    ) -> None:
        common = {"schema_version", "timestamp", "event", "run_id"}
        if set(event) != common | required:
            raise ActionLogError(f"action-log event {index + 1} has invalid fields")

    def _runs(self, events: list[dict[str, object]]) -> list[RunRecord]:
        runs: list[RunRecord] = []
        by_id: dict[str, RunRecord] = {}
        for index, event in enumerate(events):
            name = event.get("event")
            run_id = event.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise ActionLogError(f"action-log event {index + 1} has no run ID")
            if name == "RUN_STARTED":
                self._require_event_fields(
                    event, {"tool", "mode", "target_run_id"}, index
                )
                if run_id in by_id:
                    raise ActionLogError(f"duplicate run ID in action log: {run_id}")
                tool = event.get("tool")
                mode = event.get("mode")
                target_run_id_value = event.get("target_run_id")
                if not isinstance(tool, str) or tool not in {
                    member.value for member in ToolId
                }:
                    raise ActionLogError(f"invalid tool in action log: {tool!r}")
                if mode not in {"APPLY", "UNDO"}:
                    raise ActionLogError(f"invalid run mode in action log: {mode!r}")
                if mode == "APPLY" and target_run_id_value is not None:
                    raise ActionLogError("apply run cannot name an undo target")
                if mode == "UNDO" and (
                    not isinstance(target_run_id_value, str) or not target_run_id_value
                ):
                    raise ActionLogError("undo run requires a target run ID")
                target_run_id = (
                    target_run_id_value
                    if isinstance(target_run_id_value, str)
                    else None
                )
                run = RunRecord(
                    run_id=run_id,
                    tool=tool,
                    mode=mode,
                    target_run_id=target_run_id,
                    started_index=index,
                )
                runs.append(run)
                by_id[run_id] = run
                continue
            current_run = by_id.get(run_id)
            if current_run is None:
                raise ActionLogError(f"event references unknown run ID: {run_id}")
            if current_run.committed or current_run.incomplete:
                raise ActionLogError(
                    f"event follows terminal state for run ID: {run_id}"
                )
            if name == "ACTION_PLANNED":
                self._require_event_fields(event, {"action_id", "action"}, index)
                action_id = event.get("action_id")
                value = event.get("action")
                if (
                    not isinstance(action_id, str)
                    or not action_id
                    or not isinstance(value, dict)
                ):
                    raise ActionLogError("invalid planned action in action log")
                known_action_ids = {known_id for known_id, _ in current_run.actions}
                if action_id in known_action_ids:
                    raise ActionLogError(
                        f"duplicate action ID in run {run_id}: {action_id}"
                    )
                current_run.actions.append((action_id, Action.from_dict(value)))
            elif name == "ACTION_COMPLETED":
                self._require_event_fields(event, {"action_id"}, index)
                action_id = event.get("action_id")
                if not isinstance(action_id, str) or not action_id:
                    raise ActionLogError("completed action has no action ID")
                known_action_ids = {known_id for known_id, _ in current_run.actions}
                if action_id not in known_action_ids:
                    raise ActionLogError(
                        f"completed action was not planned in run {run_id}: {action_id}"
                    )
                if action_id in current_run.completed_action_ids:
                    raise ActionLogError(
                        f"action completed more than once in run {run_id}: {action_id}"
                    )
                current_run.completed_action_ids.add(action_id)
            elif name == "RUN_COMMITTED":
                self._require_event_fields(
                    event, {"action_count", "target_run_id"}, index
                )
                action_count = event.get("action_count")
                if (
                    isinstance(action_count, bool)
                    or not isinstance(action_count, int)
                    or action_count != len(current_run.actions)
                    or action_count != len(current_run.completed_action_ids)
                ):
                    raise ActionLogError(
                        f"committed action count is inconsistent for run {run_id}"
                    )
                if event.get("target_run_id") != current_run.target_run_id:
                    raise ActionLogError(
                        f"commit target is inconsistent for run {run_id}"
                    )
                current_run.committed = True
            elif name == "RUN_INCOMPLETE":
                self._require_event_fields(event, {"reason"}, index)
                if not isinstance(event.get("reason"), str):
                    raise ActionLogError(f"invalid incomplete reason for run {run_id}")
                current_run.incomplete = True
            else:
                raise ActionLogError(f"unknown action-log event: {name!r}")

        committed_undo_targets: set[str] = set()
        for run in runs:
            if run.mode != "UNDO":
                continue
            target = by_id.get(run.target_run_id or "")
            if (
                target is None
                or target.mode != "APPLY"
                or target.tool != run.tool
                or target.started_index >= run.started_index
            ):
                raise ActionLogError(f"invalid undo target for run {run.run_id}")
            if run.committed:
                if target.run_id in committed_undo_targets:
                    raise ActionLogError(
                        f"run was undone more than once: {target.run_id}"
                    )
                committed_undo_targets.add(target.run_id)
        return runs

    def _active_and_unresolved_runs(self, runs: list[RunRecord]) -> list[RunRecord]:
        undone = {
            run.target_run_id
            for run in runs
            if run.mode == "UNDO" and run.committed and run.target_run_id
        }
        return [run for run in runs if run.mode == "APPLY" and run.run_id not in undone]

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
        incomplete_undo = [
            run for run in runs if run.mode == "UNDO" and not run.committed
        ]
        if incomplete_undo:
            raise ActionConflict(
                "the action log contains an interrupted undo run; no new undo "
                "can start until it is recovered"
            )
        candidates = [
            run for run in self._active_and_unresolved_runs(runs) if run.tool == tool
        ]
        if not candidates:
            raise NoUndoableRun(f"no active {tool} run to undo")
        return max(candidates, key=lambda run: run.started_index)

    def _later_blockers(
        self, runs: list[RunRecord], target: RunRecord
    ) -> list[RunRecord]:
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
            if target_paths.intersection(
                self._paths(run)
            ) or target_identities.intersection(identities):
                blockers.append(run)
        return blockers

    def _identity_matches(self, path: Path, expected: dict[str, int | str]) -> bool:
        if path.is_symlink() or not path.is_file():
            return False
        before = path.stat()
        if before.st_size != expected.get("size"):
            return False
        digest = _sha256(path)
        if path.is_symlink() or not path.is_file():
            return False
        after = path.stat()
        return _stat_signature(before) == _stat_signature(
            after
        ) and digest == expected.get("sha256")

    def _validate_parent_chain(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.root)
        except ValueError as error:
            raise ActionConflict(f"path escaped the collection: {path}") from error
        current = self.root
        for part in relative.parts[:-1]:
            current /= part
            if current.is_symlink() or not current.is_dir():
                raise ActionConflict(f"path parent is missing or unsafe: {current}")

    @contextmanager
    def _opened_parent(self, path: Path) -> Iterator[tuple[int, str]]:
        try:
            relative = path.relative_to(self.root)
        except ValueError as error:
            raise ActionConflict(f"path escaped the collection: {path}") from error
        flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(self.root, flags)
        try:
            for part in relative.parts[:-1]:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            yield descriptor, relative.name
        except OSError as error:
            raise ActionConflict(f"path parent became unsafe: {path.parent}") from error
        finally:
            os.close(descriptor)

    def _atomic_rename_without_overwrite(self, before: Path, after: Path) -> None:
        library = ctypes.CDLL(None, use_errno=True)
        with (
            self._opened_parent(before) as (
                before_parent,
                before_name,
            ),
            self._opened_parent(after) as (after_parent, after_name),
        ):
            if sys.platform == "darwin":
                rename = library.renameatx_np
                rename.argtypes = [
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_uint,
                ]
                rename.restype = ctypes.c_int
                # RENAME_EXCL provides atomic no-replace behavior. NOFOLLOW_ANY
                # also rejects symbolic links at any component on macOS.
                result = rename(
                    before_parent,
                    os.fsencode(before_name),
                    after_parent,
                    os.fsencode(after_name),
                    0x04 | 0x10,
                )
            elif sys.platform.startswith("linux"):
                try:
                    rename = library.renameat2
                except AttributeError as error:
                    raise ActionConflict(
                        "this Linux runtime cannot perform an atomic no-replace move"
                    ) from error
                rename.argtypes = [
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_uint,
                ]
                rename.restype = ctypes.c_int
                # Parent descriptors are opened without following links;
                # RENAME_NOREPLACE supplies atomic collision refusal.
                result = rename(
                    before_parent,
                    os.fsencode(before_name),
                    after_parent,
                    os.fsencode(after_name),
                    0x01,
                )
            else:
                raise ActionConflict(
                    "atomic no-replace moves are supported only on macOS and Linux"
                )
        if result != 0:
            error_number = ctypes.get_errno()
            if error_number == errno.EEXIST:
                raise ActionConflict(f"destination is occupied: {after}")
            if error_number == errno.EXDEV:
                raise ActionConflict(
                    "cross-filesystem moves are refused because they cannot be "
                    "atomic and collision-safe"
                )
            if error_number in {errno.ELOOP, errno.ENOTDIR}:
                raise ActionConflict("move path became unsafe during execution")
            raise OSError(error_number, os.strerror(error_number), str(after))

    def _move_file_without_overwrite(
        self, before: Path, after: Path, identity: dict[str, int | str]
    ) -> None:
        self._atomic_rename_without_overwrite(before, after)
        if not self._identity_matches(after, identity):
            try:
                if not os.path.lexists(before):
                    self._atomic_rename_without_overwrite(after, before)
            except (ActionConflict, OSError):
                pass
            raise ActionConflict("moved file failed identity verification")

    def _execute_action(self, action: Action) -> None:
        before = _absolute_path(self.root, action.before) if action.before else None
        after = _absolute_path(self.root, action.after) if action.after else None
        if ActionOperation(action.operation).is_file:
            assert (
                before is not None and after is not None and action.identity is not None
            )
            self._validate_parent_chain(before)
            self._validate_parent_chain(after)
            if not self._identity_matches(before, action.identity):
                raise ActionConflict(
                    f"source file is missing or changed: {action.before}"
                )
            if os.path.lexists(after):
                raise ActionConflict(f"destination is occupied: {action.after}")
            self._move_file_without_overwrite(before, after, action.identity)
            return
        if action.operation == ActionOperation.CREATE_DIRECTORY:
            assert after is not None
            self._validate_parent_chain(after)
            if os.path.lexists(after):
                raise ActionConflict(
                    f"directory destination is occupied: {action.after}"
                )
            if not after.parent.is_dir() or after.parent.is_symlink():
                raise ActionConflict(
                    f"directory parent is missing or unsafe: {after.parent}"
                )
            after.mkdir()
            return
        assert before is not None
        self._validate_parent_chain(before)
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
            assert (
                before is not None and after is not None and action.identity is not None
            )
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
        for current, directory_names, file_names in walk_complete(self.root):
            current_path = Path(current)
            for name in directory_names:
                path = current_path / name
                relative = path.relative_to(self.root).as_posix()
                result[relative] = walk_entry_kind_complete(
                    path, listed_as_directory=True
                )
            for name in file_names:
                path = current_path / name
                relative = path.relative_to(self.root).as_posix()
                result[relative] = walk_entry_kind_complete(
                    path, listed_as_directory=False
                )
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
                    raise ActionConflict(
                        f"undo destination is occupied: {action.after}"
                    )
                parent = PurePosixPath(action.after).parent.as_posix()
                if parent != "." and entries.get(parent) != "directory":
                    raise ActionConflict(f"destination parent is missing: {parent}")
                del entries[action.before]
                entries[action.after] = "file"
            elif action.operation == ActionOperation.CREATE_DIRECTORY:
                assert action.after
                if action.after in entries:
                    raise ActionConflict(
                        f"directory destination is occupied: {action.after}"
                    )
                parent = PurePosixPath(action.after).parent.as_posix()
                if parent != "." and entries.get(parent) != "directory":
                    raise ActionConflict(f"directory parent is missing: {parent}")
                entries[action.after] = "directory"
            else:
                assert action.before
                if entries.get(action.before) != "directory":
                    raise ActionConflict(
                        f"expected directory is missing: {action.before}"
                    )
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
        tool = _tool_value(tool)
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
        tool = _tool_value(tool)
        with self._locked(create=False) as handle:
            return self._build_plan(self._read(handle), tool)

    def apply_undo(self, tool: str) -> UndoResult:
        tool = _tool_value(tool)
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
