from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path

import pytest
from PIL import Image
from test_queue_planning import change_policy, job, run, save_manifest, snapshot

from pymo import migrate, queue
from pymo.migration import policy_files, queue_run
from pymo.migration.coordinator_state import _load_state, _state_path
from pymo.migration.policy_acceptance import publish_accepted, receipt_path
from pymo.migration.policy_plan import build_candidate
from pymo.migration.queue_plan import bind_queue
from pymo.migration.virtual import canonical_bytes


def test_run_preview_is_zero_write_and_plan_compatible(tmp_path: Path) -> None:
    manifest = save_manifest(tmp_path, [job(tmp_path, 1), job(tmp_path, 2)])
    before = snapshot(tmp_path)
    result = run("queue", "run", manifest)
    assert result.returncode == 0, result.stderr
    assert "no job started" in result.stdout
    assert snapshot(tmp_path) == before


def test_two_real_jobs_complete_with_distinct_state(tmp_path: Path) -> None:
    entries = [job(tmp_path, 1, authored=True), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    result = run("queue", "run", manifest, "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.index("Queue job 1: completed") < result.stdout.index(
        "Queue job 2/2: starting"
    )
    for entry in entries:
        state = _load_state(_state_path(Path(entry["state_directory"])))
        assert state.attempts[-1].action == "signoff"
        assert state.unattended_policy_sha256 == entry["policy"]["sha256"]
        assert state.baseline == Path(entry["baseline"]["path"])
        assert list(state.baseline.iterdir()) == []
    before = snapshot(tmp_path)
    assert run("queue", "run", manifest, "--apply").returncode == 2
    assert snapshot(tmp_path) == before


def test_authored_image_job_keeps_baseline_and_duplicate_bytes(tmp_path: Path) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    entry = entries[0]
    baseline = Path(entry["baseline"]["path"])
    working = Path(entry["working"]["path"])
    for root in (baseline, working):
        Image.new("RGB", (7, 9), "red").save(root / "image.png")
        (root / "copy.png").write_bytes((root / "image.png").read_bytes())
        (root / "notes.txt").write_text("preserve this too")
    before = snapshot(baseline)
    expected = sorted(p.read_bytes() for p in baseline.iterdir())
    candidate = build_candidate(
        baseline, working, migrate._initial_options({"no_cache": True})
    )
    policy = tmp_path / "private" / "accepted-images.json"
    publish_accepted(
        policy,
        candidate["policy"],
        hashlib.sha256(canonical_bytes(candidate)).hexdigest(),
        (baseline, working),
    )
    entry["policy"] = {
        "path": str(policy),
        "sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
    }
    result = run("queue", "run", save_manifest(tmp_path, entries), "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot(baseline) == before
    assert len(list((working / "dups" / "pics").iterdir())) == 1
    actual = sorted(
        p.read_bytes()
        for p in working.rglob("*")
        if p.is_file() and p.suffix in {".png", ".txt"}
    )
    assert actual == expected


def test_bound_manual_policy_does_not_reopen_replaced_ancestry(
    tmp_path: Path, monkeypatch
) -> None:
    entry = job(tmp_path, 1)
    bound = bind_queue(save_manifest(tmp_path, [entry]))
    parent = tmp_path / "private"
    other = tmp_path / "other"
    other.mkdir(mode=0o700)
    policy = Path(entry["policy"]["path"])
    outside = other / policy.name
    outside.write_bytes(policy.read_bytes())
    outside.chmod(0o600)
    outside_identity = (outside.stat().st_dev, outside.stat().st_ino)
    original = os.open
    opened_outside = False

    def observed(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal opened_outside
        fd = original(path, flags, mode, dir_fd=dir_fd)
        value = os.fstat(fd)
        opened_outside |= (value.st_dev, value.st_ino) == outside_identity
        return fd

    monkeypatch.setattr(os, "open", observed)
    parent.rename(tmp_path / "saved")
    other.rename(parent)
    with pytest.raises(RuntimeError):
        bound.jobs[0].policy.require_current()
    assert not opened_outside


def test_initial_publication_refuses_replaced_job_directory(
    tmp_path: Path, monkeypatch
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    original = policy_files._require_external_private_parent
    replaced = False
    target = Path(entries[0]["state_directory"])

    def swap(path, roots):
        nonlocal replaced
        result = original(path, roots)
        if path.parent == target and not replaced:
            replaced = True
            target.rename(tmp_path / "saved-state")
            target.mkdir(mode=0o700)
        return result

    monkeypatch.setattr(policy_files, "_require_external_private_parent", swap)
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert replaced and list(target.iterdir()) == []
    assert not Path(entries[1]["state_directory"]).exists()


def test_whole_queue_rejection_writes_nothing(tmp_path: Path) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    entries[1]["policy"]["sha256"] = "0" * 64
    manifest = save_manifest(tmp_path, entries)
    before = snapshot(tmp_path)
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert snapshot(tmp_path) == before


def test_actual_evidence_mismatch_stops_before_next_job(tmp_path: Path) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    # Declaration remains valid, but current source bytes are not represented.
    (Path(entries[0]["baseline"]["path"]) / "content.txt").write_text("unique")
    manifest = save_manifest(tmp_path, entries)
    result = run("queue", "run", manifest, "--apply")
    assert result.returncode == 1, result.stdout + result.stderr
    assert not Path(entries[1]["state_directory"]).exists()
    assert "Queue job 2/2: starting" not in result.stdout


@pytest.mark.parametrize("status", [1, 2, 127, 130])
def test_exact_status_stops_and_preserves_started_state(
    tmp_path: Path, monkeypatch, status: int
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    monkeypatch.setattr(migrate, "_run_unattended", lambda *a, **k: status)
    assert queue.main(["run", str(manifest), "--apply"]) == status
    assert _state_path(Path(entries[0]["state_directory"])).exists()
    assert not Path(entries[1]["state_directory"]).exists()


def test_zero_status_without_completed_state_is_not_success(
    tmp_path: Path, monkeypatch
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    monkeypatch.setattr(migrate, "_run_unattended", lambda *a, **k: 0)
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert not Path(entries[1]["state_directory"]).exists()


@pytest.mark.parametrize("phase", ["binding", "state", "engine"])
def test_interruption_keeps_partial_state_and_never_adopts_it(
    tmp_path: Path, monkeypatch, phase: str
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)

    publish = queue_run.publish_private
    publications = 0

    def interrupt(*args, **kwargs):
        nonlocal publications
        publications += 1
        if phase == "state" and publications == 1:
            return publish(*args, **kwargs)
        raise KeyboardInterrupt

    module, name = (
        (migrate, "_run_unattended")
        if phase == "engine"
        else (queue_run, "publish_private")
    )
    monkeypatch.setattr(module, name, interrupt)
    assert queue.main(["run", str(manifest), "--apply"]) == 130
    assert Path(entries[0]["state_directory"]).is_dir()
    assert not Path(entries[1]["state_directory"]).exists()
    before = snapshot(tmp_path)
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("mutation", ["policy", "manifest", "receipt", "root", "state"])
def test_changed_pending_job_stops_at_stage_boundary(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2, authored=True)]
    manifest = save_manifest(tmp_path, entries)

    def change(*args, **kwargs):
        entry = entries[1]
        if mutation == "state":
            Path(entry["state_directory"]).mkdir(mode=0o700)
        elif mutation == "root":
            path = Path(entry["working"]["path"])
            path.rename(tmp_path / "saved-root")
            path.mkdir()
        else:
            path = {
                "manifest": manifest,
                "policy": Path(entry["policy"]["path"]),
                "receipt": receipt_path(Path(entry["policy"]["path"])),
            }[mutation]
            payload = path.read_bytes()
            path.rename(tmp_path / "saved-artifact")
            path.write_bytes(payload)
            path.chmod(0o600)
        kwargs["boundary_check"]()
        pytest.fail("changed queue binding was accepted")

    monkeypatch.setattr(migrate, "_run_unattended", change)
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert not _state_path(Path(entries[1]["state_directory"])).exists()


def test_state_publication_collision_preserves_both_directories(
    tmp_path: Path, monkeypatch
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    original = queue_run._atomic_rename_without_replace
    occupied = Path(entries[0]["state_directory"])

    def collide(*args):
        occupied.mkdir(mode=0o700)
        (occupied / "keep").write_text("untouched")
        return original(*args)

    monkeypatch.setattr(queue_run, "_atomic_rename_without_replace", collide)
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert (occupied / "keep").read_text() == "untouched"
    assert len(list(occupied.parent.glob(".pymo-queue-*.tmp"))) == 1
    assert not Path(entries[1]["state_directory"]).exists()


def test_authored_media_change_fails_before_private_state(tmp_path: Path) -> None:
    entry = job(tmp_path, 1, authored=True)
    manifest = save_manifest(tmp_path, [entry])
    (Path(entry["working"]["path"]) / "extra.txt").write_text("changed")
    before = snapshot(tmp_path)
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert snapshot(tmp_path) == before


def test_unmatched_validation_authority_never_starts_later_job(tmp_path: Path) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    change_policy(
        entries[0], lambda p: p["authorizations"][0]["expected"].update(other_files=1)
    )
    manifest = save_manifest(tmp_path, entries)
    result = run("queue", "run", manifest, "--apply")
    assert result.returncode == 1, result.stdout + result.stderr
    state = json.loads(_state_path(Path(entries[0]["state_directory"])).read_bytes())
    assert state["next_stage"] == 3
    assert not Path(entries[1]["state_directory"]).exists()


def test_replaced_lock_is_refused_before_the_next_stage(
    tmp_path: Path, monkeypatch
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    refused = False

    def replace_lock(log_dir, *args, **kwargs):
        nonlocal refused
        lock = log_dir / "pymo-migration-state.lock"
        lock.rename(log_dir / "retained-lock")
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with pytest.raises(RuntimeError):
                kwargs["boundary_check"]()
            refused = True
            return 2
        finally:
            os.close(fd)

    monkeypatch.setattr(migrate, "_run_unattended", replace_lock)
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert refused and not Path(entries[1]["state_directory"]).exists()


@pytest.mark.parametrize(
    "phase", ["log-allocation", "child-launch", "state-publication"]
)
def test_replaced_state_directory_receives_no_stage_writes(
    tmp_path: Path, monkeypatch, phase: str
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    target = Path(entries[0]["state_directory"])
    saved = tmp_path / "saved-state"
    changed = False
    children = 0
    original_log = migrate._new_log_file
    original_run = migrate.subprocess.run
    original_replace = os.replace

    def substitute():
        nonlocal changed
        assert not changed
        changed = True
        target.rename(saved)
        target.mkdir(mode=0o700)

    def log(*args, **kwargs):
        if phase == "log-allocation":
            substitute()
        return original_log(*args, **kwargs)

    def run_child(*args, **kwargs):
        nonlocal children
        children += 1
        if phase == "child-launch":
            substitute()
        return original_run(*args, **kwargs)

    def replace_state(*args, **kwargs):
        if phase == "state-publication" and kwargs.get("dst_dir_fd") is not None:
            substitute()
        return original_replace(*args, **kwargs)

    monkeypatch.setattr(migrate, "_new_log_file", log)
    monkeypatch.setattr(migrate.subprocess, "run", run_child)
    monkeypatch.setattr(os, "replace", replace_state)
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert changed and list(target.iterdir()) == []
    assert children == (0 if phase == "log-allocation" else 1)
    assert not Path(entries[1]["state_directory"]).exists()
    if phase == "child-launch":
        assert not list(saved.glob("*.outcome.json"))


def test_external_quarantine_does_not_advance_with_present_dups(tmp_path: Path) -> None:
    entry = job(tmp_path, 1)
    for key in ("baseline", "working"):
        root = Path(entry[key]["path"])
        Image.new("RGB", (7, 9), "red").save(root / "image.png")
        (root / "copy.png").write_bytes((root / "image.png").read_bytes())
    candidate = build_candidate(
        Path(entry["baseline"]["path"]),
        Path(entry["working"]["path"]),
        migrate._initial_options({"no_cache": True}),
    )
    policy = candidate["policy"]
    policy.pop("plan_binding")
    policy["schema_version"] = 4
    policy["authorizations"][7]["decision"] = "confirm-quarantine"
    path = Path(entry["policy"]["path"])
    path.write_bytes(canonical_bytes(policy))
    entry["policy"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    entry["disposition"] = "external-quarantine"
    second = job(tmp_path, 2)
    result = run("queue", "run", save_manifest(tmp_path, [entry, second]), "--apply")
    assert result.returncode == 1, result.stdout + result.stderr
    assert (Path(entry["working"]["path"]) / "dups").is_dir()
    assert not Path(second["state_directory"]).exists()


@pytest.mark.parametrize("phase", ["before-child", "after-child"])
def test_allocated_log_cannot_be_replaced_by_an_existing_file(
    tmp_path: Path, monkeypatch, phase: str
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    original = migrate.subprocess.run
    sentinel = tmp_path / "private" / "sentinel"
    sentinel.write_bytes(b"unchanged sentinel")
    sentinel.chmod(0o600)
    replacement = None
    children = []

    def child(command, *, check):
        nonlocal replacement
        replacement = Path(command[command.index("--log-file") + 1])

        def swap():
            replacement.rename(replacement.with_suffix(".retained"))
            sentinel.rename(replacement)

        if phase == "before-child":
            swap()
        result = original(command, check=check, capture_output=True, text=True)
        children.append(result)
        if phase == "after-child":
            swap()
        return result

    monkeypatch.setattr(migrate.subprocess, "run", child)
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert len(children) == 1
    assert children[0].returncode == (2 if phase == "before-child" else 0)
    assert replacement.read_bytes() == b"unchanged sentinel"
    assert not Path(entries[1]["state_directory"]).exists()


@pytest.mark.parametrize("mutation", ["lock", "directory"])
def test_real_child_outcome_binding_failure_has_controlled_error(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    original = migrate.subprocess.run
    children = []
    script = """
import sys
from pymo import cli, scan
original = scan.write_outcome
def altered(path, *args, **kwargs):
    if sys.argv[1] == 'lock':
        lock = path.parent / 'pymo-migration-state.lock'
        lock.rename(path.parent / 'retained-lock')
    else:
        directory = path.parent
        directory.rename(directory.with_name('retained-state'))
        directory.mkdir(mode=0o700)
    return original(path, *args, **kwargs)
scan.write_outcome = altered
raise SystemExit(cli.main(sys.argv[2:]))
"""

    def child(command, *, check):
        result = original(
            [command[0], "-c", script, mutation, *command[3:]],
            check=check,
            capture_output=True,
            text=True,
        )
        children.append(result)
        return result

    monkeypatch.setattr(migrate.subprocess, "run", child)
    assert queue.main(["run", str(manifest), "--apply"]) == 2
    assert len(children) == 1 and children[0].returncode == 1
    assert "Migration outcome could not be recorded safely" in children[0].stderr
    assert "Traceback" not in children[0].stderr
    assert str(tmp_path) not in children[0].stderr
    assert all(line.startswith("20") for line in children[0].stderr.splitlines())
    assert not Path(entries[1]["state_directory"]).exists()
    if mutation == "directory":
        assert list(Path(entries[0]["state_directory"]).iterdir()) == []
