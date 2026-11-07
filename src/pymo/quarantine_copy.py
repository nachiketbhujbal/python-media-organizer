"""Explicit, source-retaining copying of a complete duplicate review tree.

Staging and scratch directories are separately journal-bound. No recovery path
removes, overwrites, or truncates a media file, including interrupted scratch.
"""

from __future__ import annotations

import hashlib
import os
import stat
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import TextIO

from pymo.action_log import Action, ActionLog, ActionTransaction, RunRecord, ToolId
from pymo.managed_quarantine import (
    ManagedQuarantineError,
    TreeManifest,
    _atomic_rename_without_replace,
    _directory_flags,
    _encode_field,
    _hash_file,
    _identity,
    _leaf_state,
    _manifest_at,
    _namespace_snapshot,
    _normalized_absolute,
    _open_directory_path,
    _require_directory_path_identity,
    _require_target_absent,
    _same_manifest,
    _stable_file_signature,
    _target_parts,
    destination_binding_sha256,
)
from pymo.quarantine_copy_record import CopyBinding, copy_operations


class NoRetainedCopy(ManagedQuarantineError):
    """Strict history contains no copy attempt; an ordinary apply may be planned."""


@dataclass(frozen=True)
class CopyEntry:
    parts: tuple[str, ...]
    directory: bool
    size: int = 0
    sha256: str = ""


@dataclass(frozen=True)
class CopyEvidence:
    entries: tuple[CopyEntry, ...]
    sha256: str
    metadata_entries: int
    metadata_unknown: int

    @property
    def files(self) -> int:
        return sum(not entry.directory for entry in self.entries)

    @property
    def directories(self) -> int:
        return sum(entry.directory for entry in self.entries)

    @property
    def total_bytes(self) -> int:
        return sum(entry.size for entry in self.entries)


@dataclass(frozen=True)
class CopyPlan:
    collection_root: Path
    collection_identity: tuple[int, int]
    target: Path
    target_parent_identity: tuple[int, int]
    source: TreeManifest
    evidence: CopyEvidence
    reserve_bytes: int


@dataclass(frozen=True)
class CopyResult:
    plan: CopyPlan
    run_id: str
    recovered: bool
    scratch_files: int
    scratch_bytes: int


def _error(message: str) -> None:
    raise ManagedQuarantineError(message)


@contextmanager
def _child_directory(
    parent: int, name: str, expected: tuple[int, int] | None = None
) -> Iterator[int]:
    before = _leaf_state(parent, name)
    if before is None or not stat.S_ISDIR(before.st_mode):
        _error("copy directory is missing or unsafe")
    descriptor = os.open(name, _directory_flags(), dir_fd=parent)
    try:
        if before is None or _identity(os.fstat(descriptor)) != _identity(before):
            _error("copy directory changed")
        if expected is not None and _identity(os.fstat(descriptor)) != expected:
            _error("journal-bound copy directory changed before opening")
        yield descriptor
        after = _leaf_state(parent, name)
        if after is None or _identity(after) != _identity(os.fstat(descriptor)):
            _error("copy directory changed")
    finally:
        os.close(descriptor)


@contextmanager
def _file(parent: int, name: str) -> Iterator[int]:
    before = _leaf_state(parent, name)
    if before is None or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        _error("copy file is missing or unsafe")
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
        dir_fd=parent,
    )
    try:
        opened = os.fstat(descriptor)
        if before is None or _stable_file_signature(opened) != _stable_file_signature(
            before
        ):
            _error("copy file changed")
        yield descriptor
        after = _leaf_state(parent, name)
        if (
            after is None
            or _stable_file_signature(opened) != _stable_file_signature(after)
            or _stable_file_signature(opened)
            != _stable_file_signature(os.fstat(descriptor))
        ):
            _error("copy file changed")
    finally:
        os.close(descriptor)


