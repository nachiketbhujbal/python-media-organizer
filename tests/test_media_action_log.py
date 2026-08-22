from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from pymo import action_log as action_log_module
from pymo import discovery
from pymo.action_log import (
    Action,
    ActionConflict,
    ActionLog,
    ActionLogError,
    NoUndoableRun,
    action_log_path,
    file_identity,
)


def test_append_only_log_records_apply_and_undo(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    destination = tmp_path / "pics" / "photo.jpg"
    source.write_bytes(b"photo bytes")
    destination.parent.mkdir()
    log = ActionLog(tmp_path)

    with log.transaction("organize_media") as transaction:
        transaction.perform(Action.for_file(tmp_path, source, destination, "MOVE"))
        transaction.commit()

    assert not source.exists()
    assert destination.read_bytes() == b"photo bytes"
    before_undo = action_log_path(tmp_path).read_bytes()

    plan = log.plan_undo("organize_media")
    assert plan.target.tool == "organize_media"
    assert plan.actions[0].before == "pics/photo.jpg"
    assert plan.actions[0].after == "photo.jpg"

    result = log.apply_undo("organize_media")

    assert result.action_count == 1
    assert source.read_bytes() == b"photo bytes"
    assert not destination.exists()
    after_undo = action_log_path(tmp_path).read_bytes()
    assert after_undo.startswith(before_undo)
    events = [json.loads(line) for line in after_undo.splitlines()]
    assert any(event["event"] == "RUN_COMMITTED" for event in events)
    assert any(event.get("target_run_id") == plan.target.run_id for event in events)
    with pytest.raises(NoUndoableRun):
        log.plan_undo("organize_media")


def test_later_rename_blocks_earlier_organize_undo(tmp_path: Path) -> None:
    original = tmp_path / "photo.jpg"
    organized = tmp_path / "pics" / "photo.jpg"
    renamed = tmp_path / "pics" / "collection__image_0001__undated.jpg"
    original.write_bytes(b"same file")
    organized.parent.mkdir()
    log = ActionLog(tmp_path)

    with log.transaction("organize_media") as transaction:
        transaction.perform(Action.for_file(tmp_path, original, organized, "MOVE"))
        transaction.commit()
    with log.transaction("rename_media") as transaction:
        transaction.perform(Action.for_file(tmp_path, organized, renamed, "RENAME"))
        transaction.commit()

    with pytest.raises(ActionConflict, match="rename_media"):
        log.plan_undo("organize_media")

    log.apply_undo("rename_media")
    log.apply_undo("organize_media")

    assert original.read_bytes() == b"same file"
    assert not organized.exists()
    assert not renamed.exists()


def test_incomplete_run_can_be_reversed_safely(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"recover me")
    log = ActionLog(tmp_path)

    with pytest.raises(RuntimeError, match="simulated interruption"):
        with log.transaction("organize_media") as transaction:
            transaction.perform(Action.for_file(tmp_path, source, destination, "MOVE"))
            raise RuntimeError("simulated interruption")

    assert destination.exists()
    plan = log.plan_undo("organize_media")
    assert plan.target.committed is False
    log.apply_undo("organize_media")
    assert source.read_bytes() == b"recover me"
    assert not destination.exists()

    another_source = tmp_path / "another.bin"
    another_target = tmp_path / "another-moved.bin"
    another_source.write_bytes(b"new run")
    with log.transaction("organize_media") as transaction:
        transaction.perform(
            Action.for_file(tmp_path, another_source, another_target, "MOVE")
        )
        transaction.commit()
    assert another_target.exists()


def test_undo_planning_refuses_an_incomplete_collection_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"stable content")
    log = ActionLog(tmp_path)
    with log.transaction("rename_media") as transaction:
        transaction.perform(Action.for_file(tmp_path, source, destination, "RENAME"))
        transaction.commit()
    before = action_log_path(tmp_path).read_bytes()

    def incomplete_walk(_root: Path, *, topdown: bool, onerror):
        assert topdown
        yield str(tmp_path), [], [destination.name, action_log_path(tmp_path).name]
        onerror(OSError(errno.EACCES, "permission denied", str(tmp_path / "closed")))

    monkeypatch.setattr(discovery.os, "walk", incomplete_walk)

    with pytest.raises(OSError, match="filesystem discovery was incomplete"):
        log.plan_undo("rename_media")
    assert destination.read_bytes() == b"stable content"
    assert action_log_path(tmp_path).read_bytes() == before


def test_undo_planning_refuses_an_enumerated_ghost_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"stable content")
    log = ActionLog(tmp_path)
    with log.transaction("rename_media") as transaction:
        transaction.perform(Action.for_file(tmp_path, source, destination, "RENAME"))
        transaction.commit()
    before = action_log_path(tmp_path).read_bytes()

    def ghost_walk(_root: Path, *, topdown: bool, onerror):
        assert topdown
        assert onerror is not None
        yield str(tmp_path), [], [
            destination.name,
            action_log_path(tmp_path).name,
            "vanished.bin",
        ]

    monkeypatch.setattr(discovery.os, "walk", ghost_walk)

    with pytest.raises(OSError, match="filesystem discovery was incomplete"):
        log.plan_undo("rename_media")
    assert destination.read_bytes() == b"stable content"
    assert action_log_path(tmp_path).read_bytes() == before


