from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import pytest

from pymo import managed_quarantine as quarantine_module
from pymo.action_log import (
    ActionLog,
    ActionLogError,
    ActionTransaction,
    action_log_path,
)
from pymo.managed_quarantine import (
    ManagedQuarantineError,
    apply_managed_quarantine,
    apply_managed_quarantine_undo,
    plan_managed_quarantine,
    plan_managed_quarantine_undo,
    reconcile_managed_quarantine,
)


def _collection(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path.resolve() / "collection"
    review = root / "dups"
    (review / "pics" / "nested").mkdir(parents=True)
    (review / "vids").mkdir()
    (review / "pics" / "one.bin").write_bytes(b"first")
    (review / "pics" / "nested" / "two.bin").write_bytes(b"second")
    return root, review


def test_plan_is_zero_write_and_manifest_is_deterministic(tmp_path: Path) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "retained" / "review-tree"
    target.parent.mkdir()
    before = sorted(path.relative_to(root) for path in root.rglob("*"))

    first = plan_managed_quarantine(root, target)
    second = plan_managed_quarantine(root, target)

    assert first == second
    assert first.manifest.file_count == 2
    assert first.manifest.directory_count == 4
    assert first.manifest.total_bytes == 11
    assert len(first.manifest.sha256) == 64
    assert review.is_dir()
    assert not target.exists()
    assert not action_log_path(root).exists()
    assert sorted(path.relative_to(root) for path in root.rglob("*")) == before


def test_apply_and_exact_undo_are_append_only_and_keep_external_path_private(
    tmp_path: Path,
) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "private-target-name"
    plan = plan_managed_quarantine(root, target)

    applied = apply_managed_quarantine(plan)

    assert applied.direction == "quarantine"
    assert applied.file_count == 2
    assert not review.exists()
    assert (target / "pics" / "one.bin").read_bytes() == b"first"
    journal = action_log_path(root)
    before_undo = journal.read_bytes()
    assert os.fsencode(target) not in before_undo
    events = [json.loads(line) for line in before_undo.splitlines()]
    planned = next(event for event in events if event["event"] == "ACTION_PLANNED")
    assert planned["action"] == {
        "after": None,
        "before": "dups",
        "entry_type": "directory",
        "identity": plan.manifest.journal_identity,
        "operation": "QUARANTINE_TREE",
    }

    undo = plan_managed_quarantine_undo(root, target)
    restored = apply_managed_quarantine_undo(undo)

    assert restored.direction == "restore"
    assert review.is_dir()
    assert not target.exists()
    assert journal.read_bytes().startswith(before_undo)
    with pytest.raises(ManagedQuarantineError, match="no managed quarantine"):
        plan_managed_quarantine_undo(root, target)


def test_stale_forged_apply_plan_creates_no_journal(tmp_path: Path) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "target"
    plan = plan_managed_quarantine(root, target)
    (review / "pics" / "one.bin").write_bytes(b"changed")

    with pytest.raises(ManagedQuarantineError, match="changed after planning"):
        apply_managed_quarantine(plan)

    assert review.is_dir()
    assert not target.exists()
    assert not action_log_path(root).exists()


@pytest.mark.parametrize("unsafe_kind", ["symlink", "hardlink"])
def test_plan_rejects_unsafe_tree_entries(tmp_path: Path, unsafe_kind: str) -> None:
    root, review = _collection(tmp_path)
    outside = tmp_path.resolve() / "outside.bin"
    outside.write_bytes(b"outside")
    unsafe = review / "unsafe.bin"
    if unsafe_kind == "symlink":
        unsafe.symlink_to(outside)
    else:
        unsafe.hardlink_to(outside)

    with pytest.raises(ManagedQuarantineError, match=r"unsafe|symbolic"):
        plan_managed_quarantine(root, tmp_path.resolve() / "target")
    assert review.is_dir()


def test_plan_rejects_unreadable_and_changing_trees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, review = _collection(tmp_path)
    review_inode = review.stat().st_ino
    real_listdir = quarantine_module.os.listdir

    def unreadable(descriptor: int) -> list[str]:
        if os.fstat(descriptor).st_ino == review_inode:
            raise PermissionError(errno.EACCES, "denied")
        return real_listdir(descriptor)

    monkeypatch.setattr(quarantine_module.os, "listdir", unreadable)
    with pytest.raises(ManagedQuarantineError, match="enumerated completely"):
        plan_managed_quarantine(root, tmp_path.resolve() / "target")

    monkeypatch.setattr(quarantine_module.os, "listdir", real_listdir)
    real_hash = quarantine_module._hash_file
    changed = False

    def change_during_hash(descriptor: int) -> str:
        nonlocal changed
        digest = real_hash(descriptor)
        if not changed:
            changed = True
            (review / "pics" / "one.bin").write_bytes(b"altered")
        return digest

    monkeypatch.setattr(quarantine_module, "_hash_file", change_during_hash)
    with pytest.raises(ManagedQuarantineError, match="changed during inspection"):
        plan_managed_quarantine(root, tmp_path.resolve() / "target")


def test_descriptor_pinned_inventory_never_reads_a_substituted_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = _collection(tmp_path)
    held = tmp_path.resolve() / "held-collection"
    observed: list[bytes] = []
    real_hash = quarantine_module._hash_file
    replaced = False

    def replace_collection(descriptor: int) -> str:
        nonlocal replaced
        observed.append(os.pread(descriptor, 64, 0))
        if not replaced:
            replaced = True
            root.rename(held)
            (root / "dups").mkdir(parents=True)
            (root / "dups" / "outside.bin").write_bytes(b"outside-secret")
        return real_hash(descriptor)

    monkeypatch.setattr(quarantine_module, "_hash_file", replace_collection)
    with pytest.raises(ManagedQuarantineError, match="identity changed"):
        plan_managed_quarantine(root, tmp_path.resolve() / "target")

    assert b"outside-secret" not in observed
    assert (root / "dups" / "outside.bin").read_bytes() == b"outside-secret"


def test_plan_rejects_nested_aliased_cross_device_and_occupied_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, review = _collection(tmp_path)

    with pytest.raises(ManagedQuarantineError, match="outside the collection"):
        plan_managed_quarantine(root, root / "nested-target")

    alias_parent = tmp_path.resolve() / "alias-parent"
    alias_parent.symlink_to(tmp_path.resolve(), target_is_directory=True)
    with pytest.raises(ManagedQuarantineError, match="ancestry"):
        plan_managed_quarantine(root, alias_parent / "target")

    occupied = tmp_path.resolve() / "occupied"
    occupied.mkdir()
    with pytest.raises(ManagedQuarantineError, match="occupied"):
        plan_managed_quarantine(root, occupied)

    real_check = quarantine_module._require_disjoint_same_filesystem

    def report_cross_device(collection, source, target_parent) -> None:
        altered = quarantine_module.TreeManifest(
            source.sha256,
            source.file_count,
            source.directory_count,
            source.total_bytes,
            source.device + 1,
            source.inode,
        )
        real_check(collection, altered, target_parent)

    monkeypatch.setattr(
        quarantine_module, "_require_disjoint_same_filesystem", report_cross_device
    )
    with pytest.raises(ManagedQuarantineError, match="cross-filesystem"):
        plan_managed_quarantine(root, tmp_path.resolve() / "target")
    assert review.is_dir()


def test_atomic_move_has_no_copy_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "target"
    plan = plan_managed_quarantine(root, target)

    def refuse_move(*_args) -> None:
        raise ManagedQuarantineError("cross-filesystem quarantine is not supported")

    monkeypatch.setattr(
        quarantine_module, "_atomic_rename_without_replace", refuse_move
    )
    with pytest.raises(ManagedQuarantineError, match="cross-filesystem"):
        apply_managed_quarantine(plan)

    assert review.is_dir()
    assert not target.exists()
    assert not any(path.name.endswith(".tmp") for path in tmp_path.rglob("*"))


def test_linux_atomic_move_uses_renameat2_noreplace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[object, ...]] = []

    class Rename:
        argtypes: object
        restype: object

        def __call__(self, *args: object) -> int:
            observed.append(args)
            return 0

    class Library:
        renameat2 = Rename()

    monkeypatch.setattr(quarantine_module.sys, "platform", "linux")
    monkeypatch.setattr(
        quarantine_module.ctypes, "CDLL", lambda *_args, **_kwargs: Library()
    )

    quarantine_module._atomic_rename_without_replace(3, "dups", 4, "retained")

    assert observed == [(3, b"dups", 4, b"retained", 0x01)]