def _evidence(descriptor: int) -> CopyEvidence:
    initial = _namespace_snapshot(descriptor)
    entries: list[CopyEntry] = []
    metadata_entries = 0
    metadata_unknown = 0

    def metadata(fd: int) -> None:
        nonlocal metadata_entries, metadata_unknown
        try:
            metadata_entries += bool(os.listxattr(fd))  # type: ignore[attr-defined]
        except (AttributeError, OSError, TypeError):
            metadata_unknown += 1

    def visit(fd: int, parts: tuple[str, ...]) -> None:
        entries.append(CopyEntry(parts, True))
        metadata(fd)
        for name in sorted(os.listdir(fd), key=os.fsencode):
            state = _leaf_state(fd, name)
            if state is None:
                _error("copy source changed")
            assert state is not None
            if stat.S_ISDIR(state.st_mode):
                with _child_directory(fd, name) as child:
                    visit(child, (*parts, name))
            else:
                with _file(fd, name) as source:
                    metadata(source)
                    entries.append(
                        CopyEntry(
                            (*parts, name),
                            False,
                            os.fstat(source).st_size,
                            _hash_file(source),
                        )
                    )

    visit(descriptor, ())
    if initial != _namespace_snapshot(descriptor):
        _error("copy tree changed during evidence collection")
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(b"D" if entry.directory else b"F")
        _encode_field(digest, b"/".join(os.fsencode(part) for part in entry.parts))
        if not entry.directory:
            _encode_field(digest, str(entry.size).encode("ascii"))
            _encode_field(digest, entry.sha256.encode("ascii"))
    return CopyEvidence(
        tuple(entries), digest.hexdigest(), metadata_entries, metadata_unknown
    )


