"""Atomic same-filesystem retention of one collection's complete ``dups`` tree.

The external destination is deliberately supplied for every operation. Its
path-private digest is persisted in the portable collection journal beside the
exact tree manifest and filesystem identity.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import stat
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn, TextIO

from pymo.action_log import (
    Action,
    ActionConflict,
    ActionLog,
    ActionOperation,
    ActionTransaction,
    RunRecord,
    ToolId,
)


class ManagedQuarantineError(ActionConflict):
    """A managed quarantine boundary could not be proved safe."""


@dataclass(frozen=True)
class TreeManifest:
    """Path-private exact evidence for one descriptor-pinned directory tree."""

    sha256: str
    file_count: int
    directory_count: int
    total_bytes: int
    device: int
    inode: int

    @property
    def journal_identity(self) -> dict[str, int | str]:
        return {
            "size": self.total_bytes,
            "sha256": self.sha256,
            "device": self.device,
            "inode": self.inode,
        }


@dataclass(frozen=True)
class QuarantinePlan:
    """A dry-run result that must be revalidated before apply."""

    collection_root: Path
    target: Path
    manifest: TreeManifest
    target_parent_device: int
    target_parent_inode: int


@dataclass(frozen=True)
class QuarantineUndoPlan:
    """An exact external-target undo plan."""

    collection_root: Path
    target: Path
    target_run_id: str
    manifest: TreeManifest
    target_parent_device: int
    target_parent_inode: int


@dataclass(frozen=True)
class QuarantineResult:
    """Aggregate, path-private result for a completed journaled operation."""

    run_id: str
    direction: Literal["quarantine", "restore"]
    file_count: int
    directory_count: int
    total_bytes: int
    manifest_sha256: str
    reconciled: bool = False
    disposition_complete: bool = True


@dataclass(frozen=True)
class _PinnedDirectory:
    path: Path
    descriptor: int
    identity: tuple[int, int]
    ancestry: tuple[tuple[int, int], ...]


def _private_error(message: str, error: BaseException | None = None) -> NoReturn:
    if error is None:
        raise ManagedQuarantineError(message)
    raise ManagedQuarantineError(message) from error


def _normalized_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def destination_binding_sha256(path: Path) -> str:
    """Return the path-private exact binding for one normalized destination."""

    return hashlib.sha256(os.fsencode(_normalized_absolute(path))).hexdigest()


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )


def _identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _same_entry(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        first.st_dev,
        first.st_ino,
        stat.S_IFMT(first.st_mode),
    ) == (
        second.st_dev,
        second.st_ino,
        stat.S_IFMT(second.st_mode),
    )


@contextmanager
def _open_directory_path(path: Path) -> Iterator[_PinnedDirectory]:
    normalized = _normalized_absolute(path)
    descriptor: int | None = None
    ancestry: list[tuple[int, int]] = []
    try:
        descriptor = os.open(os.sep, _directory_flags())
        root_state = os.fstat(descriptor)
        ancestry.append(_identity(root_state))
        for part in normalized.parts[1:]:
            try:
                listed = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
                opened = os.open(part, _directory_flags(), dir_fd=descriptor)
            except OSError as error:
                _private_error(
                    "required directory ancestry is missing or unsafe", error
                )
            opened_state = os.fstat(opened)
            if not stat.S_ISDIR(listed.st_mode) or not _same_entry(
                listed, opened_state
            ):
                os.close(opened)
                _private_error("required directory ancestry is missing or unsafe")
            os.close(descriptor)
            descriptor = opened
            ancestry.append(_identity(opened_state))
        assert descriptor is not None
        final_state = os.fstat(descriptor)
        if not stat.S_ISDIR(final_state.st_mode):
            _private_error("required directory is not a real directory")
        yield _PinnedDirectory(
            normalized,
            descriptor,
            _identity(final_state),
            tuple(ancestry),
        )
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _require_directory_path_identity(path: Path, expected: tuple[int, int]) -> None:
    try:
        with _open_directory_path(path) as reopened:
            if reopened.identity != expected:
                _private_error("required directory identity changed")
    except ManagedQuarantineError:
        raise
    except OSError as error:
        _private_error("required directory identity changed", error)


def _leaf_state(parent_descriptor: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        _private_error("directory endpoint could not be inspected", error)


def _encode_field(digest: object, value: bytes) -> None:
    assert hasattr(digest, "update")
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _metadata_bytes(value: os.stat_result, *, directory: bool) -> bytes:
    fields = [
        value.st_dev,
        value.st_ino,
        stat.S_IMODE(value.st_mode),
        value.st_uid,
        value.st_gid,
        value.st_mtime_ns,
    ]
    if not directory:
        fields.extend((value.st_size, value.st_ctime_ns))
    return ":".join(str(field) for field in fields).encode("ascii")


def _stable_directory_signature(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _stable_file_signature(value: os.stat_result) -> tuple[int, ...]:
    return (*_stable_directory_signature(value), value.st_nlink)


def _hash_file(descriptor: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while chunk := os.pread(descriptor, 1024 * 1024, offset):
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def _namespace_snapshot(
    descriptor: int,
) -> tuple[tuple[bytes, str, tuple[int, ...]], ...]:
    """Capture every entry's no-follow state without reading file content."""

    records: list[tuple[bytes, str, tuple[int, ...]]] = []
    visited: set[tuple[int, int]] = set()

    def inspect(current_descriptor: int, relative: bytes) -> None:
        try:
            before = os.fstat(current_descriptor)
            names = sorted(os.listdir(current_descriptor), key=os.fsencode)
        except OSError as error:
            _private_error("review tree could not be enumerated completely", error)
        if not stat.S_ISDIR(before.st_mode) or _identity(before) in visited:
            _private_error("review tree contains an unsafe directory")
        visited.add(_identity(before))
        records.append((relative, "directory", _stable_directory_signature(before)))
        encoded_names = tuple(os.fsencode(name) for name in names)
        for name, encoded_name in zip(names, encoded_names, strict=True):
            child_relative = (
                encoded_name if not relative else relative + b"/" + encoded_name
            )
            try:
                listed = os.stat(name, dir_fd=current_descriptor, follow_symlinks=False)
            except OSError as error:
                _private_error("review tree entry could not be inspected", error)
            if stat.S_ISLNK(listed.st_mode):
                _private_error("review tree contains a symbolic link")
            if stat.S_ISDIR(listed.st_mode):
                child_descriptor: int | None = None
                try:
                    child_descriptor = os.open(
                        name, _directory_flags(), dir_fd=current_descriptor
                    )
                    opened = os.fstat(child_descriptor)
                    if not _same_entry(listed, opened):
                        _private_error("review tree changed during inspection")
                    inspect(child_descriptor, child_relative)
                except ManagedQuarantineError:
                    raise
                except OSError as error:
                    _private_error("review tree directory became unsafe", error)
                finally:
                    if child_descriptor is not None:
                        os.close(child_descriptor)
                continue
            if not stat.S_ISREG(listed.st_mode) or listed.st_nlink != 1:
                _private_error("review tree contains an unsafe non-regular entry")
            records.append((child_relative, "file", _stable_file_signature(listed)))
        try:
            final_names = tuple(
                os.fsencode(name)
                for name in sorted(os.listdir(current_descriptor), key=os.fsencode)
            )
            after = os.fstat(current_descriptor)
        except OSError as error:
            _private_error("review tree could not be revalidated", error)
        if encoded_names != final_names or _stable_directory_signature(
            before
        ) != _stable_directory_signature(after):
            _private_error("review tree changed during inspection")

    inspect(descriptor, b"")
    return tuple(sorted(records, key=lambda record: (record[0], record[1])))


