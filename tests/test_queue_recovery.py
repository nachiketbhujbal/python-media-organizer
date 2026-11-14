from __future__ import annotations

import fcntl
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_queue_planning import job, run, save_manifest, snapshot

from pymo import migrate, queue
from pymo.migration import queue_recovery
from pymo.migration.coordinator_state import _load_state, _state_path
from pymo.migration.policy_acceptance import receipt_path


def pause(tmp_path, monkeypatch, *, stage=2, authored=False, count=2):
    entries = [job(tmp_path, n, authored=authored) for n in range(1, count + 1)]
    manifest = save_manifest(tmp_path, entries)
    engine = migrate._run_unattended

    def interrupted(directory, state_path, state, policy, *, boundary_check):
        def boundary():
            boundary_check()
            if _load_state(state_path).next_stage >= stage:
                raise KeyboardInterrupt

        return engine(directory, state_path, state, policy, boundary_check=boundary)

    with monkeypatch.context() as patch:
        patch.setattr(migrate, "_run_unattended", interrupted)
        assert queue.main(["run", str(manifest), "--apply"]) == 130
    return entries, manifest


def test_resume_preview_is_zero_write_and_preserves_original_plan_contract(
    tmp_path, monkeypatch
):
    _, manifest = pause(tmp_path, monkeypatch, authored=True)
    before = snapshot(tmp_path)
    result = run("queue", "resume", manifest)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "preview only" in result.stdout
        and str(tmp_path) not in result.stdout + result.stderr
    )
    assert snapshot(tmp_path) == before
    assert run("queue", "plan", manifest).returncode == 2
    assert run("queue", "run", manifest, "--apply").returncode == 2
    assert snapshot(tmp_path) == before