def _capacity(parent: int, evidence: CopyEvidence, reserve: int) -> None:
    if type(reserve) is not int or reserve < 0:
        _error("copy reserve must be a nonnegative integer")
    space = os.fstatvfs(parent)
    block = max(1, space.f_frsize)
    # Account for rounded file allocations and directory blocks. This remains
    # a preflight estimate; other writers and filesystem overhead can change it.
    required = reserve + sum(
        block if entry.directory else ((entry.size + block - 1) // block) * block
        for entry in evidence.entries
    )
    if space.f_bavail * block < required:
        _error("insufficient available capacity for retained copying and reserve")


def _require_distinct_devices(source_device: int, destination_device: int) -> None:
    if source_device == destination_device:
        _error("explicit cross-filesystem copy requires distinct filesystems")


def _inspect(
    collection_root: Path, target: Path, reserve_bytes: int, *, occupied: bool = False
) -> CopyPlan:
    if type(reserve_bytes) is not int or reserve_bytes < 0:
        _error("copy reserve must be a nonnegative integer")
    parent_path, name = _target_parts(target)
    with (
        _open_directory_path(collection_root) as collection,
        _open_directory_path(parent_path) as parent,
    ):
        if (
            collection.identity in parent.ancestry
            or parent.identity in collection.ancestry
        ):
            _error("copy destination and collection must be disjoint")
        source = _manifest_at(collection.descriptor, "dups")
        if (source.device, source.inode) in parent.ancestry:
            _error("copy destination is nested in the source")
        _require_distinct_devices(source.device, parent.identity[0])
        with _child_directory(
            collection.descriptor, "dups", (source.device, source.inode)
        ) as source_fd:
            evidence = _evidence(source_fd)
        if not _same_manifest(_manifest_at(collection.descriptor, "dups"), source):
            _error("copy source changed during planning")
        if not occupied:
            _require_target_absent(parent.descriptor, name)
            _capacity(parent.descriptor, evidence, reserve_bytes)
        _require_directory_path_identity(collection.path, collection.identity)
        _require_directory_path_identity(parent.path, parent.identity)
    return CopyPlan(
        collection.path,
        collection.identity,
        parent.path / name,
        parent.identity,
        source,
        evidence,
        reserve_bytes,
    )


def inspect_copy_source(
    collection_root: Path, target: Path, reserve_bytes: int
) -> CopyPlan:
    """Read current source evidence before authorizing a recovery attempt."""
    return _inspect(collection_root, target, reserve_bytes, occupied=True)


def plan_copy(collection_root: Path, target: Path, reserve_bytes: int) -> CopyPlan:
    """Build a zero-write, exact source and explicit target plan."""
    return _inspect(collection_root, target, reserve_bytes)


def _source_scope(plan: CopyPlan) -> str:
    digest = hashlib.sha256(os.fsencode(plan.collection_root))
    digest.update(
        f":{plan.collection_identity[0]}:{plan.collection_identity[1]}".encode("ascii")
    )
    return digest.hexdigest()


def _action(
    operation: str,
    plan: CopyPlan,
    binding: CopyBinding,
    identity: tuple[int, int] | None = None,
) -> Action:
    source = plan.source
    return Action(
        operation,
        "dups",
        binding.encode(),
        "directory",
        {
            "size": source.total_bytes,
            "sha256": source.sha256,
            "device": source.device if identity is None else identity[0],
            "inode": source.inode if identity is None else identity[1],
        },
    )


def _complete(log: ActionLog, handle: TextIO, run_id: str, action_id: str) -> None:
    log._append(
        handle, {"event": "ACTION_COMPLETED", "run_id": run_id, "action_id": action_id}
    )


def _commit(log: ActionLog, handle: TextIO, run_id: str, action_count: int) -> None:
    log._append(
        handle,
        {
            "event": "RUN_COMMITTED",
            "run_id": run_id,
            "action_count": action_count,
            "target_run_id": None,
        },
    )


def _record_identity(action: Action) -> tuple[int, int]:
    assert action.identity is not None
    return int(action.identity["device"]), int(action.identity["inode"])


def _require_identity(parent: int, name: str, identity: tuple[int, int]) -> None:
    state = _leaf_state(parent, name)
    if state is None or not stat.S_ISDIR(state.st_mode) or _identity(state) != identity:
        _error("journal-bound copy directory changed or disappeared")


def _scratch_evidence(
    descriptor: int, tree: int, artifacts: dict[str, Action]
) -> tuple[int, int]:
    total = 0
    initial = _namespace_snapshot(descriptor)
    names = set(os.listdir(descriptor))
    if not names.issubset(artifacts):
        _error("unrecorded or replaced retained scratch artifact")
    published: set[bytes] = set()
    for name, action in artifacts.items():
        assert action.identity is not None and action.before is not None
        if name in names:
            with _file(descriptor, name) as fd:
                if _record_identity(action) != _identity(os.fstat(fd)):
                    _error("unrecorded or replaced retained scratch artifact")
                total += os.fstat(fd).st_size
        else:
            parts = PurePosixPath(action.before).parts[1:]
            with ExitStack() as stack:
                parent = tree
                for part in parts[:-1]:
                    parent = stack.enter_context(_child_directory(parent, part))
                fd = stack.enter_context(_file(parent, parts[-1]))
                if (
                    _record_identity(action) != _identity(os.fstat(fd))
                    or os.fstat(fd).st_size != action.identity["size"]
                    or _hash_file(fd) != action.identity["sha256"]
                ):
                    _error("recorded artifact is missing or changed after publication")
            published.add(b"/".join(os.fsencode(part) for part in parts))
    present = {path for path, kind, _ in _namespace_snapshot(tree) if kind == "file"}
    if present != published:
        _error("staging contains an unrecorded copied file")
    if initial != _namespace_snapshot(descriptor):
        _error("retained scratch changed")
    return len(names), total


def _write_bytes(source: int, target: int) -> None:
    offset = 0
    while chunk := os.pread(source, 1024 * 1024, offset):
        offset += len(chunk)
        view = memoryview(chunk)
        while view:
            written = os.write(target, view)
            if written <= 0:
                _error("retained copy write made no progress")
            view = view[written:]


def _populate(
    source: int,
    stage: int,
    scratch: int,
    evidence: CopyEvidence,
    parent: int,
    reserve: int,
    record_artifact: Callable[[str, int, CopyEntry], None],
) -> None:
    expected = {entry.parts: entry for entry in evidence.entries}

    def visit(src: int, dst: int, parts: tuple[str, ...]) -> None:
        names = sorted(os.listdir(src), key=os.fsencode)
        if not set(os.listdir(dst)).issubset(names):
            _error("staging contains an unexpected entry")
        for name in names:
            entry = expected.get((*parts, name))
            if entry is None:
                _error("source namespace changed after planning")
            assert entry is not None
            present = _leaf_state(dst, name)
            if entry.directory:
                if present is None:
                    os.mkdir(name, 0o700, dir_fd=dst)
                    os.fsync(dst)
                with (
                    _child_directory(src, name) as source_child,
                    _child_directory(dst, name) as target_child,
                ):
                    visit(source_child, target_child, entry.parts)
                    os.fsync(target_child)
                continue
            if present is not None:
                with _file(dst, name) as existing:
                    if (
                        os.fstat(existing).st_size != entry.size
                        or _hash_file(existing) != entry.sha256
                    ):
                        _error("staged file differs from the reviewed source")
                continue
            _capacity(parent, CopyEvidence((entry,), "", 0, 0), reserve)
            temporary = str(uuid.uuid4())
            with _file(src, name) as input_fd:
                output = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=scratch,
                )
                try:
                    os.fsync(output)
                    os.fsync(scratch)
                    record_artifact(temporary, output, entry)
                    _write_bytes(input_fd, output)
                    os.fsync(output)
                finally:
                    os.close(output)
                os.fsync(scratch)
                with _file(scratch, temporary) as copied:
                    if (
                        os.fstat(copied).st_size != entry.size
                        or _hash_file(copied) != entry.sha256
                    ):
                        _error("copied file failed byte verification")
                if _hash_file(input_fd) != entry.sha256:
                    _error("source bytes changed during copying")
                _atomic_rename_without_replace(scratch, temporary, dst, name)
                os.fsync(dst)
                os.fsync(scratch)
        os.fsync(dst)

    visit(source, stage, ())