def _manifest_from_open_directory(descriptor: int) -> TreeManifest:
    initial_namespace = _namespace_snapshot(descriptor)
    digest = hashlib.sha256()
    file_count = 0
    directory_count = 0
    total_bytes = 0
    visited: set[tuple[int, int]] = set()

    def inspect(current_descriptor: int, relative: bytes) -> None:
        nonlocal file_count, directory_count, total_bytes
        try:
            before = os.fstat(current_descriptor)
        except OSError as error:
            _private_error("review tree could not be inspected completely", error)
        if not stat.S_ISDIR(before.st_mode):
            _private_error("review tree contains an unsafe directory")
        directory_identity = _identity(before)
        if directory_identity in visited:
            _private_error("review tree contains an aliased directory")
        visited.add(directory_identity)
        directory_count += 1
        digest.update(b"D")
        _encode_field(digest, relative)
        _encode_field(digest, _metadata_bytes(before, directory=True))
        try:
            names = sorted(os.listdir(current_descriptor), key=os.fsencode)
        except OSError as error:
            _private_error("review tree could not be enumerated completely", error)
        encoded_names = tuple(os.fsencode(name) for name in names)
        for name, encoded_name in zip(names, encoded_names, strict=True):
            child_relative = (
                encoded_name if not relative else relative + b"/" + encoded_name
            )
            try:
                listed = os.stat(name, dir_fd=current_descriptor, follow_symlinks=False)
            except OSError as error:
                _private_error("review tree entry could not be inspected", error)
            if stat.S_ISLNK(listed.st_mode):
                _private_error("review tree contains a symbolic link")
            if stat.S_ISDIR(listed.st_mode):
                child_descriptor: int | None = None
                try:
                    child_descriptor = os.open(
                        name, _directory_flags(), dir_fd=current_descriptor
                    )
                    opened = os.fstat(child_descriptor)
                    if not _same_entry(listed, opened):
                        _private_error("review tree changed during inspection")
                    inspect(child_descriptor, child_relative)
                    current = os.stat(
                        name, dir_fd=current_descriptor, follow_symlinks=False
                    )
                    if not _same_entry(opened, current):
                        _private_error("review tree changed during inspection")
                except ManagedQuarantineError:
                    raise
                except OSError as error:
                    _private_error("review tree directory became unsafe", error)
                finally:
                    if child_descriptor is not None:
                        os.close(child_descriptor)
                continue
            if not stat.S_ISREG(listed.st_mode) or listed.st_nlink != 1:
                _private_error("review tree contains an unsafe non-regular entry")
            file_descriptor: int | None = None
            try:
                file_descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_NONBLOCK", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=current_descriptor,
                )
                opened = os.fstat(file_descriptor)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1
                    or _stable_file_signature(opened) != _stable_file_signature(listed)
                ):
                    _private_error("review tree file became unsafe")
                content_sha256 = _hash_file(file_descriptor)
                final = os.fstat(file_descriptor)
                current = os.stat(
                    name, dir_fd=current_descriptor, follow_symlinks=False
                )
                if _stable_file_signature(final) != _stable_file_signature(
                    opened
                ) or _stable_file_signature(current) != _stable_file_signature(opened):
                    _private_error("review tree changed during inspection")
            except ManagedQuarantineError:
                raise
            except OSError as error:
                _private_error("review tree file could not be read", error)
            finally:
                if file_descriptor is not None:
                    os.close(file_descriptor)
            file_count += 1
            total_bytes += opened.st_size
            digest.update(b"F")
            _encode_field(digest, child_relative)
            _encode_field(digest, _metadata_bytes(opened, directory=False))
            _encode_field(digest, content_sha256.encode("ascii"))
        try:
            final_names = tuple(
                os.fsencode(name)
                for name in sorted(os.listdir(current_descriptor), key=os.fsencode)
            )
            after = os.fstat(current_descriptor)
        except OSError as error:
            _private_error("review tree could not be revalidated", error)
        if encoded_names != final_names or _stable_directory_signature(
            before
        ) != _stable_directory_signature(after):
            _private_error("review tree changed during inspection")

    inspect(descriptor, b"")
    if _namespace_snapshot(descriptor) != initial_namespace:
        _private_error("review tree changed during inspection")
    root = os.fstat(descriptor)
    return TreeManifest(
        sha256=digest.hexdigest(),
        file_count=file_count,
        directory_count=directory_count,
        total_bytes=total_bytes,
        device=root.st_dev,
        inode=root.st_ino,
    )


