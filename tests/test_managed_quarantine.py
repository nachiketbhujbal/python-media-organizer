from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import pytest

from pymo import managed_quarantine as quarantine_module
from pymo import quarantine as quarantine_cli
from pymo.action_log import (
    Action,
    ActionLog,
    ActionLogError,
    ActionTransaction,
    action_log_path,
)
from pymo.managed_quarantine import (
    ManagedQuarantineError,
    apply_managed_quarantine,
    apply_managed_quarantine_undo,
    destination_binding_sha256,
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
        "after": (
            "external:"
            + destination_binding_sha256(target)
            + f":{target.parent.stat().st_dev}:{target.parent.stat().st_ino}"
        ),
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


def test_undo_refuses_same_tree_moved_to_a_different_explicit_target(
    tmp_path: Path,
) -> None:
    root, _ = _collection(tmp_path)
    recorded_target = tmp_path.resolve() / "recorded-target"
    substituted_target = tmp_path.resolve() / "substituted-target"
    apply_managed_quarantine(plan_managed_quarantine(root, recorded_target))
    recorded_target.rename(substituted_target)

    with pytest.raises(
        ManagedQuarantineError, match="target does not match the journal"
    ):
        plan_managed_quarantine_undo(root, substituted_target)


def test_active_quarantine_blocks_undo_of_actions_inside_dups(tmp_path: Path) -> None:
    root = tmp_path.resolve() / "collection"
    source = root / "pics" / "copy.jpg"
    target_in_dups = root / "dups" / "pics" / "copy.jpg"
    source.parent.mkdir(parents=True)
    target_in_dups.parent.mkdir(parents=True)
    source.write_bytes(b"content")
    log = ActionLog(root)
    with log.transaction("find_image_duplicates") as transaction:
        transaction.perform(Action.for_file(root, source, target_in_dups, "MOVE"))
        transaction.commit()
    retained = tmp_path.resolve() / "retained"
    apply_managed_quarantine(plan_managed_quarantine(root, retained))

    with pytest.raises(ActionLogError, match="later active run"):
        log.plan_undo("find_image_duplicates")


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


def test_apply_refuses_a_substituted_destination_parent_before_journaling(
    tmp_path: Path,
) -> None:
    root, review = _collection(tmp_path)
    target_parent = tmp_path.resolve() / "retained"
    target_parent.mkdir()
    target = target_parent / "review-tree"
    plan = plan_managed_quarantine(root, target)
    displaced = tmp_path.resolve() / "displaced-retained"
    target_parent.rename(displaced)
    target_parent.mkdir()

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


def test_reconcile_marks_an_empty_interrupted_apply_as_not_complete(
    tmp_path: Path,
) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "target"
    log = ActionLog(root)
    with log._locked(create=True) as handle:
        ActionTransaction(log, handle, tool="managed_quarantine")  # RUN_STARTED only.

    reconciled = reconcile_managed_quarantine(root, target)

    assert reconciled.reconciled
    assert not reconciled.disposition_complete
    assert review.is_dir()
    assert not target.exists()


def test_cli_recovery_retries_the_reviewed_move_after_an_empty_journal_run(
    tmp_path: Path,
) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "target"
    log = ActionLog(root)
    with log._locked(create=True) as handle:
        ActionTransaction(log, handle, tool="managed_quarantine")

    assert quarantine_cli.main([str(root), str(target), "--recover", "--apply"]) == 0

    assert not review.exists()
    assert (target / "pics" / "one.bin").read_bytes() == b"first"
    undo = plan_managed_quarantine_undo(root, target)
    assert undo.manifest.file_count == 2


def test_standalone_cli_is_preview_first_reversible_and_exact(tmp_path: Path) -> None:
    root, review = _collection(tmp_path)
    target = tmp_path.resolve() / "target"

    assert quarantine_cli.main([str(root), str(target)]) == 0
    assert review.is_dir()
    assert not target.exists()

    assert quarantine_cli.main([str(root), str(target), "--apply"]) == 0
    assert not review.exists()
    assert target.is_dir()

    assert quarantine_cli.main([str(root), str(target), "--undo"]) == 0
    assert not review.exists()
    assert target.is_dir()

    assert quarantine_cli.main([str(root), str(target), "--undo", "--apply"]) == 0
    assert review.is_dir()
    assert not target.exists()


def test_reconcile_can_reobserve_a_committed_move_without_rewriting_journal(
    tmp_path: Path,
) -> None:
    root, _ = _collection(tmp_path)
    target = tmp_path.resolve() / "target"
    applied = apply_managed_quarantine(plan_managed_quarantine(root, target))
    before = action_log_path(root).read_bytes()

    observed = reconcile_managed_quarantine(root, target)

    assert observed.run_id == applied.run_id
    assert observed.reconciled
    assert observed.file_count == 2
    assert action_log_path(root).read_bytes() == before


def test_coordinator_bound_recovery_refuses_a_replaced_destination_parent(
    tmp_path: Path,
) -> None:
    root, review = _collection(tmp_path)
    target_parent = tmp_path.resolve() / "retained"
    target_parent.mkdir()
    target = target_parent / "review-tree"
    private = tmp_path.resolve() / "private"
    private.mkdir()
    preview_outcome = private / "preview.json"
    assert (
        quarantine_cli.main(
            [
                str(root),
                str(target),
                "--migration-outcome",
                str(preview_outcome),
            ]
        )
        == 0
    )
    digest = json.loads(preview_outcome.read_text(encoding="utf-8"))["data"][
        "decision_digest"
    ]
    assert (
        quarantine_cli.main(
            [
                str(root),
                str(target),
                "--migration-decision-digest",
                digest,
                "--apply",
            ]
        )
        == 0
    )
    assert not review.exists()

    displaced = tmp_path.resolve() / "displaced-retained"
    target_parent.rename(displaced)
    target_parent.mkdir()
    (displaced / "review-tree").rename(target)
    recovery_outcome = private / "recovery.json"

    assert (
        quarantine_cli.main(
            [
                str(root),
                str(target),
                "--recover",
                "--migration-outcome",
                str(recovery_outcome),
                "--migration-decision-digest",
                digest,
                "--apply",
            ]
        )
        == 1
    )
    assert not recovery_outcome.exists()
    assert target.is_dir()

    # A normal undo is a separately reviewed plan bound to the current parent.
    undo = plan_managed_quarantine_undo(root, target)
    assert undo.target_parent_inode == target_parent.stat().st_ino
    apply_managed_quarantine_undo(undo)
    assert review.is_dir()
    assert not target.exists()


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


@pytest.mark.parametrize(
    ("tool", "before", "after", "identity"),
    (
        (
            "organize_media",
            "dups",
            "external:" + "0" * 64 + ":1:2",
            {"size": 0, "sha256": "0" * 64, "device": 1, "inode": 2},
        ),
        (
            "managed_quarantine",
            "other",
            "external:" + "0" * 64 + ":1:2",
            {"size": 0, "sha256": "0" * 64, "device": 1, "inode": 2},
        ),
        (
            "managed_quarantine",
            "dups",
            "external:" + "0" * 64 + ":1:2",
            {"size": 0, "sha256": "short", "device": 1, "inode": 2},
        ),
        (
            "managed_quarantine",
            "dups",
            "external:" + "0" * 64 + ":+1:02",
            {"size": 0, "sha256": "0" * 64, "device": 1, "inode": 2},
        ),
    ),
)
def test_quarantine_journal_requires_exact_action_and_tool_semantics(
    tmp_path: Path,
    tool: str,
    before: str,
    after: str,
    identity: dict[str, int | str],
) -> None:
    root, _ = _collection(tmp_path)
    action = {
        "operation": "QUARANTINE_TREE",
        "before": before,
        "after": after,
        "entry_type": "directory",
        "identity": identity,
    }
    events = [
        {
            "schema_version": 1,
            "timestamp": "2026-09-13T00:00:00+00:00",
            "event": "RUN_STARTED",
            "run_id": "run-1",
            "tool": tool,
            "mode": "APPLY",
            "target_run_id": None,
        },
        {
            "schema_version": 1,
            "timestamp": "2026-09-13T00:00:01+00:00",
            "event": "ACTION_PLANNED",
            "run_id": "run-1",
            "action_id": "action-1",
            "action": action,
        },
    ]
    action_log_path(root).write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    with pytest.raises(ActionLogError):
        ActionLog(root).plan_undo(tool)