def _run_copy(
    plan: CopyPlan, log: ActionLog, handle: TextIO, run: RunRecord
) -> CopyResult:
    if not run.actions:
        _error("interrupted copy has no bound intent; operator review is required")
    intent_id, intent = run.actions[0]
    binding = CopyBinding.decode(intent.after or "")
    if (
        intent.identity != plan.source.journal_identity
        or binding.destination != destination_binding_sha256(plan.target)
        or (binding.parent_device, binding.parent_inode) != plan.target_parent_identity
        or binding.content != plan.evidence.sha256
        or binding.reserve_bytes != plan.reserve_bytes
        or binding.source_scope != _source_scope(plan)
    ):
        _error("retained copy no longer matches its exact journal binding")
    with (
        _open_directory_path(plan.collection_root) as collection,
        _open_directory_path(plan.target.parent) as parent,
    ):
        if (
            collection.identity != plan.collection_identity
            or parent.identity != plan.target_parent_identity
        ):
            _error("retained-copy endpoints changed")
        actions = list(run.actions)
        completed = set(run.completed_action_ids)
        target_name = plan.target.name
        for index, name in enumerate(
            (binding.stage_name, binding.scratch_name), start=1
        ):
            if len(actions) <= index:
                _require_target_absent(parent.descriptor, target_name)
                _require_target_absent(parent.descriptor, name)
                _capacity(parent.descriptor, plan.evidence, plan.reserve_bytes)
                os.mkdir(name, 0o700, dir_fd=parent.descriptor)
                os.fsync(parent.descriptor)
                with _child_directory(parent.descriptor, name) as fd:
                    identity = _identity(os.fstat(fd))
                    os.fsync(fd)
                action = _action(copy_operations()[index], plan, binding, identity)
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
                actions.append((action_id, action))
            action_id, action = actions[index]
            current_name = (
                target_name
                if index == 1 and _leaf_state(parent.descriptor, name) is None
                else name
            )
            _require_identity(parent.descriptor, current_name, _record_identity(action))
            if action_id not in completed:
                _complete(log, handle, run.run_id, action_id)
                completed.add(action_id)
        stage_identity = _record_identity(actions[1][1])
        scratch_identity = _record_identity(actions[2][1])
        _require_identity(parent.descriptor, binding.scratch_name, scratch_identity)
        artifacts: dict[str, Action] = {}
        for _, artifact in actions[3:]:
            artifact_binding = CopyBinding.decode(artifact.after or "")
            assert artifact_binding.artifact_name is not None
            parts = PurePosixPath(artifact.before or "").parts[1:]
            source_entry = next(
                (entry for entry in plan.evidence.entries if entry.parts == parts), None
            )
            if (
                source_entry is None
                or source_entry.directory
                or artifact.identity is None
                or (artifact.identity["size"], artifact.identity["sha256"])
                != (source_entry.size, source_entry.sha256)
            ):
                _error("artifact intent does not match its bound source entry")
            artifacts[artifact_binding.artifact_name] = artifact
        with _child_directory(
            parent.descriptor, binding.scratch_name, scratch_identity
        ) as scratch:

            def account_artifacts() -> tuple[int, int]:
                location = (
                    binding.stage_name
                    if _leaf_state(parent.descriptor, binding.stage_name) is not None
                    else target_name
                )
                with _child_directory(
                    parent.descriptor, location, stage_identity
                ) as tree:
                    return _scratch_evidence(scratch, tree, artifacts)

            account_artifacts()
            for artifact_id, artifact in actions[3:]:
                if artifact_id not in completed:
                    pending_name = CopyBinding.decode(
                        artifact.after or ""
                    ).artifact_name
                    assert pending_name is not None
                    with _file(scratch, pending_name) as fd:
                        if _identity(os.fstat(fd)) != _record_identity(
                            artifacts[pending_name]
                        ):
                            _error("pending retained scratch artifact changed")
                    _complete(log, handle, run.run_id, artifact_id)
                    completed.add(artifact_id)

            def record_artifact(name: str, descriptor: int, entry: CopyEntry) -> None:
                state = os.fstat(descriptor)
                artifact = Action(
                    copy_operations()[3],
                    "/".join(("dups", *entry.parts)),
                    replace(binding, artifact_name=name).encode(),
                    "file",
                    {
                        "size": entry.size,
                        "sha256": entry.sha256,
                        "device": state.st_dev,
                        "inode": state.st_ino,
                    },
                )
                artifact_id = str(uuid.uuid4())
                log._append(
                    handle,
                    {
                        "event": "ACTION_PLANNED",
                        "run_id": run.run_id,
                        "action_id": artifact_id,
                        "action": artifact.as_dict(),
                    },
                )
                actions.append((artifact_id, artifact))
                _complete(log, handle, run.run_id, artifact_id)
                completed.add(artifact_id)
                artifacts[name] = artifact

            stage_present = (
                _leaf_state(parent.descriptor, binding.stage_name) is not None
            )
            if (run.committed or intent_id in completed) and stage_present:
                _error("committed copy unexpectedly has an unpublished stage")
            if stage_present:
                _require_target_absent(parent.descriptor, target_name)
                _require_identity(parent.descriptor, binding.stage_name, stage_identity)
                with (
                    _child_directory(
                        collection.descriptor,
                        "dups",
                        (plan.source.device, plan.source.inode),
                    ) as source,
                    _child_directory(
                        parent.descriptor, binding.stage_name, stage_identity
                    ) as stage,
                ):
                    _populate(
                        source,
                        stage,
                        scratch,
                        plan.evidence,
                        parent.descriptor,
                        plan.reserve_bytes,
                        record_artifact,
                    )
                    if _evidence(stage).sha256 != plan.evidence.sha256:
                        _error("staged retained tree failed complete byte verification")
                    os.fsync(stage)
                if not _same_manifest(
                    _manifest_at(collection.descriptor, "dups"), plan.source
                ):
                    _error("source changed before copy publication")
                _require_directory_path_identity(collection.path, collection.identity)
                _require_directory_path_identity(parent.path, parent.identity)
                _require_identity(parent.descriptor, binding.stage_name, stage_identity)
                _atomic_rename_without_replace(
                    parent.descriptor,
                    binding.stage_name,
                    parent.descriptor,
                    target_name,
                )
                os.fsync(parent.descriptor)
            _require_identity(parent.descriptor, target_name, stage_identity)
            with _child_directory(
                parent.descriptor, target_name, stage_identity
            ) as published:
                published_state = _namespace_snapshot(published)
                if _evidence(published).sha256 != plan.evidence.sha256:
                    _error("published retained tree failed byte verification")
                if published_state != _namespace_snapshot(published):
                    _error("published retained tree changed during verification")
            files, byte_count = account_artifacts()
            with _child_directory(
                collection.descriptor, "dups", (plan.source.device, plan.source.inode)
            ) as source:
                final_source_state = _namespace_snapshot(source)
            if not _same_manifest(
                _manifest_at(collection.descriptor, "dups"), plan.source
            ):
                _error("source changed after copy publication")
        _require_directory_path_identity(collection.path, collection.identity)
        _require_directory_path_identity(parent.path, parent.identity)
        _require_identity(parent.descriptor, target_name, stage_identity)
        with _child_directory(
            parent.descriptor, target_name, stage_identity
        ) as published:
            if published_state != _namespace_snapshot(published):
                _error("published retained tree changed before journal commit")
        with _child_directory(
            collection.descriptor, "dups", (plan.source.device, plan.source.inode)
        ) as source:
            if final_source_state != _namespace_snapshot(source):
                _error("source changed before copy journal commit")
        if not run.committed:
            if intent_id not in completed:
                _complete(log, handle, run.run_id, intent_id)
            _commit(log, handle, run.run_id, len(actions))
    return CopyResult(plan, run.run_id, True, files, byte_count)