def _manifest_at(parent_descriptor: int, name: str) -> TreeManifest:
    descriptor: int | None = None
    try:
        listed = _leaf_state(parent_descriptor, name)
        if listed is None or not stat.S_ISDIR(listed.st_mode):
            _private_error("required review tree is missing or unsafe")
        assert listed is not None
        descriptor = os.open(name, _directory_flags(), dir_fd=parent_descriptor)
        opened = os.fstat(descriptor)
        if not _same_entry(listed, opened):
            _private_error("review tree changed during inspection")
        manifest = _manifest_from_open_directory(descriptor)
        current = _leaf_state(parent_descriptor, name)
        if current is None or not _same_entry(opened, current):
            _private_error("review tree changed during inspection")
        return manifest
    except ManagedQuarantineError:
        raise
    except OSError as error:
        _private_error("required review tree is missing or unsafe", error)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _target_parts(target: Path) -> tuple[Path, str]:
    normalized = _normalized_absolute(target)
    if normalized.parent == normalized or normalized.name in {"", ".", ".."}:
        _private_error("external quarantine target is invalid")
    return normalized.parent, normalized.name


def _require_disjoint_same_filesystem(
    collection: _PinnedDirectory,
    source: TreeManifest,
    target_parent: _PinnedDirectory,
) -> None:
    if (
        collection.identity in target_parent.ancestry
        or (
            source.device,
            source.inode,
        )
        in target_parent.ancestry
    ):
        _private_error("external quarantine target must be outside the collection")
    if source.device != target_parent.identity[0]:
        _private_error("cross-filesystem quarantine is not supported")


