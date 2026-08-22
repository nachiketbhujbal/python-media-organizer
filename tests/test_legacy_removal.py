from __future__ import annotations

from pathlib import Path


def test_organizer_rejects_removed_manifest_option(tmp_path: Path, run_script) -> None:
    result = run_script(
        "organize_media.py", tmp_path, "--undo", "--manifest", "old.csv"
    )

    assert result.returncode == 2
    assert "unrecognized arguments: --manifest" in result.stderr


def test_image_finder_rejects_removed_group_migration_options(
    tmp_path: Path, run_script
) -> None:
    (tmp_path / "pics").mkdir()

    for arguments in (
        ("--recursive",),
        ("--reorganize-existing",),
        ("--duplicates-dir", "duplicates"),
    ):
        result = run_script("find_image_duplicates.py", tmp_path, *arguments)

        assert result.returncode == 2
        assert "unrecognized arguments" in result.stderr


def test_fixed_action_log_name_is_no_longer_detected(
    tmp_path: Path, run_script
) -> None:
    (tmp_path / "pics").mkdir()
    (tmp_path / "vids").mkdir()
    fixed_name = tmp_path / "media_actions.jsonl"
    fixed_name.write_text("", encoding="utf-8")

    result = run_script("rename_media.py", tmp_path, "--undo")

    assert result.returncode == 2
    assert "no action log found" in result.stderr
    assert fixed_name.is_file()
