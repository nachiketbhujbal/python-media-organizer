"""Sequential new-job execution over the existing unattended stage engine."""

from __future__ import annotations

import fcntl
import os
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from pymo import __version__, migrate
from pymo.logging_config import emit as print
from pymo.managed_quarantine import _atomic_rename_without_replace
from pymo.migration.coordinator_state import (
    MigrationState,
    _load_state,
    _now,
    _state_path,
)
from pymo.migration.policy_files import _pinned_private_parent, publish_private
from pymo.migration.queue_manifest import Endpoint, QueuePlanningError, observe_endpoint
from pymo.migration.queue_plan import BoundJob, bind_queue
from pymo.migration.synopsis import validate_synopsis_history
from pymo.migration.unattended_binding import (
    _binding_for,
    require_private_unattended_log_directory,
    require_unattended_policy_binding,
    unattended_policy_binding_path,
)
from pymo.migration.virtual import canonical_bytes
from pymo.migration.workflow import _stages


@contextmanager
def _new_state_directory(destination: Endpoint) -> Iterator[Endpoint]:
    """Publish an exclusively allocated directory; preserve all partial state."""
    with _pinned_private_parent(destination.path, destination.ancestry) as (
        parent_fd,
        name,
        _,
    ):
        destination.require_current()
        temporary = f".pymo-queue-{uuid.uuid4().hex}.tmp"
        os.mkdir(temporary, mode=0o700, dir_fd=parent_fd)
        descriptor = os.open(
            temporary,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
        try:
            allocated = os.fstat(descriptor)
            _atomic_rename_without_replace(parent_fd, temporary, parent_fd, name)
            os.fsync(parent_fd)
            created = observe_endpoint(destination.path)
            if created.ancestry != (
                (allocated.st_dev, allocated.st_ino),
                *destination.ancestry,
            ):
                raise QueuePlanningError("new state directory was replaced")
            require_private_unattended_log_directory(created.path)
            yield created
            created.require_current()
        finally:
            os.close(descriptor)


@contextmanager
def _new_job_lock(directory: Endpoint) -> Iterator[None]:
    path = directory.path / "pymo-migration-state.lock"
    with _pinned_private_parent(path, directory.ancestry) as (parent_fd, name, _):
        descriptor = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            initial = os.fstat(descriptor)
            yield
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (initial.st_dev, initial.st_ino):
                raise QueuePlanningError("new job lock was replaced")
        finally:
            os.close(descriptor)


def _initial_state(job: BoundJob) -> MigrationState:
    created = _now()
    state = MigrationState(
        __version__,
        job.declaration.baseline,
        job.declaration.working,
        migrate._initial_options(dict(job.policy.options)),
        0,
        (),
        created,
        created,
        job.policy.payload_sha256,
    )
    job.policy.require_binding(state)
    job.policy.require_current()
    job.policy.require_target(state)
    return state


def _require_completed(
    job: BoundJob, directory: Endpoint, initial: MigrationState
) -> None:
    directory.require_current()
    state = _load_state(_state_path(directory.path))
    migrate._require_operator_binding(state, initial)
    migrate._require_collection_identities(
        state, (job.declaration.baseline_identity, job.declaration.working_identity)
    )
    job.policy.require_current()
    job.policy.require_binding(state)
    job.policy.require_target(state)
    require_unattended_policy_binding(directory.path, state, job.policy)
    validate_synopsis_history(directory.path, state)
    if (
        state.next_stage != len(_stages())
        or not state.attempts
        or state.attempts[-1].action != "signoff"
    ):
        raise QueuePlanningError("job returned success without completed sign-off")
    # A final state is bookkeeping; the original final evidence must still be
    # present, typed and exactly authorized, including retained-copy dependencies.
    job.policy.require_checkpoint(
        "final-signoff",
        migrate._recorded_outcome(directory.path, state, _stages()[-1].identifier),
    )
    migrate._require_current_retained_copy(state)
    if _load_state(_state_path(directory.path)) != state:
        raise QueuePlanningError("completed job state changed during verification")
    directory.require_current()


def _execute_job(
    job: BoundJob,
    directory: Endpoint,
    initial: MigrationState,
    check: Callable[[], None],
) -> int:
    with _new_job_lock(directory):
        check()
        job.policy.require_target(initial)
        publish_private(
            unattended_policy_binding_path(directory.path),
            canonical_bytes(_binding_for(initial, job.policy).as_json()),
            (initial.baseline, initial.working),
            expected_ancestry=directory.ancestry,
        )
        check()
        publish_private(
            _state_path(directory.path),
            canonical_bytes(initial.as_json()),
            (initial.baseline, initial.working),
            expected_ancestry=directory.ancestry,
        )
        check()
        status = migrate._run_unattended(
            directory.path,
            _state_path(directory.path),
            initial,
            job.policy,
            boundary_check=check,
        )
        if status != 0:
            return status
        check()
        _require_completed(job, directory, initial)
        return 0


def run_queue(path: Path) -> int:
    """Start each new job once, never adopt state or continue past uncertainty."""
    ordinal = 0
    try:
        queue = bind_queue(path)
        directories: list[Endpoint] = []

        def check() -> None:
            queue.require_current(started=len(directories))
            for directory in directories:
                directory.require_current()
                require_private_unattended_log_directory(directory.path)

        for ordinal, job in enumerate(queue.jobs, 1):
            check()
            initial = _initial_state(job)
            check()
            print(f"Queue job {ordinal}/{len(queue.jobs)}: starting approved workflow.")
            with _new_state_directory(job.endpoints[2]) as directory:
                directories.append(directory)
                status = _execute_job(job, directory, initial, check)
                if status != 0:
                    print(
                        f"Queue stopped at job {ordinal} with status {status}; later jobs were not started.",
                        file=sys.stderr,
                    )
                    return status
                check()
            print(f"Queue job {ordinal}: completed its approved workflow.")
        print(
            "Queue execution finished. Retain sources and review storage; cleanup remains a separate human decision."
        )
        return 0
    except KeyboardInterrupt:
        print(
            "Queue interrupted; partial job state is retained and later jobs were not started.",
            file=sys.stderr,
        )
        return 130
    except (OSError, ValueError, RuntimeError, RecursionError):
        print(
            f"Queue stopped safely at job {ordinal}: unsafe, changed or incomplete evidence. Preserve any started job state; later jobs were not started.",
            file=sys.stderr,
        )
        return 2