def _atomic_rename_without_replace(
    source_parent: int,
    source_name: str,
    target_parent: int,
    target_name: str,
) -> None:
    library = ctypes.CDLL(None, use_errno=True)
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
        result = rename(
            source_parent,
            os.fsencode(source_name),
            target_parent,
            os.fsencode(target_name),
            0x04 | 0x10,
        )
    elif sys.platform.startswith("linux"):
        try:
            rename = library.renameat2
        except AttributeError as error:
            _private_error("atomic no-replace directory moves are unavailable", error)
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(
            source_parent,
            os.fsencode(source_name),
            target_parent,
            os.fsencode(target_name),
            0x01,
        )
    else:
        _private_error("atomic no-replace directory moves require macOS or Linux")
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        _private_error("external quarantine destination is occupied")
    if error_number == errno.EXDEV:
        _private_error("cross-filesystem quarantine is not supported")
    if error_number in {errno.ELOOP, errno.ENOTDIR}:
        _private_error("quarantine endpoint became unsafe")
    _private_error(
        "atomic quarantine movement failed",
        OSError(error_number, os.strerror(error_number)),
    )


def _same_manifest(observed: TreeManifest, expected: TreeManifest) -> bool:
    return (
        observed.sha256,
        observed.total_bytes,
        observed.device,
        observed.inode,
    ) == (
        expected.sha256,
        expected.total_bytes,
        expected.device,
        expected.inode,
    )


