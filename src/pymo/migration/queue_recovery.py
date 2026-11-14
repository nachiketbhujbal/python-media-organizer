"""Explicit queue recovery over strict, independently authorized job state."""

from __future__ import annotations

import fcntl
import os
import stat
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from pymo import __version__, migrate
from pymo.action_log import ActionLog
from pymo.logging_config import emit as print
from pymo.managed_quarantine import (
    _inspect_undo_locked,
    _open_directory_path,
    _require_no_unresolved,
)
from pymo.migration.coordinator_state import MigrationState, _load_state, _state_path
from pymo.migration.policy_files import _pinned_private_parent
from pymo.migration.private_io import PrivateIO
from pymo.migration.queue_manifest import Endpoint, QueuePlanningError
from pymo.migration.queue_plan import BoundJob, bind_queue
from pymo.migration.queue_run import (
    _execute_job,
    _initial_state,
    _new_job_lock,
    _new_state_directory,
    _require_completed,
)
from pymo.migration.synopsis import validate_synopsis_history
from pymo.migration.unattended_binding import (
    require_unattended_policy_binding,
    unattended_policy_binding_path,
)
from pymo.quarantine_copy import verify_copy


@dataclass(frozen=True)
class RecoveryJob:
    state: MigrationState
    files: dict[str, tuple[int, ...]]
    completed: bool
    retry_required: bool


@contextmanager
def _existing_lock(directory: Endpoint) -> Iterator[PrivateIO]:
    """Hold the original existing lock without creating any private entry."""
    path = directory.path / "pymo-migration-state.lock"
    with _pinned_private_parent(path, directory.ancestry) as (parent, name, _):
        descriptor = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        try:
            value = os.fstat(descriptor)
            binding = PrivateIO(
                directory.path, directory.ancestry, (value.st_dev, value.st_ino)
            )
            binding.require_current()
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            binding.require_current()
            yield binding
            binding.require_current()
        finally:
            os.close(descriptor)


def _storage(binding: PrivateIO) -> dict[str, tuple[int, ...]]:
    """Exhaustively pin all entries, including unreferenced child/scratch files."""
    with binding.pinned(_state_path(binding.directory)) as (parent, _, _):
        names = os.listdir(parent)
        result: dict[str, tuple[int, ...]] = {}
        for name in names:
            value = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (
                not stat.S_ISREG(value.st_mode)
                or value.st_nlink != 1
                or value.st_mode & 0o077
                or value.st_uid != os.getuid()
            ):
                raise QueuePlanningError("unsafe recovery artifact")
            result[name] = (
                value.st_dev,
                value.st_ino,
                value.st_mode,
                value.st_nlink,
                value.st_size,
                value.st_mtime_ns,
                value.st_ctime_ns,
            )
        if set(os.listdir(parent)) != set(names):
            raise QueuePlanningError("recovery artifact namespace changed")
        return result


def _require_artifacts(
    state: MigrationState, files: dict[str, tuple[int, ...]]
) -> None:
    expected = {
        "pymo-migration-state.json",
        "pymo-migration-state.lock",
        unattended_policy_binding_path(Path("/")).name,
    }
    children = []
    for attempt in state.attempts:
        for name in (attempt.log_file, attempt.outcome_file):
            if name is not None:
                children.append(name)
    if len(children) != len(set(children)) or set(files) != expected | set(children):
        raise QueuePlanningError(
            "incomplete or unreferenced recovery artifacts require review"
        )