def test_resume_continues_from_exact_stage_and_does_not_rerun_completed(
    tmp_path, monkeypatch
):
    entries, manifest = pause(tmp_path, monkeypatch, authored=True)
    first = Path(entries[0]["state_directory"])
    original = _load_state(_state_path(first)).attempts
    result = run("queue", "resume", manifest, "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("Running one migration stage: baseline-scan.") == 1
    for entry in entries:
        assert (
            _load_state(_state_path(Path(entry["state_directory"]))).attempts[-1].action
            == "signoff"
        )
    assert _load_state(_state_path(first)).attempts[: len(original)] == original
    before = snapshot(tmp_path)
    result = run("queue", "resume", manifest, "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Running one migration stage" not in result.stdout
    assert snapshot(tmp_path) == before


def test_selected_job_does_not_advance_other_jobs_or_claim_queue_completion(
    tmp_path, monkeypatch
):
    entries, manifest = pause(tmp_path, monkeypatch)
    first = Path(entries[0]["state_directory"])
    before = snapshot(first)
    result = run("queue", "resume", manifest, "--job", 2, "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot(first) == before
    assert (
        "Selected job finished" in result.stdout
        and "Queue recovery finished" not in result.stdout
    )
    second = Path(entries[1]["state_directory"])
    before_second = snapshot(second)
    assert run("queue", "resume", manifest, "--apply").returncode == 0
    assert snapshot(second) == before_second


@pytest.mark.parametrize(
    "args",
    [
        ("--job", "0"),
        ("--job", "3"),
        ("--retry-job", "1"),
        ("--retry-job", "1", "--retry-job", "1"),
        ("--job", "1", "--retry-job", "2"),
        ("--skip-job", "1"),
    ],
)
def test_invalid_or_unneeded_selection_is_zero_write(tmp_path, monkeypatch, args):
    _, manifest = pause(tmp_path, monkeypatch, stage=0)
    before = snapshot(tmp_path)
    assert run("queue", "resume", manifest, *args, "--apply").returncode == 2
    assert snapshot(tmp_path) == before


def test_failed_read_requires_explicit_retry_and_preserves_attempt_history(
    tmp_path, monkeypatch
):
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    with monkeypatch.context() as patch:
        patch.setattr(
            migrate.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=127)
        )
        assert queue.main(["run", str(manifest), "--apply"]) == 127
    first = Path(entries[0]["state_directory"])
    before = snapshot(tmp_path)
    assert run("queue", "resume", manifest, "--apply").returncode == 1
    assert snapshot(tmp_path) == before
    result = run("queue", "resume", manifest, "--retry-job", 1, "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    state = _load_state(_state_path(first))
    assert state.attempts[0].exit_status == 127 and state.attempts[1].exit_status == 0
    assert state.attempts[-1].action == "signoff"


@pytest.mark.parametrize(
    "artifact", ["orphan.log", "orphan.outcome.json", ".state.tmp", "unknown"]
)
def test_orphan_artifacts_refused_even_for_individual_selection(
    tmp_path, monkeypatch, artifact
):
    entries, manifest = pause(tmp_path, monkeypatch, stage=0)
    path = Path(entries[0]["state_directory"]) / artifact
    path.write_bytes(b"preserve ambiguous output")
    path.chmod(0o600)
    before = snapshot(tmp_path)
    result = run("queue", "resume", manifest, "--job", 2, "--apply")
    assert result.returncode == 2 and str(tmp_path) not in result.stderr
    assert snapshot(tmp_path) == before


def test_failed_apply_is_never_automatically_retried(tmp_path, monkeypatch):
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    real = migrate.subprocess.run

    def child(command, **kwargs):
        if "--apply" in command:
            return SimpleNamespace(returncode=127)
        return real(command, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(migrate.subprocess, "run", child)
        assert queue.main(["run", str(manifest), "--apply"]) == 127
    state = _load_state(_state_path(Path(entries[0]["state_directory"])))
    assert state.attempts[-1].apply
    before = snapshot(tmp_path)
    assert run("queue", "resume", manifest, "--retry-job", 1, "--apply").returncode == 2
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "name",
    [
        "pymo-migration-state.lock",
        "pymo-migration-state.json",
        "pymo-unattended-policy-binding.json",
    ],
)
def test_missing_controls_are_not_recreated(tmp_path, monkeypatch, name):
    entries, manifest = pause(tmp_path, monkeypatch, stage=0)
    directory = Path(entries[0]["state_directory"])
    (directory / name).rename(tmp_path / "retained-control")
    before = snapshot(tmp_path)
    assert run("queue", "resume", manifest, "--apply").returncode == 2
    assert snapshot(tmp_path) == before


def test_busy_later_job_prevents_any_state_or_child_work(tmp_path, monkeypatch):
    entries, manifest = pause(tmp_path, monkeypatch, stage=0)
    with monkeypatch.context() as patch:
        patch.setattr(migrate, "_run_unattended", lambda *a, **k: 130)
        assert queue.main(["resume", str(manifest), "--job", "2", "--apply"]) == 130
    lock = Path(entries[1]["state_directory"]) / "pymo-migration-state.lock"
    with lock.open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = snapshot(tmp_path)
        assert run("queue", "resume", manifest, "--job", 1, "--apply").returncode == 2
        assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "mutation", ["state", "policy", "receipt", "root", "directory", "lock"]
)
def test_binding_changes_stop_before_resumed_child(tmp_path, monkeypatch, mutation):
    entries, manifest = pause(tmp_path, monkeypatch, authored=True, stage=0)
    original = queue_recovery._inspect_job
    changed = False
    directory = Path(entries[0]["state_directory"])

    def inspect(job, binding):
        nonlocal changed
        result = original(job, binding)
        if not changed:
            changed = True
            target = {
                "state": _state_path(directory),
                "policy": Path(entries[0]["policy"]["path"]),
                "receipt": receipt_path(Path(entries[0]["policy"]["path"])),
                "root": Path(entries[0]["working"]["path"]),
                "directory": directory,
                "lock": directory / "pymo-migration-state.lock",
            }[mutation]
            is_directory = target.is_dir()
            payload = None if is_directory else target.read_bytes()
            target.rename(tmp_path / "retained")
            if is_directory:
                target.mkdir(mode=0o700)
            else:
                target.write_bytes(payload)
                target.chmod(0o600)
        return result

    monkeypatch.setattr(queue_recovery, "_inspect_job", inspect)
    monkeypatch.setattr(
        migrate, "_run_unattended", lambda *a, **k: pytest.fail("child dispatched")
    )
    assert queue.main(["resume", str(manifest), "--apply"]) == 2
    assert changed and not Path(entries[1]["state_directory"]).exists()


def test_resume_preserves_ctrl_c_and_later_job_absence(tmp_path, monkeypatch):
    entries, manifest = pause(tmp_path, monkeypatch, stage=0)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(migrate, "_run_unattended", interrupt)
    assert queue.main(["resume", str(manifest), "--apply"]) == 130
    assert not Path(entries[1]["state_directory"]).exists()


def managed_fixture(tmp_path):
    import hashlib

    from test_migrate import _set_simulation_review, _state_at, _zero_unattended_policy

    from pymo.managed_quarantine import plan_managed_quarantine
    from pymo.quarantine import _plan_data

    entry = job(tmp_path, 1)
    baseline = Path(entry["baseline"]["path"])
    working = Path(entry["working"]["path"])
    directory = Path(entry["state_directory"])
    directory.mkdir(mode=0o700)
    destination = tmp_path / "retained"
    (working / "dups").mkdir()
    (working / "dups" / "copy.bin").write_bytes(b"retained bytes")
    _state_at(directory, baseline, working, 21, quarantine_destination=destination)
    _set_simulation_review(directory, review_files=1, review_bytes=14)
    policy = _zero_unattended_policy(
        Path(entry["policy"]["path"]),
        baseline,
        working,
        options={"quarantine_destination": str(destination)},
        overrides={
            "duplicate-disposition": {
                "review_files": 1,
                "review_bytes": 14,
                "quarantine_plan": _plan_data(
                    plan_managed_quarantine(working, destination)
                ),
            }
        },
        duplicate_disposition="quarantine-dups",
    )
    state = _load_state(_state_path(directory))
    for attempt in state.attempts:
        if attempt.log_file:
            path = directory / attempt.log_file
            path.write_bytes(b"synthetic completed stage\n")
            path.chmod(0o600)
    with migrate._state_lock(directory):
        migrate._bind_unattended_policy(
            directory,
            _state_path(directory),
            state,
            migrate.load_preauthorization(policy, roots=(baseline, working)),
        )
    entry["policy"]["sha256"] = hashlib.sha256(policy.read_bytes()).hexdigest()
    entry["disposition"] = "managed-same-filesystem"
    entry["quarantine"] = {"destination": str(destination), "copy_reserve_bytes": None}
    return entry, save_manifest(tmp_path, [entry]), destination


def test_recovery_verifies_committed_managed_retention_and_refuses_changed_tree(
    tmp_path,
):
    _, manifest, destination = managed_fixture(tmp_path)
    result = run("queue", "resume", manifest, "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (destination / "copy.bin").read_bytes() == b"retained bytes"
    before = snapshot(tmp_path)
    result = run("queue", "resume", manifest)
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot(tmp_path) == before
    (destination / "copy.bin").write_bytes(b"changed bytes")
    before = snapshot(tmp_path)
    assert run("queue", "resume", manifest, "--apply").returncode == 2
    assert snapshot(tmp_path) == before


def test_occupied_managed_destination_cannot_be_adopted(tmp_path):
    _, manifest, destination = managed_fixture(tmp_path)
    destination.mkdir()
    before = snapshot(tmp_path)
    assert run("queue", "resume", manifest, "--apply").returncode == 2
    assert snapshot(tmp_path) == before


def test_unresolved_action_journal_blocks_even_with_clean_coordinator_state(
    tmp_path, monkeypatch
):
    from pymo.action_log import ActionLog, ToolId

    entries, manifest = pause(tmp_path, monkeypatch, stage=0)
    journal = ActionLog(Path(entries[0]["working"]["path"]))
    with pytest.raises(KeyboardInterrupt), journal.transaction(ToolId.ORGANIZE):
        raise KeyboardInterrupt
    before = snapshot(tmp_path)
    assert run("queue", "resume", manifest, "--apply").returncode == 2
    assert snapshot(tmp_path) == before


def test_late_orphan_stops_at_next_resumed_stage_boundary(tmp_path, monkeypatch):
    entries, manifest = pause(tmp_path, monkeypatch, stage=0)

    def child(directory, *args, **kwargs):
        orphan = directory / "late.log"
        orphan.write_bytes(b"unaccounted child")
        orphan.chmod(0o600)
        kwargs["boundary_check"]()
        pytest.fail("late orphan was accepted")

    monkeypatch.setattr(migrate, "_run_unattended", child)
    assert queue.main(["resume", str(manifest), "--apply"]) == 2
    assert not Path(entries[1]["state_directory"]).exists()


def test_log_marker_sync_failure_prevents_child_launch(tmp_path, monkeypatch):
    entries = [job(tmp_path, 1)]
    manifest = save_manifest(tmp_path, entries)
    original = queue_recovery.os.fsync

    def sync(descriptor):
        if os.fstat(descriptor).st_size == 0:
            raise OSError("synthetic sync refusal")
        return original(descriptor)

    monkeypatch.setattr(queue_recovery.os, "fsync", sync)
    monkeypatch.setattr(
        migrate.subprocess, "run", lambda *a, **k: pytest.fail("child started")
    )
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert list(Path(entries[0]["state_directory"]).glob("*.log"))


@pytest.mark.parametrize("mutation", ["tree", "journal"])
def test_retained_evidence_is_rechecked_before_a_later_job_runs(
    tmp_path, monkeypatch, mutation
):
    from pymo.action_log import ActionLog, ToolId

    entry, manifest, destination = managed_fixture(tmp_path)
    assert run("queue", "resume", manifest, "--apply").returncode == 0
    second = job(tmp_path, 2)
    manifest = save_manifest(tmp_path, [entry, second])

    def intercepted(job, directory, initial, check, private_io=None, **kwargs):
        if mutation == "tree":
            (destination / "copy.bin").write_bytes(b"changed retained content")
        else:
            journal = ActionLog(Path(entry["working"]["path"]))
            with pytest.raises(KeyboardInterrupt), journal.transaction(ToolId.ORGANIZE):
                raise KeyboardInterrupt
        check()
        pytest.fail("changed retained evidence accepted at next dispatch")

    monkeypatch.setattr(queue_recovery, "_execute_job", intercepted)
    assert queue.main(["resume", str(manifest), "--apply"]) == 2
    assert not _state_path(Path(second["state_directory"])).exists()


def test_retained_tree_is_rechecked_before_recovery_success(tmp_path, monkeypatch):
    _, manifest, destination = managed_fixture(tmp_path)
    assert run("queue", "resume", manifest, "--apply").returncode == 0
    original = queue_recovery._retained_evidence
    calls = 0

    def checked(*args):
        nonlocal calls
        calls += 1
        original(*args)
        if calls == 2:
            (destination / "copy.bin").write_bytes(b"late changed bytes")

    monkeypatch.setattr(queue_recovery, "_retained_evidence", checked)
    assert queue.main(["resume", str(manifest), "--apply"]) == 2
    assert calls >= 3


@pytest.mark.parametrize("changed", [False, True])
def test_unsigned_terminal_manual_run_requires_fresh_human_review(
    tmp_path, monkeypatch, changed
):
    entries, manifest = pause(
        tmp_path, monkeypatch, stage=len(migrate._stages()), count=1
    )
    if changed:
        (Path(entries[0]["baseline"]["path"]) / "new.txt").write_bytes(
            b"not represented"
        )
    before = snapshot(tmp_path)
    result = run("queue", "resume", manifest, "--apply")
    assert result.returncode == 2, result.stdout + result.stderr
    assert snapshot(tmp_path) == before
    assert (
        _load_state(_state_path(Path(entries[0]["state_directory"])))
        .attempts[-1]
        .action
        != "signoff"
    )


def test_unsigned_terminal_authored_run_requires_current_bound_namespace(
    tmp_path, monkeypatch
):
    entries, manifest = pause(
        tmp_path, monkeypatch, stage=len(migrate._stages()), count=1, authored=True
    )
    baseline = Path(entries[0]["baseline"]["path"])
    (baseline / "new.txt").write_bytes(b"not represented")
    before = snapshot(tmp_path)
    assert run("queue", "resume", manifest, "--apply").returncode == 2
    assert snapshot(tmp_path) == before


def test_status_one_validation_keeps_exact_acknowledgement_policy(tmp_path):
    entry = job(tmp_path, 1)
    (Path(entry["baseline"]["path"]) / "empty.jpg").write_bytes(b"")
    manifest = save_manifest(tmp_path, [entry])
    result = run("queue", "run", manifest, "--apply")
    assert result.returncode == 1, result.stdout + result.stderr
    state = _load_state(_state_path(Path(entry["state_directory"])))
    assert state.attempts[-1].stage == "baseline-validation"
    assert state.attempts[-1].exit_status == 1
    before = snapshot(tmp_path)
    assert run("queue", "resume", manifest, "--retry-job", 1, "--apply").returncode == 2
    assert run("queue", "resume", manifest, "--apply").returncode == 1
    assert snapshot(tmp_path) == before