def _action_destination(action: Action) -> tuple[str, int, int]:
    if action.after is None:
        _private_error("managed quarantine journal action is inconsistent")
    parts = action.after.split(":")
    if len(parts) != 4 or parts[0] != "external":
        _private_error("managed quarantine journal action is inconsistent")
    try:
        return parts[1], int(parts[2]), int(parts[3])
    except ValueError as error:  # pragma: no cover - Action owns strict parsing.
        _private_error("managed quarantine journal action is inconsistent", error)


def _manifest_from_action(
    action: Action,
    target: Path | None = None,
    target_parent_identity: tuple[int, int] | None = None,
) -> TreeManifest:
    if (
        action.operation != ActionOperation.QUARANTINE_TREE
        or action.before != "dups"
        or action.after is None
        or action.entry_type != "directory"
        or action.identity is None
    ):
        _private_error("managed quarantine journal action is inconsistent")
    destination_sha256, destination_device, destination_inode = _action_destination(
        action
    )
    if target is not None and destination_sha256 != destination_binding_sha256(target):
        _private_error("explicit quarantine target does not match the journal")
    if (
        target_parent_identity is not None
        and (
            destination_device,
            destination_inode,
        )
        != target_parent_identity
    ):
        _private_error("quarantine destination identity changed")
    identity = action.identity
    assert identity is not None
    size = identity.get("size")
    digest = identity.get("sha256")
    device = identity.get("device")
    inode = identity.get("inode")
    if (
        isinstance(size, bool)
        or not isinstance(size, int)
        or not isinstance(digest, str)
        or isinstance(device, bool)
        or not isinstance(device, int)
        or isinstance(inode, bool)
        or not isinstance(inode, int)
    ):
        _private_error("managed quarantine journal identity is inconsistent")
    return TreeManifest(digest, 0, 0, size, device, inode)


def _action_for_manifest(
    manifest: TreeManifest,
    target: Path,
    target_parent_identity: tuple[int, int],
) -> Action:
    return Action(
        operation=ActionOperation.QUARANTINE_TREE,
        before="dups",
        after=(
            "external:"
            + destination_binding_sha256(target)
            + f":{target_parent_identity[0]}:{target_parent_identity[1]}"
        ),
        entry_type="directory",
        identity=manifest.journal_identity,
    )


def _require_target_absent(parent_descriptor: int, name: str) -> None:
    if _leaf_state(parent_descriptor, name) is not None:
        _private_error("external quarantine destination is occupied")


def _inspect_forward(collection_root: Path, target: Path) -> QuarantinePlan:
    target_parent_path, target_name = _target_parts(target)
    with (
        _open_directory_path(collection_root) as collection,
        _open_directory_path(target_parent_path) as target_parent,
    ):
        manifest = _manifest_at(collection.descriptor, "dups")
        _require_target_absent(target_parent.descriptor, target_name)
        _require_disjoint_same_filesystem(collection, manifest, target_parent)
        _require_directory_path_identity(collection.path, collection.identity)
        _require_directory_path_identity(target_parent.path, target_parent.identity)
    return QuarantinePlan(
        collection.path,
        target_parent.path / target_name,
        manifest,
        target_parent.identity[0],
        target_parent.identity[1],
    )


def plan_managed_quarantine(collection_root: Path, target: Path) -> QuarantinePlan:
    """Build a zero-write plan for moving the complete ``dups`` tree."""

    return _inspect_forward(collection_root, target)


def _unresolved_runs(log: ActionLog, runs: list[RunRecord]) -> list[RunRecord]:
    unresolved = [
        run for run in log._active_and_unresolved_runs(runs) if not run.committed
    ]
    unresolved.extend(run for run in runs if run.mode == "UNDO" and not run.committed)
    return unresolved


def _require_no_unresolved(log: ActionLog, runs: list[RunRecord]) -> None:
    if _unresolved_runs(log, runs):
        _private_error("the action journal contains an interrupted operation")