def test_same_size_content_change_blocks_undo(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"original")
    log = ActionLog(tmp_path)
    with log.transaction("rename_media") as transaction:
        transaction.perform(Action.for_file(tmp_path, source, destination, "RENAME"))
        transaction.commit()

    destination.write_bytes(b"modified")

    with pytest.raises(ActionConflict, match="no longer matches"):
        log.plan_undo("rename_media")
    assert destination.read_bytes() == b"modified"
    assert not source.exists()


def test_action_log_name_comes_from_media_collection_root(tmp_path: Path) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()

    assert action_log_path(root).name == "media-collection-actions-log.jsonl"


def test_symbolic_link_action_log_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-action-log.jsonl"
    outside.write_text("leave unchanged", encoding="utf-8")
    action_log_path(tmp_path).symlink_to(outside)

    with pytest.raises(ActionConflict, match="cannot be a symbolic link"):
        ActionLog(tmp_path)
    assert outside.read_text(encoding="utf-8") == "leave unchanged"


def test_action_log_open_does_not_follow_link_created_after_initialization(
    tmp_path: Path,
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    log = ActionLog(root)
    outside = tmp_path / "outside.jsonl"
    outside.write_text("leave unchanged", encoding="utf-8")
    log.path.symlink_to(outside)

    with pytest.raises(ActionConflict, match="cannot open action log safely"):
        log.plan_undo("organize_media")

    assert outside.read_text(encoding="utf-8") == "leave unchanged"


def test_hard_linked_action_log_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_text("leave unchanged", encoding="utf-8")
    action_log_path(root).hardlink_to(outside)

    with pytest.raises(ActionConflict, match="not a private regular file"):
        ActionLog(root).plan_undo("organize_media")

    assert outside.read_text(encoding="utf-8") == "leave unchanged"


def test_action_refuses_intermediate_symlink_introduced_after_planning(
    tmp_path: Path,
) -> None:
    root = tmp_path / "collection"
    nested = root / "nested"
    nested.mkdir(parents=True)
    source = nested / "source.bin"
    source.write_bytes(b"stable content")
    action = Action.for_file(root, source, root / "destination.bin", "MOVE")

    held = root / "held"
    nested.rename(held)
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_source = outside / "source.bin"
    outside_source.write_bytes(b"stable content")
    nested.symlink_to(outside, target_is_directory=True)

    log = ActionLog(root)
    with pytest.raises(ActionConflict, match="path parent is missing or unsafe"):
        with log.transaction("organize_media") as transaction:
            transaction.perform(action)

    assert outside_source.read_bytes() == b"stable content"
    assert (held / "source.bin").read_bytes() == b"stable content"
    assert not (root / "destination.bin").exists()


def test_atomic_move_refuses_a_destination_created_after_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"source content")
    destination.write_bytes(b"occupied content")
    action = Action.for_file(tmp_path, source, destination, "MOVE")
    real_lexists = action_log_module.os.path.lexists

    def hide_destination(path: object) -> bool:
        if Path(path) == destination:
            return False
        return real_lexists(path)

    monkeypatch.setattr(action_log_module.os.path, "lexists", hide_destination)

    with pytest.raises(ActionConflict, match="destination is occupied"):
        with ActionLog(tmp_path).transaction("organize_media") as transaction:
            transaction.perform(action)

    assert source.read_bytes() == b"source content"
    assert destination.read_bytes() == b"occupied content"


def test_file_identity_rejects_a_file_that_changes_while_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "changing.bin"
    path.write_bytes(b"original")
    original_sha256 = action_log_module._sha256

    def hash_then_change(candidate: Path) -> str:
        digest = original_sha256(candidate)
        candidate.write_bytes(b"modified")
        return digest

    monkeypatch.setattr(action_log_module, "_sha256", hash_then_change)

    with pytest.raises(ActionConflict, match="changed while identity"):
        file_identity(path)


def _write_events(root: Path, events: list[dict[str, object]]) -> None:
    path = action_log_path(root)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


def _event(name: str, **values: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "timestamp": "2026-08-22T00:00:00+00:00",
        "event": name,
        "run_id": "run-1",
        **values,
    }


@pytest.mark.parametrize(
    ("events", "message"),
    [
        (
            [
                _event(
                    "RUN_STARTED",
                    tool="organize_media",
                    mode="APPLY",
                    target_run_id=None,
                ),
                _event("UNRECOGNIZED"),
            ],
            "unknown action-log event",
        ),
        (
            [
                _event(
                    "RUN_STARTED",
                    tool="organize_media",
                    mode="APPLY",
                    target_run_id=None,
                ),
                _event("ACTION_COMPLETED", action_id="not-planned"),
            ],
            "was not planned",
        ),
        (
            [
                _event(
                    "RUN_STARTED",
                    tool="organize_media",
                    mode="APPLY",
                    target_run_id=None,
                ),
                _event("RUN_COMMITTED", action_count=1, target_run_id=None),
            ],
            "action count is inconsistent",
        ),
    ],
)
def test_malformed_action_lifecycle_fails_closed(
    tmp_path: Path, events: list[dict[str, object]], message: str
) -> None:
    _write_events(tmp_path, events)

    with pytest.raises(ActionLogError, match=message):
        ActionLog(tmp_path).plan_undo("organize_media")