@contextmanager
def _copy_journal(
    root: Path,
    *,
    create: bool = False,
    write_existing: bool = False,
    expected: tuple[int, int] | None = None,
) -> Iterator[tuple[ActionLog, TextIO]]:
    """Anchor journal creation and access to the same declared collection."""
    with _open_directory_path(root) as collection:
        if expected is not None and collection.identity != expected:
            _error("copy collection changed before journal access")
        log = ActionLog(root)
        if log.root != collection.path:
            _error("copy collection changed before journal access")
        with log._locked(
            create=create,
            write_existing=write_existing,
            root_descriptor=collection.descriptor,
        ) as handle:

            def verify() -> None:
                _require_directory_path_identity(collection.path, collection.identity)
                state = _leaf_state(collection.descriptor, log.path.name)
                if state is None or _identity(state) != _identity(
                    os.fstat(handle.fileno())
                ):
                    _error("copy action journal changed during access")

            verify()
            if create:
                os.fsync(collection.descriptor)
            yield log, handle
            verify()


def apply_copy(plan: CopyPlan) -> CopyResult:
    """Revalidate and copy, retaining every source and interrupted artifact."""
    if plan_copy(plan.collection_root, plan.target, plan.reserve_bytes) != plan:
        _error("retained-copy plan changed before apply")
    with _copy_journal(
        plan.collection_root, create=True, expected=plan.collection_identity
    ) as (log, handle):
        runs = log._runs(log._read(handle))
        if any(not run.committed for run in runs):
            _error("action history contains an interrupted operation")
        if any(
            run.tool == ToolId.COPY_QUARANTINE
            for run in log._active_and_unresolved_runs(runs)
        ):
            _error("a retained-copy operation already binds this source")
        if plan_copy(plan.collection_root, plan.target, plan.reserve_bytes) != plan:
            _error("retained-copy plan changed before journaling")
        binding = CopyBinding(
            destination_binding_sha256(plan.target),
            *plan.target_parent_identity,
            str(uuid.uuid4()),
            plan.evidence.sha256,
            plan.reserve_bytes,
            _source_scope(plan),
        )
        transaction = ActionTransaction(log, handle, tool=ToolId.COPY_QUARANTINE.value)
        transaction.plan(_action(copy_operations()[0], plan, binding))
        run = log._runs(log._read(handle))[-1]
        return _run_copy(plan, log, handle, run)