def _append_completion(
    log: ActionLog, handle: TextIO, run: RunRecord, action_id: str
) -> None:
    log._append(
        handle,
        {
            "event": "ACTION_COMPLETED",
            "run_id": run.run_id,
            "action_id": action_id,
        },
    )


def _append_commit(log: ActionLog, handle: TextIO, run: RunRecord, count: int) -> None:
    log._append(
        handle,
        {
            "event": "RUN_COMMITTED",
            "run_id": run.run_id,
            "action_count": count,
            "target_run_id": run.target_run_id,
        },
    )


def _perform_move_and_verify(
    collection_root: Path,
    target: Path,
    expected: TreeManifest,
    expected_target_parent_identity: tuple[int, int],
    *,
    restore: bool,
) -> TreeManifest:
    target_parent_path, target_name = _target_parts(target)
    with (
        _open_directory_path(collection_root) as collection,
        _open_directory_path(target_parent_path) as target_parent,
    ):
        if target_parent.identity != expected_target_parent_identity:
            _private_error("quarantine destination identity changed after planning")
        if restore:
            _require_target_absent(collection.descriptor, "dups")
            observed = _manifest_at(target_parent.descriptor, target_name)
        else:
            _require_target_absent(target_parent.descriptor, target_name)
            observed = _manifest_at(collection.descriptor, "dups")
        if not _same_manifest(observed, expected):
            _private_error("review tree no longer matches its planned manifest")
        _require_disjoint_same_filesystem(collection, observed, target_parent)
        _require_directory_path_identity(collection.path, collection.identity)
        _require_directory_path_identity(target_parent.path, target_parent.identity)
        if restore:
            _atomic_rename_without_replace(
                target_parent.descriptor,
                target_name,
                collection.descriptor,
                "dups",
            )
        else:
            _atomic_rename_without_replace(
                collection.descriptor,
                "dups",
                target_parent.descriptor,
                target_name,
            )
        os.fsync(collection.descriptor)
        if target_parent.identity != collection.identity:
            os.fsync(target_parent.descriptor)
        if restore:
            _require_target_absent(target_parent.descriptor, target_name)
            verified = _manifest_at(collection.descriptor, "dups")
        else:
            _require_target_absent(collection.descriptor, "dups")
            verified = _manifest_at(target_parent.descriptor, target_name)
        if not _same_manifest(verified, expected):
            _private_error("moved review tree failed exact post-move verification")
        _require_directory_path_identity(collection.path, collection.identity)
        _require_directory_path_identity(target_parent.path, target_parent.identity)
        return verified


def apply_managed_quarantine(plan: QuarantinePlan) -> QuarantineResult:
    """Revalidate and atomically apply one dry-run quarantine plan."""

    preflight = _inspect_forward(plan.collection_root, plan.target)
    if preflight != plan:
        _private_error("review tree or quarantine endpoint changed after planning")
    log = ActionLog(preflight.collection_root)
    with log._locked(create=True) as handle:
        runs = log._runs(log._read(handle))
        _require_no_unresolved(log, runs)
        refreshed = _inspect_forward(plan.collection_root, plan.target)
        if refreshed != plan:
            _private_error("review tree or quarantine endpoint changed after planning")
        transaction = ActionTransaction(
            log, handle, tool=ToolId.MANAGED_QUARANTINE.value
        )
        target_parent_identity = (
            plan.target_parent_device,
            plan.target_parent_inode,
        )
        action_id = transaction.plan(
            _action_for_manifest(plan.manifest, plan.target, target_parent_identity)
        )
        verified = _perform_move_and_verify(
            plan.collection_root,
            plan.target,
            plan.manifest,
            target_parent_identity,
            restore=False,
        )
        transaction.complete(action_id)
        transaction.commit()
    return QuarantineResult(
        transaction.run_id,
        "quarantine",
        verified.file_count,
        verified.directory_count,
        verified.total_bytes,
        verified.sha256,
    )