def _retained_evidence(job: BoundJob, state: MigrationState) -> None:
    """Do not accept an occupied managed destination from bookkeeping alone."""
    destination = job.declaration.quarantine_destination
    journal = ActionLog(state.working)
    if journal.path.exists():
        with (
            _open_directory_path(state.working) as root,
            journal._locked(create=False, root_descriptor=root.descriptor) as handle,
        ):
            if root.identity != job.declaration.working_identity:
                raise QueuePlanningError("working root changed")
            runs = journal._runs(journal._read(handle))
            _require_no_unresolved(journal, runs)
    successful = any(
        a.action == "quarantine-apply" and a.exit_status == 0 for a in state.attempts
    )
    if destination is None:
        return
    if not successful:
        if os.path.lexists(destination):
            raise QueuePlanningError("occupied quarantine lacks completed disposition")
        return
    preview = migrate._latest_quarantine_preview(job.declaration.state_directory, state)
    if preview is None:
        raise QueuePlanningError("managed disposition lacks its reviewed preview")
    job.policy.require_quarantine_plan(preview)
    if job.declaration.disposition == "retained-copy":
        assert job.declaration.copy_reserve_bytes is not None
        result = verify_copy(
            state.working, destination, job.declaration.copy_reserve_bytes
        )
        manifest = result.plan.source
    else:
        with (
            _open_directory_path(state.working) as root,
            journal._locked(create=False, root_descriptor=root.descriptor) as handle,
        ):
            if root.identity != job.declaration.working_identity:
                raise QueuePlanningError("working root changed")
            runs = journal._runs(journal._read(handle))
            _require_no_unresolved(journal, runs)
            manifest = _inspect_undo_locked(
                journal, runs, state.working, destination
            ).manifest
    if manifest.sha256 != preview["data"]["manifest_sha256"]:  # type: ignore[index]
        raise QueuePlanningError("retained evidence differs from the approved tree")


def _inspect_job(job: BoundJob, binding: PrivateIO) -> RecoveryJob:
    before = _storage(binding)
    state = _load_state(_state_path(binding.directory), private_io=binding)
    if state.tool_version != __version__:
        raise QueuePlanningError("recovery version differs")
    job.policy.require_binding(state)
    migrate._require_collection_identities(
        state, (job.declaration.baseline_identity, job.declaration.working_identity)
    )
    require_unattended_policy_binding(binding.directory, state, job.policy)
    validate_synopsis_history(binding.directory, state)
    _require_artifacts(state, before)
    _retained_evidence(job, state)
    # Authored policy evidence is rederived; ordinary manual checkpoints retain
    # their fresh-child and exact planned-byte checks on continuation.
    job.policy.require_target(state)
    completed = bool(state.attempts and state.attempts[-1].action == "signoff")
    if completed:
        _require_completed(
            job, Endpoint(binding.directory, binding.ancestry, False), state
        )
    retry = False
    if state.attempts:
        latest = state.attempts[-1]
        if latest.exit_status != 0 and latest.action in {
            "run",
            "quarantine-preview",
            "quarantine-apply",
        }:
            if latest.apply or latest.action == "quarantine-apply":
                raise QueuePlanningError("failed mutation requires journal review")
            retry = migrate._pending_status_one_validation(state) is None
    if _storage(binding) != before:
        raise QueuePlanningError("recovery files changed during inspection")
    return RecoveryJob(state, before, completed, retry)