def test_exact_post_move_verification_rejects_a_changed_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "target"
    plan = plan_managed_quarantine(root, target)
    real_rename = quarantine_module._atomic_rename_without_replace

    def move_then_change(*args) -> None:
        real_rename(*args)
        (target / "pics" / "one.bin").write_bytes(b"changed-after-move")

    monkeypatch.setattr(
        quarantine_module, "_atomic_rename_without_replace", move_then_change
    )
    with pytest.raises(ManagedQuarantineError, match="post-move verification"):
        apply_managed_quarantine(plan)

    assert not review.exists()
    assert target.is_dir()
    with pytest.raises(ManagedQuarantineError, match="changed"):
        reconcile_managed_quarantine(root, target)


def test_apply_reconciles_interruption_after_atomic_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "target"
    plan = plan_managed_quarantine(root, target)
    real_complete = ActionTransaction.complete

    def interrupt_after_move(self: ActionTransaction, action_id: str) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(ActionTransaction, "complete", interrupt_after_move)
    with pytest.raises(KeyboardInterrupt):
        apply_managed_quarantine(plan)
    assert not review.exists()
    assert target.is_dir()

    monkeypatch.setattr(ActionTransaction, "complete", real_complete)
    reconciled = reconcile_managed_quarantine(root, target)

    assert reconciled.reconciled
    assert reconciled.direction == "quarantine"
    assert reconciled.file_count == 2
    undo = plan_managed_quarantine_undo(root, target)
    assert undo.target_run_id == reconciled.run_id


