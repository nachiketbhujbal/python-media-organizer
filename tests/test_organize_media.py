from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image

from pymo.action_log import action_log_path


def make_fixture(root: Path) -> None:
    nested = root / "album" / "nested"
    nested.mkdir(parents=True)
    Image.new("RGB", (3, 2), "blue").save(nested / "photo.png")
    (nested / "clip.mp4").write_bytes(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    )
    (root / "album" / "notes.txt").write_text("notes", encoding="utf-8")


def test_organizer_dry_run_changes_nothing(tmp_path: Path, run_script) -> None:
    make_fixture(tmp_path)

    result = run_script("organize_media.py", tmp_path)

    assert result.returncode == 0
    assert "Dry run only" in result.stdout
    assert (tmp_path / "album" / "nested" / "photo.png").exists()
    assert (tmp_path / "album" / "nested" / "clip.mp4").exists()
    assert (tmp_path / "album" / "notes.txt").exists()
    assert not (tmp_path / "pics").exists()
    assert not (tmp_path / "vids").exists()
    assert not action_log_path(tmp_path).exists()


def test_organizer_apply_and_undo_restore_exact_structure(
    tmp_path: Path, run_script
) -> None:
    make_fixture(tmp_path)

    applied = run_script("organize_media.py", tmp_path, "--apply")

    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert (tmp_path / "pics" / "photo.png").exists()
    assert (tmp_path / "vids" / "clip.mp4").exists()
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "notes"
    assert not (tmp_path / "album").exists()
    log_path = action_log_path(tmp_path)
    before_undo = log_path.read_bytes()
    assert not (tmp_path / "organization_manifest.csv").exists()

    undone = run_script("organize_media.py", tmp_path, "--undo", "--apply")

    assert undone.returncode == 0, undone.stdout + undone.stderr
    assert (tmp_path / "album" / "nested" / "photo.png").exists()
    assert (tmp_path / "album" / "nested" / "clip.mp4").exists()
    assert (tmp_path / "album" / "notes.txt").read_text(encoding="utf-8") == "notes"
    assert not (tmp_path / "pics").exists()
    assert not (tmp_path / "vids").exists()
    after_undo = log_path.read_bytes()
    assert after_undo.startswith(before_undo)
    events = [json.loads(line) for line in after_undo.splitlines()]
    assert any(
        event.get("event") == "RUN_STARTED" and event.get("mode") == "UNDO"
        for event in events
    )


def test_organizer_undo_dry_run_preserves_organized_state(
    tmp_path: Path, run_script
) -> None:
    make_fixture(tmp_path)
    assert run_script("organize_media.py", tmp_path, "--apply").returncode == 0
    before = action_log_path(tmp_path).read_bytes()

    result = run_script("organize_media.py", tmp_path, "--undo")

    assert result.returncode == 0
    assert "Would reverse" in result.stdout
    assert (tmp_path / "pics" / "photo.png").exists()
    assert not (tmp_path / "album").exists()
    assert action_log_path(tmp_path).read_bytes() == before


def test_legacy_csv_manifest_can_still_be_undone(tmp_path: Path, run_script) -> None:
    pics = tmp_path / "pics"
    pics.mkdir()
    organized = pics / "photo.jpg"
    organized.write_bytes(b"legacy photo")
    original = tmp_path / "old" / "photo.jpg"
    manifest = tmp_path / "organization_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["kind", "mime_type", "moved_from", "moved_to"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "kind": "picture",
                "mime_type": "image/jpeg",
                "moved_from": str(original),
                "moved_to": str(organized),
            }
        )

    result = run_script("organize_media.py", tmp_path, "--undo", "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert original.read_bytes() == b"legacy photo"
    assert not organized.exists()
    assert not manifest.exists()
    assert not action_log_path(tmp_path).exists()


def test_organizer_preserves_reserved_dups_tree(tmp_path: Path, run_script) -> None:
    pics = tmp_path / "pics"
    vids = tmp_path / "vids"
    duplicate_pics = tmp_path / "dups" / "pics"
    duplicate_vids = tmp_path / "dups" / "vids"
    pics.mkdir()
    vids.mkdir()
    duplicate_pics.mkdir(parents=True)
    duplicate_vids.mkdir()
    Image.new("RGB", (2, 2), "blue").save(pics / "kept.png")
    Image.new("RGB", (2, 2), "blue").save(duplicate_pics / "kept_copy(1).png")

    result = run_script("organize_media.py", tmp_path, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (pics / "kept.png").exists()
    assert (duplicate_pics / "kept_copy(1).png").exists()
    assert duplicate_vids.is_dir()
    assert not action_log_path(tmp_path).exists()