def _quarantine_action(run: RunRecord) -> tuple[str, Action]:
    if len(run.actions) != 1:
        _private_error("managed quarantine journal run is inconsistent")
    action_id, action = run.actions[0]
    return action_id, action


def _undo_target(log: ActionLog, runs: list[RunRecord]) -> RunRecord:
    if any(run.mode == "UNDO" and not run.committed for run in runs):
        _private_error("the action journal contains an interrupted undo")
    candidates = [
        run
        for run in log._active_and_unresolved_runs(runs)
        if run.tool == ToolId.MANAGED_QUARANTINE and run.actions
    ]
    if not candidates:
        _private_error("no managed quarantine run is available to undo")
    target = max(candidates, key=lambda run: run.started_index)
    if log._later_blockers(runs, target):
        _private_error("a later active operation blocks managed quarantine undo")
    return target


def _inspect_undo_locked(
    log: ActionLog,
    runs: list[RunRecord],
    collection_root: Path,
    target: Path,
) -> QuarantineUndoPlan:
    target_run = _undo_target(log, runs)
    _, action = _quarantine_action(target_run)
    expected = _manifest_from_action(action, target)
    target_parent_path, target_name = _target_parts(target)
    with (
        _open_directory_path(collection_root) as collection,
        _open_directory_path(target_parent_path) as target_parent,
    ):
        _require_target_absent(collection.descriptor, "dups")
        observed = _manifest_at(target_parent.descriptor, target_name)
        if not _same_manifest(observed, expected):
            _private_error("explicit quarantine target does not match the journal")
        _require_disjoint_same_filesystem(collection, observed, target_parent)
        _require_directory_path_identity(collection.path, collection.identity)
        _require_directory_path_identity(target_parent.path, target_parent.identity)
    return QuarantineUndoPlan(
        collection.path,
        target_parent.path / target_name,
        target_run.run_id,
        observed,
        target_parent.identity[0],
        target_parent.identity[1],
    )


def plan_managed_quarantine_undo(
    collection_root: Path, target: Path
) -> QuarantineUndoPlan:
    """Build a zero-write exact undo plan for an explicitly named target."""

    log = ActionLog(collection_root)
    with log._locked(create=False) as handle:
        runs = log._runs(log._read(handle))
        return _inspect_undo_locked(log, runs, collection_root, target)


def apply_managed_quarantine_undo(plan: QuarantineUndoPlan) -> QuarantineResult:
    """Revalidate and atomically restore an explicitly named quarantine tree."""

    log = ActionLog(plan.collection_root)
    with log._locked(create=True) as handle:
        runs = log._runs(log._read(handle))
        refreshed = _inspect_undo_locked(log, runs, plan.collection_root, plan.target)
        if refreshed != plan:
            _private_error("review tree or restoration endpoint changed after planning")
        transaction = ActionTransaction(
            log,
            handle,
            tool=ToolId.MANAGED_QUARANTINE.value,
            mode="UNDO",
            target_run_id=plan.target_run_id,
        )
        target_parent_identity = (
            plan.target_parent_device,
            plan.target_parent_inode,
        )
        action_id = transaction.plan(
            _action_for_manifest(plan.manifest, plan.target, target_parent_identity)
        )
        verified = _perform_move_and_verify(
            plan.collection_root,
            plan.target,
            plan.manifest,
            target_parent_identity,
            restore=True,
        )
        transaction.complete(action_id)
        transaction.commit()
    return QuarantineResult(
        transaction.run_id,
        "restore",
        verified.file_count,
        verified.directory_count,
        verified.total_bytes,
        verified.sha256,
    )