def test_undo_reconciles_interruption_after_atomic_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "target"
    apply_managed_quarantine(plan_managed_quarantine(root, target))
    undo = plan_managed_quarantine_undo(root, target)
    real_complete = ActionTransaction.complete

    def interrupt_after_move(self: ActionTransaction, action_id: str) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(ActionTransaction, "complete", interrupt_after_move)
    with pytest.raises(KeyboardInterrupt):
        apply_managed_quarantine_undo(undo)
    assert review.is_dir()
    assert not target.exists()

    monkeypatch.setattr(ActionTransaction, "complete", real_complete)
    reconciled = reconcile_managed_quarantine(root, target)

    assert reconciled.reconciled
    assert reconciled.direction == "restore"
    assert reconciled.file_count == 2
    with pytest.raises(ManagedQuarantineError, match="no managed quarantine"):
        plan_managed_quarantine_undo(root, target)


def test_undo_requires_exact_unaltered_target_and_empty_source(tmp_path: Path) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "target"
    apply_managed_quarantine(plan_managed_quarantine(root, target))

    (target / "pics" / "one.bin").write_bytes(b"changed")
    with pytest.raises(ManagedQuarantineError, match="does not match"):
        plan_managed_quarantine_undo(root, target)

    (target / "pics" / "one.bin").write_bytes(b"first")
    review.mkdir()
    with pytest.raises(ManagedQuarantineError, match="occupied"):
        plan_managed_quarantine_undo(root, target)


def test_late_occupied_destination_is_refused_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "target"
    plan = plan_managed_quarantine(root, target)
    real_rename = quarantine_module._atomic_rename_without_replace

    def occupy_then_rename(*args) -> None:
        target.mkdir()
        real_rename(*args)

    monkeypatch.setattr(
        quarantine_module, "_atomic_rename_without_replace", occupy_then_rename
    )
    with pytest.raises(ManagedQuarantineError, match="occupied"):
        apply_managed_quarantine(plan)
    assert review.is_dir()
    assert target.is_dir()


def test_failures_do_not_disclose_collection_or_target_paths(tmp_path: Path) -> None:
    root, _ = _collection(tmp_path)
    target = tmp_path.resolve() / "sensitive-target-name"
    target.mkdir()

    with pytest.raises(ManagedQuarantineError) as raised:
        plan_managed_quarantine(root, target)

    message = str(raised.value)
    assert root.name not in message
    assert target.name not in message
    assert str(tmp_path.resolve()) not in message


def test_generic_undo_requires_the_dedicated_explicit_target_api(
    tmp_path: Path,
) -> None:
    root, _ = _collection(tmp_path)
    target = tmp_path.resolve() / "target"
    apply_managed_quarantine(plan_managed_quarantine(root, target))

    with pytest.raises(ActionLogError, match="explicit external target"):
        ActionLog(root).plan_undo("managed_quarantine")


def test_generic_transaction_cannot_create_a_managed_quarantine_run(
    tmp_path: Path,
) -> None:
    root, _ = _collection(tmp_path)

    with pytest.raises(ActionLogError, match="dedicated external-target"):
        with ActionLog(root).transaction("managed_quarantine"):
            pass

    assert not action_log_path(root).exists()


def test_malformed_quarantine_journal_action_fails_closed(tmp_path: Path) -> None:
    root, _ = _collection(tmp_path)
    events = [
        {
            "schema_version": 1,
            "timestamp": "2026-09-13T00:00:00+00:00",
            "event": "RUN_STARTED",
            "run_id": "run-1",
            "tool": "managed_quarantine",
            "mode": "APPLY",
            "target_run_id": None,
        },
        {
            "schema_version": 1,
            "timestamp": "2026-09-13T00:00:01+00:00",
            "event": "ACTION_PLANNED",
            "run_id": "run-1",
            "action_id": "action-1",
            "action": {
                "operation": "QUARANTINE_TREE",
                "before": "dups",
                "after": "external-path-must-not-be-recorded",
                "entry_type": "directory",
                "identity": {
                    "size": 0,
                    "sha256": "0" * 64,
                    "device": 1,
                    "inode": 2,
                },
            },
        },
    ]
    journal = action_log_path(root)
    journal.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    with pytest.raises(ActionLogError, match="requires a source tree"):
        ActionLog(root).plan_undo("managed_quarantine")