def recover_copy(collection_root: Path, target: Path, reserve_bytes: int) -> CopyResult:
    """Rehash and resume only the exact journal-bound source and destination."""
    root = _normalized_absolute(collection_root)
    with _copy_journal(root, write_existing=True) as (log, handle):
        runs = log._runs(log._read(handle))
        active = log._active_and_unresolved_runs(runs)
        copies = [run for run in active if run.tool == ToolId.COPY_QUARANTINE]
        if not copies and all(run.committed for run in runs):
            raise NoRetainedCopy("no retained-copy attempt exists")
        if len(copies) != 1 or any(
            not run.committed and run not in copies for run in runs
        ):
            _error("no unique recoverable retained-copy operation")
        plan = _inspect(root, target, reserve_bytes, occupied=True)
        return _run_copy(plan, log, handle, copies[0])


def verify_copy(collection_root: Path, target: Path, reserve_bytes: int) -> CopyResult:
    """Freshly verify a committed retained copy without writing any state."""
    root = _normalized_absolute(collection_root)
    with _copy_journal(root) as (log, handle):
        runs = log._runs(log._read(handle))
        copies = [
            run
            for run in log._active_and_unresolved_runs(runs)
            if run.tool == ToolId.COPY_QUARANTINE
        ]
        if len(copies) != 1 or not copies[0].committed:
            _error("retained copy is not committed")
        plan = _inspect(root, target, reserve_bytes, occupied=True)
        return _run_copy(plan, log, handle, copies[0])
