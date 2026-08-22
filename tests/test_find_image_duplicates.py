from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from pymo.action_log import action_log_path
from pymo.duplicates import images as image_duplicates


def make_organized_collection(root: Path) -> tuple[Path, Path]:
    pics = root / "pics"
    vids = root / "vids"
    pics.mkdir(parents=True)
    vids.mkdir()
    return pics, vids


def test_duplicate_finder_stays_dry_run_until_apply(tmp_path: Path, run_script) -> None:
    pics, vids = make_organized_collection(tmp_path)
    (pics / ".DS_Store").write_bytes(b"finder metadata")
    (vids / ".DS_Store").write_bytes(b"finder metadata")
    older = pics / "older.png"
    larger = pics / "larger.png"
    Image.new("RGB", (4, 3), "purple").save(older)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("note", "metadata makes this retained copy larger")
    Image.new("RGB", (4, 3), "purple").save(larger, pnginfo=metadata)
    os.utime(older, ns=(1_600_000_000_000_000_000,) * 2)

    dry_run = run_script("find_image_duplicates.py", tmp_path)

    assert dry_run.returncode == 0
    assert "Ignored by configuration: 1 path(s)." in dry_run.stdout
    assert "Would move 1 duplicate" in dry_run.stdout
    assert "Potentially reclaimable if extra copies were deleted" in dry_run.stdout
    assert "No files are deleted by this tool" in dry_run.stdout
    assert older.exists()
    assert larger.exists()
    assert not (tmp_path / "dups").exists()
    assert not action_log_path(tmp_path).exists()

    applied = run_script("find_image_duplicates.py", tmp_path, "--apply")

    assert applied.returncode == 0
    assert larger.exists()
    assert not older.exists()
    moved = tmp_path / "dups" / "pics" / "larger_copy(1).png"
    assert moved.exists()
    assert not (tmp_path / "dups" / "vids").exists()
    assert action_log_path(tmp_path).exists()
    assert not (tmp_path / "dups" / "pics" / "move_manifest.csv").exists()

    undone = run_script("find_image_duplicates.py", tmp_path, "--undo", "--apply")

    assert undone.returncode == 0, undone.stdout + undone.stderr
    assert older.exists()
    assert larger.exists()
    assert not (tmp_path / "dups").exists()
    assert action_log_path(tmp_path).exists()


