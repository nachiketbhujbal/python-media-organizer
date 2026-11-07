from __future__ import annotations

import errno
import json
import os
import tempfile
from pathlib import Path

import pytest

from pymo import quarantine as cli
from pymo import quarantine_copy as copying
from pymo.action_log import Action, ActionLog, ActionLogError, action_log_path
from pymo.managed_quarantine import ManagedQuarantineError


def collection(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path.resolve() / "collection"
    source = root / "dups"
    (source / "pics").mkdir(parents=True)
    (source / "empty").mkdir()
    (source / "pics" / "first.bin").write_bytes(b"first content")
    (source / "second.bin").write_bytes(b"second content")
    parent = tmp_path.resolve() / "retained"
    parent.mkdir()
    return root, parent / "target"


@pytest.fixture
def simulated_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    # Unit tests exercise failures on temporary storage. A separate integration
    # test below uses actual distinct devices and does not patch this guard.
    monkeypatch.setattr(copying, "_require_distinct_devices", lambda *_: None)


def media(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_same_filesystem_is_rejected_without_implicit_fallback(tmp_path: Path) -> None:
    root, target = collection(tmp_path)
    with pytest.raises(ManagedQuarantineError, match="distinct filesystems"):
        copying.plan_copy(root, target, 0)
    assert not action_log_path(root).exists()
    assert not target.exists()


def test_copy_is_explicit_zero_write_preview_and_retains_originals(
    tmp_path: Path, simulated_devices: None
) -> None:
    root, target = collection(tmp_path)
    before = media(root / "dups")
    first = copying.plan_copy(root, target, 0)
    assert first == copying.plan_copy(root, target, 0)
    assert not action_log_path(root).exists()
    assert not list(target.parent.iterdir())
    result = copying.apply_copy(first)
    assert result.plan == first
    assert media(root / "dups") == before == media(target)
    assert (target / "empty").is_dir()
    journal = action_log_path(root).read_bytes()
    assert os.fsencode(target) not in journal
    events = [json.loads(line) for line in journal.splitlines()]
    assert events[-1]["event"] == "RUN_COMMITTED"
    assert len([event for event in events if event["event"] == "ACTION_PLANNED"]) == 5
    copying.recover_copy(root, target, 0)
    assert action_log_path(root).read_bytes() == journal


def test_changed_source_and_occupied_target_refuse_before_journaling(
    tmp_path: Path, simulated_devices: None
) -> None:
    root, target = collection(tmp_path)
    plan = copying.plan_copy(root, target, 0)
    (root / "dups" / "second.bin").write_bytes(b"changed")
    with pytest.raises(ManagedQuarantineError, match="changed"):
        copying.apply_copy(plan)
    assert not action_log_path(root).exists()
    target.mkdir()
    with pytest.raises(ManagedQuarantineError, match="occupied"):
        copying.plan_copy(root, target, 0)


def test_capacity_failure_creates_no_journal_or_staging(
    tmp_path: Path, simulated_devices: None
) -> None:
    root, target = collection(tmp_path)
    with pytest.raises(ManagedQuarantineError, match="capacity"):
        copying.plan_copy(root, target, 10**30)
    assert not action_log_path(root).exists()
    assert list(target.parent.iterdir()) == []


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_unsafe_source_entries_fail_closed(
    tmp_path: Path, simulated_devices: None, kind: str
) -> None:
    root, target = collection(tmp_path)
    path = root / "dups" / "unsafe"
    if kind == "symlink":
        path.symlink_to(root / "dups" / "second.bin")
    elif kind == "hardlink":
        path.hardlink_to(root / "dups" / "second.bin")
    else:
        os.mkfifo(path)
    with pytest.raises(ManagedQuarantineError):
        copying.plan_copy(root, target, 0)
    assert not action_log_path(root).exists()


def test_partial_copy_is_retained_and_recovery_never_overwrites_it(
    tmp_path: Path, simulated_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = collection(tmp_path)
    before = media(root / "dups")
    original = copying._write_bytes

    def interrupted(source: int, destination: int) -> None:
        os.write(destination, b"partial")
        raise OSError(errno.ENOSPC, "injected")

    monkeypatch.setattr(copying, "_write_bytes", interrupted)
    with pytest.raises(OSError):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    assert not target.exists()
    scratch = next(target.parent.glob("*-partial"))
    partials = media(scratch)
    journal_before = action_log_path(root).read_bytes()
    monkeypatch.setattr(copying, "_write_bytes", original)
    result = copying.recover_copy(root, target, 0)
    assert result.scratch_files == 1
    assert media(scratch) == partials
    assert media(target) == before == media(root / "dups")
    assert action_log_path(root).read_bytes().startswith(journal_before)


def test_recovery_reuses_only_verified_completed_files(
    tmp_path: Path, simulated_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = collection(tmp_path)
    original = copying._write_bytes
    calls = 0

    def interrupted(source: int, destination: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        original(source, destination)

    monkeypatch.setattr(copying, "_write_bytes", interrupted)
    with pytest.raises(KeyboardInterrupt):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    calls = 0
    monkeypatch.setattr(copying, "_write_bytes", interrupted)
    copying.recover_copy(root, target, 0)
    assert calls == 1
    assert media(target) == media(root / "dups")


def test_publication_interruption_recovers_exact_recorded_directory(
    tmp_path: Path, simulated_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = collection(tmp_path)
    original = copying._atomic_rename_without_replace

    def after_publish(
        source_parent: int, source_name: str, target_parent: int, target_name: str
    ) -> None:
        original(source_parent, source_name, target_parent, target_name)
        if target_name == target.name:
            raise KeyboardInterrupt

    monkeypatch.setattr(copying, "_atomic_rename_without_replace", after_publish)
    with pytest.raises(KeyboardInterrupt):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    identity = target.stat().st_ino
    monkeypatch.setattr(copying, "_atomic_rename_without_replace", original)
    copying.recover_copy(root, target, 0)
    assert target.stat().st_ino == identity
    assert media(target) == media(root / "dups")


def test_impostor_published_tree_and_changed_source_are_not_adopted(
    tmp_path: Path, simulated_devices: None
) -> None:
    root, target = collection(tmp_path)
    copying.apply_copy(copying.plan_copy(root, target, 0))
    original = target.with_name("original")
    target.rename(original)
    target.mkdir()
    with pytest.raises(ManagedQuarantineError, match=r"changed|disappeared"):
        copying.recover_copy(root, target, 0)
    target.rmdir()
    original.rename(target)
    (root / "dups" / "second.bin").write_bytes(b"changed")
    with pytest.raises(ManagedQuarantineError, match="binding"):
        copying.recover_copy(root, target, 0)


def test_orphan_stage_is_never_adopted(
    tmp_path: Path, simulated_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = collection(tmp_path)
    original = ActionLog._append

    def fail_record(log: ActionLog, handle: object, event: dict[str, object]) -> None:
        if (
            event["event"] == "ACTION_PLANNED"
            and event["action"]["operation"] == "COPY_QUARANTINE_STAGE"
        ):
            raise KeyboardInterrupt
        original(log, handle, event)

    monkeypatch.setattr(ActionLog, "_append", fail_record)
    with pytest.raises(KeyboardInterrupt):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    monkeypatch.setattr(ActionLog, "_append", original)
    with pytest.raises(ManagedQuarantineError, match="occupied"):
        copying.recover_copy(root, target, 0)
    assert not target.exists()
    assert media(root / "dups")


def test_copy_cannot_be_generically_undone_or_source_mutated(
    tmp_path: Path, simulated_devices: None
) -> None:
    root, target = collection(tmp_path)
    copying.apply_copy(copying.plan_copy(root, target, 0))
    with pytest.raises(ActionLogError):
        ActionLog(root).plan_undo("copy_quarantine")
    with pytest.raises(ActionLogError, match="protects"):
        with ActionLog(root).transaction("organize_media") as transaction:
            transaction.plan(Action.create_directory(root, root / "dups" / "new"))
    assert media(root / "dups") == media(target)


def test_cli_recovery_checks_review_binding_before_any_resume_write(
    tmp_path: Path, simulated_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = collection(tmp_path)
    original = copying._write_bytes
    monkeypatch.setattr(
        copying, "_write_bytes", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt())
    )
    with pytest.raises(KeyboardInterrupt):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    monkeypatch.setattr(copying, "_write_bytes", original)
    before = action_log_path(root).read_bytes()
    assert (
        cli.main(
            [
                str(root),
                str(target),
                "--copy",
                "--copy-reserve-bytes",
                "0",
                "--recover",
                "--apply",
                "--migration-decision-digest",
                "0" * 64,
            ]
        )
        == 1
    )
    assert action_log_path(root).read_bytes() == before
    assert not target.exists()


def test_real_distinct_filesystem_copy(tmp_path: Path) -> None:
    root, _ = collection(tmp_path)
    candidate = os.environ.get("PYMO_TEST_CROSS_DEVICE_ROOT", "/dev/shm")
    parent = Path(candidate)
    if not parent.is_dir() or parent.stat().st_dev == root.stat().st_dev:
        pytest.skip("a distinct writable filesystem is required")
    with tempfile.TemporaryDirectory(prefix="pymo-synthetic-", dir=parent) as temporary:
        target = Path(temporary) / "retained"
        plan = copying.plan_copy(root, target, 0)
        copying.apply_copy(plan)
        copying.recover_copy(root, target, 0)
        assert media(root / "dups") == media(target)


@pytest.mark.parametrize(
    "attack",
    [
        "binding",
        "stage-device",
        "scratch-alias",
        "completion-order",
        "missing-stage",
        "scratch-before-stage-complete",
    ],
)
def test_copy_journal_rejects_inconsistent_lifecycle(
    tmp_path: Path, simulated_devices: None, attack: str
) -> None:
    root, target = collection(tmp_path)
    copying.apply_copy(copying.plan_copy(root, target, 0))
    events = [
        json.loads(line) for line in action_log_path(root).read_text().splitlines()
    ]
    planned = [event for event in events if event["event"] == "ACTION_PLANNED"]
    if attack == "binding":
        planned[2]["action"]["after"] += ":extra"
    elif attack == "stage-device":
        planned[1]["action"]["identity"]["device"] += 1
    elif attack == "scratch-alias":
        planned[2]["action"]["identity"] = dict(planned[1]["action"]["identity"])
    elif attack == "completion-order":
        completions = [
            event for event in events if event["event"] == "ACTION_COMPLETED"
        ]
        completions[0]["action_id"], completions[-1]["action_id"] = (
            completions[-1]["action_id"],
            completions[0]["action_id"],
        )
    elif attack == "scratch-before-stage-complete":
        stage_complete = next(
            event
            for event in events
            if event["event"] == "ACTION_COMPLETED"
            and event["action_id"] == planned[1]["action_id"]
        )
        events.remove(stage_complete)
        events.insert(events.index(planned[2]) + 1, stage_complete)
    else:
        events.remove(planned[1])
    with pytest.raises(ActionLogError):
        ActionLog(root)._runs(events)


def test_retained_target_change_during_final_source_check_prevents_commit(
    tmp_path: Path, simulated_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = collection(tmp_path)
    original = copying._manifest_at

    def change_after_target_verification(
        parent: int, name: str
    ) -> copying.TreeManifest:
        result = original(parent, name)
        if target.exists():
            (target / "second.bin").write_bytes(b"tampered")
        return result

    monkeypatch.setattr(copying, "_manifest_at", change_after_target_verification)
    with pytest.raises(
        ManagedQuarantineError,
        match=r"changed before journal commit|changed after publication",
    ):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    events = [
        json.loads(line) for line in action_log_path(root).read_text().splitlines()
    ]
    assert not any(event["event"] == "RUN_COMMITTED" for event in events)
    assert (root / "dups" / "second.bin").read_bytes() == b"second content"


@pytest.mark.parametrize("surface", ["stage", "scratch", "published"])
def test_bound_directory_swap_between_check_and_open_is_refused(
    tmp_path: Path,
    simulated_devices: None,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    from contextlib import contextmanager

    root, target = collection(tmp_path)
    original = copying._child_directory
    attacked = False

    @contextmanager
    def swapped(parent: int, name: str, expected: tuple[int, int] | None = None):
        nonlocal attacked
        selected = (
            (surface == "scratch" and name.endswith("-partial"))
            or (
                surface == "stage"
                and name.startswith(".pymo-copy-")
                and not name.endswith("-partial")
            )
            or (surface == "published" and name == target.name)
        )
        if expected is not None and selected and not attacked:
            attacked = True
            os.rename(name, name + "-saved", src_dir_fd=parent, dst_dir_fd=parent)
            os.mkdir(name, dir_fd=parent)
        with original(parent, name, expected) as descriptor:
            yield descriptor

    monkeypatch.setattr(copying, "_child_directory", swapped)
    before = media(root / "dups")
    with pytest.raises(ManagedQuarantineError, match="changed before opening"):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    assert attacked
    assert media(root / "dups") == before
    events = [
        json.loads(line) for line in action_log_path(root).read_text().splitlines()
    ]
    assert not any(event["event"] == "RUN_COMMITTED" for event in events)


def test_copy_settings_are_rejected_before_private_state_creation(
    tmp_path: Path,
) -> None:
    from pymo import migrate

    baseline = tmp_path / "baseline"
    working = tmp_path / "working"
    private = tmp_path / "private"
    baseline.mkdir()
    working.mkdir()
    with pytest.raises(SystemExit) as error:
        migrate.main(
            [
                str(baseline),
                str(working),
                "--log-dir",
                str(private),
                "--start",
                "--quarantine-copy-reserve-bytes",
                "0",
            ]
        )
    assert error.value.code == 2
    assert not private.exists()


def test_journal_creation_is_anchored_if_collection_path_is_replaced(
    tmp_path: Path, simulated_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import contextmanager

    root, target = collection(tmp_path)
    plan = copying.plan_copy(root, target, 0)
    original = ActionLog._locked
    parked = root.with_name("parked")
    before = media(root / "dups")

    @contextmanager
    def replaced(log: ActionLog, create: bool, **kwargs):
        root.rename(parked)
        root.mkdir()
        with original(log, create, **kwargs) as handle:
            yield handle

    monkeypatch.setattr(ActionLog, "_locked", replaced)
    with pytest.raises(ManagedQuarantineError, match="changed"):
        copying.apply_copy(plan)
    assert list(root.iterdir()) == []
    assert media(parked / "dups") == before
    assert not target.exists()


@pytest.mark.parametrize("history", ["absent", "committed", "incomplete", "malformed"])
def test_recovery_retries_prejournal_failure_only_with_safe_history(
    tmp_path: Path, simulated_devices: None, history: str
) -> None:
    root, target = collection(tmp_path)
    if history in {"committed", "incomplete"}:
        with ActionLog(root).transaction("organize_media") as transaction:
            if history == "committed":
                transaction.commit()
    elif history == "malformed":
        action_log_path(root).write_text("not a journal\n")
    status = cli.main(
        [
            str(root),
            str(target),
            "--copy",
            "--copy-reserve-bytes",
            "0",
            "--recover",
            "--apply",
        ]
    )
    if history in {"absent", "committed"}:
        assert status == 0
        assert media(target) == media(root / "dups")
    else:
        assert status == 1
        assert not target.exists()


def test_bound_copy_refuses_duplicate_owner_transactions_before_new_journal_run(
    tmp_path: Path, simulated_devices: None
) -> None:
    from pymo.action_log import ActionTransaction, ToolId

    root, target = collection(tmp_path)
    copying.apply_copy(copying.plan_copy(root, target, 0))
    log = ActionLog(root)
    before = log.path.read_bytes()
    for tool in (
        ToolId.IMAGE_DUPLICATES,
        ToolId.VIDEO_DUPLICATES,
        ToolId.MANAGED_QUARANTINE,
    ):
        with log._locked(create=False, write_existing=True) as handle:
            with pytest.raises(ActionLogError, match="protects"):
                ActionTransaction(log, handle, tool=tool.value)
        assert log.path.read_bytes() == before
    copying.verify_copy(root, target, 0)


@pytest.mark.parametrize("attack", ["injected", "replacement"])
def test_unbound_or_replaced_scratch_leaf_is_never_adopted(
    tmp_path: Path,
    simulated_devices: None,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    import uuid

    root, target = collection(tmp_path)
    original = copying._write_bytes
    monkeypatch.setattr(
        copying, "_write_bytes", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt())
    )
    with pytest.raises(KeyboardInterrupt):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    scratch = next(target.parent.glob("*-partial"))
    if attack == "injected":
        unexpected = scratch / str(uuid.uuid4())
    else:
        unexpected = next(scratch.iterdir())
        unexpected.rename(target.parent / "saved-partial")
    unexpected.write_bytes(b"unrelated")
    before = action_log_path(root).read_bytes()
    monkeypatch.setattr(copying, "_write_bytes", original)
    with pytest.raises(ManagedQuarantineError, match="unrecorded or replaced"):
        copying.recover_copy(root, target, 0)
    assert action_log_path(root).read_bytes() == before
    assert unexpected.read_bytes() == b"unrelated"
    assert not target.exists()


@pytest.mark.parametrize("recorded", [False, True])
def test_interrupted_scratch_leaf_record_requires_exact_recorded_identity(
    tmp_path: Path,
    simulated_devices: None,
    monkeypatch: pytest.MonkeyPatch,
    recorded: bool,
) -> None:
    root, target = collection(tmp_path)
    original = ActionLog._append

    def stop(log, handle, event):
        if (
            event["event"] == "ACTION_PLANNED"
            and event["action"]["operation"] == "COPY_QUARANTINE_ARTIFACT"
        ):
            if recorded:
                original(log, handle, event)
            raise KeyboardInterrupt
        original(log, handle, event)

    monkeypatch.setattr(ActionLog, "_append", stop)
    with pytest.raises(KeyboardInterrupt):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    monkeypatch.setattr(ActionLog, "_append", original)
    if recorded:
        copying.recover_copy(root, target, 0)
        assert media(target) == media(root / "dups")
    else:
        with pytest.raises(ManagedQuarantineError, match="unrecorded"):
            copying.recover_copy(root, target, 0)
        assert not target.exists()


def test_missing_recorded_partial_prevents_recovery_commit(
    tmp_path: Path, simulated_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = collection(tmp_path)
    original = copying._write_bytes

    def partial(source, destination):
        os.write(destination, b"partial")
        raise KeyboardInterrupt

    monkeypatch.setattr(copying, "_write_bytes", partial)
    with pytest.raises(KeyboardInterrupt):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    scratch = next(target.parent.glob("*-partial"))
    artifact = next(scratch.iterdir())
    saved = target.parent / "externally-retained-partial"
    artifact.rename(saved)
    before = action_log_path(root).read_bytes()
    monkeypatch.setattr(copying, "_write_bytes", original)
    with pytest.raises(ManagedQuarantineError, match="missing"):
        copying.recover_copy(root, target, 0)
    assert not target.exists()
    assert saved.read_bytes() == b"partial"
    assert action_log_path(root).read_bytes() == before


def test_file_publication_interruption_accounts_for_the_exact_staged_artifact(
    tmp_path: Path, simulated_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = collection(tmp_path)
    original = copying._atomic_rename_without_replace
    staged_inode = None

    def interrupted(source_parent, source_name, destination_parent, destination_name):
        nonlocal staged_inode
        original(source_parent, source_name, destination_parent, destination_name)
        if destination_name == "first.bin":
            staged_inode = os.stat(destination_name, dir_fd=destination_parent).st_ino
            raise KeyboardInterrupt

    monkeypatch.setattr(copying, "_atomic_rename_without_replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    monkeypatch.setattr(copying, "_atomic_rename_without_replace", original)
    copying.recover_copy(root, target, 0)
    assert (target / "pics" / "first.bin").stat().st_ino == staged_inode
    assert media(target) == media(root / "dups")


def test_equal_bytes_in_unrecorded_staged_file_do_not_inherit_copy_authority(
    tmp_path: Path, simulated_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = collection(tmp_path)
    original = copying._write_bytes
    monkeypatch.setattr(
        copying, "_write_bytes", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt())
    )
    with pytest.raises(KeyboardInterrupt):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    stage = next(
        path
        for path in target.parent.glob(".pymo-copy-*")
        if not path.name.endswith("-partial")
    )
    (stage / "pics" / "first.bin").write_bytes(
        (root / "dups" / "pics" / "first.bin").read_bytes()
    )
    monkeypatch.setattr(copying, "_write_bytes", original)
    with pytest.raises(ManagedQuarantineError, match="unrecorded copied file"):
        copying.recover_copy(root, target, 0)
    assert not target.exists()


def test_source_change_during_final_artifact_accounting_refuses_commit(
    tmp_path: Path, simulated_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = collection(tmp_path)
    original = copying._scratch_evidence

    def changed(descriptor, tree, artifacts):
        result = original(descriptor, tree, artifacts)
        if target.exists():
            (root / "dups" / "second.bin").write_bytes(b"external change")
        return result

    monkeypatch.setattr(copying, "_scratch_evidence", changed)
    with pytest.raises(ManagedQuarantineError, match="source changed"):
        copying.apply_copy(copying.plan_copy(root, target, 0))
    events = [
        json.loads(line) for line in action_log_path(root).read_text().splitlines()
    ]
    assert not any(event["event"] == "RUN_COMMITTED" for event in events)