def resume_queue(
    path: Path,
    *,
    apply: bool,
    selected: int | None = None,
    retries: tuple[int, ...] = (),
) -> int:
    """Preview or resume explicit jobs; never infer completion from missing state."""
    ordinal = 0
    try:
        queue = bind_queue(path, recovery=True)
        count = len(queue.jobs)
        if (selected is not None and not 1 <= selected <= count) or (
            len(retries) != len(set(retries))
            or any(not 1 <= n <= count for n in retries)
        ):
            raise QueuePlanningError("invalid recovery job selection")
        chosen = set(range(count)) if selected is None else {selected - 1}
        if any(n - 1 not in chosen for n in retries):
            raise QueuePlanningError("retry does not select this job")
        with ExitStack() as locks:
            # Lock every existing job before reading any lifecycle or outcome.
            bindings = {
                index: locks.enter_context(_existing_lock(job.endpoints[2]))
                for index, job in enumerate(queue.jobs)
                if not job.endpoints[2].missing
            }
            recovered = {
                index: _inspect_job(queue.jobs[index], binding)
                for index, binding in bindings.items()
            }
            if any(
                not recovered.get(n - 1) or not recovered[n - 1].retry_required
                for n in retries
            ):
                raise QueuePlanningError("retry requires a failed read or preview")
            started: set[int] = set()
            active: int | None = None
            created: list[Endpoint] = []

            def check() -> None:
                queue.require_current(started_jobs=frozenset(started))
                for directory in created:
                    directory.require_current()
                for index, binding in bindings.items():
                    files = _storage(binding)
                    if index == active:
                        current = _load_state(
                            _state_path(binding.directory), private_io=binding
                        )
                        migrate._require_operator_binding(
                            current, recovered[index].state
                        )
                        _require_artifacts(current, files)
                        validate_synopsis_history(binding.directory, current)
                        if _storage(binding) != files:
                            raise QueuePlanningError("active job evidence changed")
                    elif files != recovered[index].files:
                        raise QueuePlanningError("another job changed during recovery")

            check()
            for index in range(count):
                previous = recovered.get(index)
                label = (
                    "not selected"
                    if index not in chosen
                    else (
                        "completed; no child will rerun"
                        if previous and previous.completed
                        else (
                            "retry requires explicit selection"
                            if previous and previous.retry_required
                            else (
                                "resume existing workflow"
                                if previous
                                else "start new workflow"
                            )
                        )
                    )
                )
                print(f"Queue recovery job {index + 1}: {label}.")
            print(
                "Recovery bookkeeping is not fresh preservation evidence or cleanup authority."
            )
            check()
            if not apply:
                print("Recovery preview only; no files written and no child started.")
                return 0
            for index in sorted(chosen):
                previous = recovered.get(index)
                if previous and previous.retry_required and index + 1 not in retries:
                    print(
                        f"Queue recovery stopped at job {index + 1}; explicit --retry-job {index + 1} is required.",
                        file=sys.stderr,
                    )
                    return 1
            for index in sorted(chosen):
                ordinal = index + 1
                job = queue.jobs[index]
                check()
                previous = recovered.get(index)
                if previous and previous.completed:
                    continue
                print(f"Queue recovery job {ordinal}: continuing approved workflow.")
                if previous is None:
                    initial = _initial_state(job)
                    check()
                    with _new_state_directory(job.endpoints[2]) as directory:
                        created.append(directory)
                        started.add(index)
                        private_io = locks.enter_context(_new_job_lock(directory))
                        status = _execute_job(
                            job, directory, initial, check, private_io
                        )
                        if status == 0:
                            recovered[index] = _inspect_job(job, private_io)
                            bindings[index] = private_io
                else:
                    active = index
                    check()
                    state = previous.state
                    status = migrate._run_unattended(
                        job.declaration.state_directory,
                        _state_path(job.declaration.state_directory),
                        state,
                        job.policy,
                        boundary_check=check,
                    )
                    check()
                    if status == 0:
                        _require_completed(job, job.endpoints[2], state)
                        recovered[index] = _inspect_job(job, bindings[index])
                    active = None
                if status != 0:
                    print(
                        f"Queue recovery stopped at job {ordinal} with status {status}; no later selected job started.",
                        file=sys.stderr,
                    )
                    return status
                check()
            print(
                "Selected job finished; other jobs were not advanced."
                if selected
                else "Queue recovery finished; previously completed jobs were not rerun. Retain sources and review storage."
            )
            return 0
    except KeyboardInterrupt:
        print(
            "Queue recovery interrupted; retain all partial state for review.",
            file=sys.stderr,
        )
        return 130
    except (OSError, ValueError, RuntimeError, RecursionError):
        print(
            f"Queue recovery stopped safely at job {ordinal}: unsafe, changed or incomplete evidence. Preserve state and inspect unresolved work.",
            file=sys.stderr,
        )
        return 2