def test_image_summary_applies_with_path_private_aggregate_output(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "private-garden-collection"
    pics, _ = make_organized_collection(root)
    first = pics / "secret-fern.png"
    second = pics / "secret-moss.png"
    broken = pics / "secret-broken.png"
    Image.new("RGB", (3, 2), "green").save(first)
    Image.new("RGB", (3, 2), "green").save(second)
    broken.write_bytes(b"not an image")

    result = run_script("find_image_duplicates.py", root, "--summary", "--apply")

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Scanning 3 image(s)" in result.stdout
    assert "Moved 1 duplicate(s) from 1 group(s)" in result.stdout
    assert "Skipped 1 file(s)." in result.stdout
    assert "Duplicate storage summary:" in result.stdout
    assert "Action log updated." in result.stdout
    assert "Group 1:" not in output
    assert "duplicate:" not in output
    assert "Action log:" not in output
    for private_text in (root.name, first.name, second.name, broken.name, str(root)):
        assert private_text not in output
    assert action_log_path(root).is_file()

    undo_preview = run_script("find_image_duplicates.py", root, "--summary", "--undo")

    undo_output = undo_preview.stdout + undo_preview.stderr
    assert undo_preview.returncode == 0, undo_output
    assert "Would reverse" in undo_preview.stdout
    assert "Using action log:" not in undo_output
    assert "Duplicate-finder run:" not in undo_output
    for private_text in (root.name, first.name, second.name, broken.name, str(root)):
        assert private_text not in undo_output


def test_image_summary_refuses_explicit_ignored_paths(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "private-garden-collection"
    make_organized_collection(root)

    result = run_script("find_image_duplicates.py", root, "--summary", "--show-ignored")

    assert result.returncode == 2
    assert "cannot be combined" in result.stderr
    assert root.name not in result.stdout + result.stderr


def test_duplicate_finder_honors_custom_file_rules(tmp_path: Path, run_script) -> None:
    pics, _ = make_organized_collection(tmp_path)
    original = pics / "original.png"
    protected_copy = pics / "protected-copy.png"
    Image.new("RGB", (2, 2), "teal").save(original)
    Image.new("RGB", (2, 2), "teal").save(protected_copy)
    (tmp_path / ".pymo.toml").write_text(
        'version = 1\n\n[ignore]\nfiles = ["protected-copy.png"]\n',
        encoding="utf-8",
    )

    result = run_script(
        "find_image_duplicates.py", tmp_path, "--show-ignored", "--apply"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Scanning 1 image(s)" in result.stdout
    assert "Ignored by configuration: 1 path(s)." in result.stdout
    assert "Ignored paths:" in result.stdout
    assert "  pics/protected-copy.png" in result.stdout
    assert "Moved 0 duplicate(s)" in result.stdout
    assert original.exists()
    assert protected_copy.exists()
    assert not action_log_path(tmp_path).exists()


def test_duplicate_finder_uses_custom_inspection_extensions(
    tmp_path: Path, run_script
) -> None:
    pics, _ = make_organized_collection(tmp_path)
    first = pics / "first.flower"
    second = pics / "second.flower"
    Image.new("RGB", (2, 2), "green").save(first, format="PNG")
    Image.new("RGB", (2, 2), "green").save(second, format="PNG")
    (tmp_path / ".pymo.toml").write_text(
        "version = 1\n" "[image_duplicates]\n" 'extensions = [".flower"]\n',
        encoding="utf-8",
    )

    result = run_script("find_image_duplicates.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Scanning 2 image(s)" in result.stdout
    assert "Would move 1 duplicate" in result.stdout
    assert first.exists()
    assert second.exists()


def test_duplicate_finder_requires_organized_collection_root(
    tmp_path: Path, run_script
) -> None:
    Image.new("RGB", (2, 2), "red").save(tmp_path / "photo.png")

    result = run_script("find_image_duplicates.py", tmp_path)

    assert result.returncode == 2
    assert "Collection is not ready for duplicate scanning" in result.stderr
    assert "missing required folder" in result.stderr
    assert "Run pymo organize" in result.stderr
    assert not action_log_path(tmp_path).exists()


def test_duplicate_finder_ignores_video_folder_state(
    tmp_path: Path, run_script
) -> None:
    pics = tmp_path / "pics"
    pics.mkdir()
    (tmp_path / "videos").mkdir()
    dups = tmp_path / "dups"
    dups.mkdir()
    (dups / "vids").write_text("owned by the video finder", encoding="utf-8")

    result = run_script("find_image_duplicates.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Scanning 0 image(s)" in result.stdout
    assert (dups / "vids").read_text(encoding="utf-8") == "owned by the video finder"


def test_duplicate_finder_never_overwrites_review_files(
    tmp_path: Path, run_script
) -> None:
    pics, _ = make_organized_collection(tmp_path)
    first = pics / "first.png"
    second = pics / "second.png"
    Image.new("RGB", (2, 2), "orange").save(first)
    Image.new("RGB", (2, 2), "orange").save(second)
    duplicate_dir = tmp_path / "dups" / "pics"
    duplicate_dir.mkdir(parents=True)
    (tmp_path / "dups" / "vids").mkdir()
    occupied = duplicate_dir / "first_copy(1).png"
    occupied.write_text("do not overwrite", encoding="utf-8")

    result = run_script("find_image_duplicates.py", tmp_path, "--apply")

    assert result.returncode == 0
    assert occupied.read_text(encoding="utf-8") == "do not overwrite"
    assert (duplicate_dir / "first_copy(2).png").exists()


def test_full_workflow_must_be_undone_in_reverse_order(
    tmp_path: Path, run_script
) -> None:
    first = tmp_path / "first" / "photo.png"
    second = tmp_path / "second" / "copy.png"
    first.parent.mkdir()
    second.parent.mkdir()
    Image.new("RGB", (3, 2), "green").save(first)
    Image.new("RGB", (3, 2), "green").save(second)

    assert run_script("organize_media.py", tmp_path, "--apply").returncode == 0
    assert run_script("rename_media.py", tmp_path, "--apply").returncode == 0
    duplicate_run = run_script("find_image_duplicates.py", tmp_path, "--apply")
    assert duplicate_run.returncode == 0, duplicate_run.stdout + duplicate_run.stderr

    blocked = run_script("rename_media.py", tmp_path, "--undo", "--apply")
    assert blocked.returncode == 1
    assert "find_image_duplicates" in blocked.stderr

    assert (
        run_script("find_image_duplicates.py", tmp_path, "--undo", "--apply").returncode
        == 0
    )
    assert run_script("rename_media.py", tmp_path, "--undo", "--apply").returncode == 0
    final_undo = run_script("organize_media.py", tmp_path, "--undo", "--apply")
    assert final_undo.returncode == 0, final_undo.stdout + final_undo.stderr
    assert first.exists()
    assert second.exists()


def test_image_inspection_rejects_a_file_changed_during_decode(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "changing.png"
    Image.new("RGB", (2, 2), "green").save(path)
    original_hash = image_duplicates.displayed_pixel_hash

    def mutate_after_hash(descriptor: int) -> str:
        result = original_hash(descriptor)
        Image.new("RGB", (3, 2), "blue").save(path)
        return result

    monkeypatch.setattr(image_duplicates, "displayed_pixel_hash", mutate_after_hash)

    with pytest.raises(
        image_duplicates.FileChangedError, match="changed during image analysis"
    ):
        image_duplicates.inspect_image(tmp_path, path)


def test_image_inspection_pins_decode_during_path_swap(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "collection"
    pics = root / "pics"
    pics.mkdir(parents=True)
    candidate = pics / "candidate.png"
    Image.new("RGB", (2, 2), "green").save(candidate)
    expected_source = tmp_path / "expected.png"
    Image.new("RGB", (2, 2), "green").save(expected_source)
    replacement = tmp_path / "replacement.png"
    Image.new("RGB", (3, 2), "blue").save(replacement)
    displaced = pics / "displaced.png"
    original_hash = image_duplicates.displayed_pixel_hash
    observed = ""

    descriptor = os.open(expected_source, os.O_RDONLY)
    try:
        expected = original_hash(descriptor)
    finally:
        os.close(descriptor)

    def swap_before_decode(descriptor: int) -> str:
        nonlocal observed
        candidate.rename(displaced)
        candidate.symlink_to(replacement)
        observed = original_hash(descriptor)
        return observed

    monkeypatch.setattr(image_duplicates, "displayed_pixel_hash", swap_before_decode)

    with pytest.raises(
        image_duplicates.FileChangedError, match="changed during image analysis"
    ):
        image_duplicates.inspect_image(root, candidate)

    assert observed == expected


def test_image_hash_promotes_decompression_bomb_warnings(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "large.png"
    Image.new("RGB", (4, 4), "green").save(path)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 4)

    descriptor = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(Image.DecompressionBombError):
            image_duplicates.displayed_pixel_hash(descriptor)
    finally:
        os.close(descriptor)


def test_image_apply_aborts_if_the_keeper_changes_after_planning(
    tmp_path: Path, monkeypatch
) -> None:
    pics, _ = make_organized_collection(tmp_path)
    keeper = pics / "keeper.png"
    duplicate = pics / "duplicate.png"
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("note", "make the retained file larger")
    Image.new("RGB", (2, 2), "green").save(keeper, pnginfo=metadata)
    Image.new("RGB", (2, 2), "green").save(duplicate)
    original_for_file = image_duplicates.Action.for_file

    def change_keeper_during_planning(*args, **kwargs):
        action = original_for_file(*args, **kwargs)
        Image.new("RGB", (3, 2), "blue").save(keeper)
        return action

    monkeypatch.setattr(
        image_duplicates.Action,
        "for_file",
        staticmethod(change_keeper_during_planning),
    )

    assert image_duplicates.main([str(tmp_path), "--apply"]) == 1
    assert keeper.exists()
    assert duplicate.exists()
    assert not (tmp_path / "dups").exists()
    assert not action_log_path(tmp_path).exists()