def _expected_state(
    collection_root: Path,
    target: Path,
    expected: TreeManifest,
    action: Action,
    *,
    restore: bool,
) -> tuple[Literal["pending", "complete"], TreeManifest]:
    target_parent_path, target_name = _target_parts(target)
    with (
        _open_directory_path(collection_root) as collection,
        _open_directory_path(target_parent_path) as target_parent,
    ):
        _manifest_from_action(action, target, target_parent.identity)
        source_state = _leaf_state(collection.descriptor, "dups")
        target_state = _leaf_state(target_parent.descriptor, target_name)
        if source_state is not None and target_state is None:
            observed = _manifest_at(collection.descriptor, "dups")
            if not _same_manifest(observed, expected):
                _private_error("review tree changed during interrupted operation")
            state: Literal["pending", "complete"] = "complete" if restore else "pending"
        elif source_state is None and target_state is not None:
            observed = _manifest_at(target_parent.descriptor, target_name)
            if not _same_manifest(observed, expected):
                _private_error("quarantine target changed during interrupted operation")
            state = "pending" if restore else "complete"
        else:
            _private_error("interrupted quarantine endpoints are inconsistent")
        _require_disjoint_same_filesystem(collection, expected, target_parent)
        return state, observed


def reconcile_managed_quarantine(
    collection_root: Path, target: Path
) -> QuarantineResult:
    """Finish exactly one interrupted managed quarantine apply or undo."""

    log = ActionLog(collection_root)
    if not log.path.exists():
        _private_error("no action journal is available for reconciliation")
    with log._locked(create=True) as handle:
        runs = log._runs(log._read(handle))
        unresolved = _unresolved_runs(log, runs)
        if not unresolved:
            observed = _inspect_undo_locked(log, runs, collection_root, target)
            return QuarantineResult(
                observed.target_run_id,
                "quarantine",
                observed.manifest.file_count,
                observed.manifest.directory_count,
                observed.manifest.total_bytes,
                observed.manifest.sha256,
                True,
            )
        if len(unresolved) != 1:
            _private_error("action journal does not contain one reconcilable operation")
        run = unresolved[0]
        if run.tool != ToolId.MANAGED_QUARANTINE or run.incomplete:
            _private_error("interrupted operation is not safely reconcilable")
        if not run.actions:
            if run.mode == "APPLY":
                _append_commit(log, handle, run, 0)
                return QuarantineResult(
                    run.run_id,
                    "quarantine",
                    0,
                    0,
                    0,
                    hashlib.sha256().hexdigest(),
                    True,
                    False,
                )
            original = next(
                (
                    candidate
                    for candidate in runs
                    if candidate.run_id == run.target_run_id
                ),
                None,
            )
            if original is None:
                _private_error("interrupted undo target is missing")
            assert original is not None
            _, original_action = _quarantine_action(original)
            original_manifest = _manifest_from_action(original_action, target)
            target_parent_path, _ = _target_parts(target)
            with _open_directory_path(target_parent_path) as target_parent:
                action = _action_for_manifest(
                    original_manifest, target, target_parent.identity
                )
            action_id = str(uuid.uuid4())
            log._append(
                handle,
                {
                    "event": "ACTION_PLANNED",
                    "run_id": run.run_id,
                    "action_id": action_id,
                    "action": action.as_dict(),
                },
            )
            run.actions.append((action_id, action))
        action_id, action = _quarantine_action(run)
        expected = _manifest_from_action(action, target)
        restore = run.mode == "UNDO"
        endpoint_state, observed_manifest = _expected_state(
            collection_root, target, expected, action, restore=restore
        )
        if endpoint_state == "pending":
            _, destination_device, destination_inode = _action_destination(action)
            verified = _perform_move_and_verify(
                collection_root,
                target,
                expected,
                (destination_device, destination_inode),
                restore=restore,
            )
        else:
            verified = observed_manifest
        if action_id not in run.completed_action_ids:
            _append_completion(log, handle, run, action_id)
        _append_commit(log, handle, run, 1)
    return QuarantineResult(
        run.run_id,
        "restore" if restore else "quarantine",
        verified.file_count,
        verified.directory_count,
        verified.total_bytes,
        verified.sha256,
        True,
    )
