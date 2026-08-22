from __future__ import annotations

import json
from pathlib import Path

import pytest

from pymo.action_log import (
    Action,
    ActionConflict,
    ActionLog,
    NoUndoableRun,
    action_log_path,
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
