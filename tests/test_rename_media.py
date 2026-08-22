from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from pymo.action_log import action_log_path
from pymo.config import load_config
from pymo.rename import clean_descriptor, timestamp_from_name


def write_video(path: Path) -> None:
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("IMG_20201027_012834_225.jpg", "2020-10-27_01-28-34-225"),
        ("VID_20210419_025751_350_1814186.mp4", "2021-04-19_02-57-51-350"),
        ("photo_2020-10-01_16-06-35 (2).jpg", "2020-10-01_16-06-35"),
        ("2020-10-18 07.22.04.mov", "2020-10-18_07-22-04"),
        ("2020_08_11_22_09_35.mp4", "2020-08-11_22-09-35"),
        (
            "2020-09-09_1242x2688_c8c3ed12887dd5768610e078c4af88c4-SOURCE-SITE.COM.jpg",
            "2020-09-09",
        ),
        ("5f4bdaaf27f8c5bc73a5a_source.mp4", None),
    ],
)
def test_timestamp_patterns(name: str, expected: str | None) -> None:
    assert timestamp_from_name(name) == expected


@pytest.mark.parametrize(
    ("stem", "collection", "expected"),
    [
        ("Media Collection Garden Fern", "media_collection", "garden_fern"),
        ("Lisbon Ceramic Planter", "media_collection", "lisbon_ceramic_planter"),
        ("media_collection-Kyoto-4-thumb-1024x578", "media_collection", "kyoto"),
        ("media_collectionsunflowers-pic-100", "media_collection", "sunflowers"),
        ("5f4bdaaf27f8c5bc73a5a_source", "media_collection", None),
        ("@site001 join us TG 2020-11-03 08.33.55", "media_collection", None),
        (
            "2020-09-09_1242x2688_c8c3ed12887dd5768610e078c4af88c4-SOURCE-SITE.COM",
            "media_collection",
            None,
        ),
        ("TG-PromoChannel103", "media_collection", None),
        ("TP (15)", "media_collection", None),
    ],
)
def test_descriptor_cleanup(
    tmp_path: Path, stem: str, collection: str, expected: str | None
) -> None:
    noise_tokens = load_config(tmp_path).rename.noise_tokens
    assert clean_descriptor(stem, collection, noise_tokens) == expected


def make_rename_fixture(root: Path) -> None:
    pics = root / "pics"
    vids = root / "vids"
    pics.mkdir(parents=True)
    vids.mkdir()
    Image.new("RGB", (2, 2), "red").save(pics / "IMG_20201027_012834_225.jpg")
    Image.new("RGB", (2, 2), "green").save(
        pics / "1114x1630_8da314be4838b75b28d2b5cd9d78364b.jpg"
    )
    write_video(vids / "5f4bdaaf27f8c5bc73a5a_source.mp4")
    write_video(vids / "Media Collection Garden Fern.mp4")
    (root / "notes.txt").write_text("leave me", encoding="utf-8")


def test_renamer_dry_run_uses_universal_schema(tmp_path: Path, run_script) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    make_rename_fixture(root)

    result = run_script("rename_media.py", root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Would rename 4 media file(s)" in result.stdout
    assert "media_collection__image_0001__2020-10-27_01-28-34-225.jpg" in result.stdout
    assert "media_collection__image_0002__undated.jpg" in result.stdout
    assert "media_collection__video_0001__undated.mp4" in result.stdout
    assert "media_collection__video_0002__undated__garden_fern.mp4" in result.stdout
    assert (root / "notes.txt").read_text(encoding="utf-8") == "leave me"
    assert not action_log_path(root).exists()


def test_renamer_apply_and_undo_are_logged_and_reversible(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    make_rename_fixture(root)
    originals = sorted(
        str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()
    )

    applied = run_script("rename_media.py", root, "--apply")

    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert (
        root / "pics" / "media_collection__image_0001__2020-10-27_01-28-34-225.jpg"
    ).exists()
    assert action_log_path(root).exists()

    undone = run_script("rename_media.py", root, "--undo", "--apply")

    assert undone.returncode == 0, undone.stdout + undone.stderr
    restored = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and path != action_log_path(root)
    )
    assert restored == originals
    assert action_log_path(root).exists()


def test_organize_undo_is_blocked_until_rename_is_undone(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "collection"
    nested = root / "nested"
    nested.mkdir(parents=True)
    Image.new("RGB", (2, 2), "blue").save(nested / "IMG_20200102_030405_006.jpg")

    assert run_script("organize_media.py", root, "--apply").returncode == 0
    assert run_script("rename_media.py", root, "--apply").returncode == 0

    blocked = run_script("organize_media.py", root, "--undo", "--apply")

    assert blocked.returncode == 1
    assert "rename_media" in blocked.stderr
    assert run_script("rename_media.py", root, "--undo", "--apply").returncode == 0
    final_undo = run_script("organize_media.py", root, "--undo", "--apply")
    assert final_undo.returncode == 0, final_undo.stdout + final_undo.stderr
    assert (nested / "IMG_20200102_030405_006.jpg").exists()


def test_renamer_preserves_reserved_dups_tree(tmp_path: Path, run_script) -> None:
    root = tmp_path / "collection"
    pics = root / "pics"
    vids = root / "vids"
    duplicate_pics = root / "dups" / "pics"
    duplicate_vids = root / "dups" / "vids"
    pics.mkdir(parents=True)
    vids.mkdir()
    duplicate_pics.mkdir(parents=True)
    duplicate_vids.mkdir()
    Image.new("RGB", (2, 2), "blue").save(pics / "IMG_20200102_030405.jpg")
    quarantined = duplicate_pics / "old_duplicate_name.jpg"
    Image.new("RGB", (2, 2), "blue").save(quarantined)

    result = run_script("rename_media.py", root, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert quarantined.exists()
    assert len(list(pics.glob("collection__image_*.jpg"))) == 1


def test_renamer_honors_custom_file_rules(tmp_path: Path, run_script) -> None:
    root = tmp_path / "collection"
    pics = root / "pics"
    vids = root / "vids"
    pics.mkdir(parents=True)
    vids.mkdir()
    protected = pics / "keep-original.png"
    candidate = pics / "rename-this.png"
    Image.new("RGB", (2, 2), "blue").save(protected)
    Image.new("RGB", (2, 2), "green").save(candidate)
    (root / ".pymo.toml").write_text(
        'version = 1\n\n[ignore]\nfiles = ["keep-original.png"]\n',
        encoding="utf-8",
    )

    result = run_script("rename_media.py", root, "--show-ignored", "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ignored by configuration: 2 path(s)." in result.stdout
    assert "  .pymo.toml" in result.stdout
    assert "  pics/keep-original.png" in result.stdout
    assert protected.exists()
    assert not candidate.exists()
    assert len(list(pics.glob("collection__image_0001__*.png"))) == 1
    assert "keep-original.png" not in action_log_path(root).read_text(encoding="utf-8")


def test_renamer_uses_custom_noise_tokens(tmp_path: Path, run_script) -> None:
    root = tmp_path / "collection"
    pics = root / "pics"
    (root / "vids").mkdir(parents=True)
    pics.mkdir()
    source = pics / "Garden Fern.png"
    Image.new("RGB", (2, 2), "green").save(source)
    (root / ".pymo.toml").write_text(
        "version = 1\n" "[rename]\n" 'noise_tokens = ["garden"]\n',
        encoding="utf-8",
    )

    result = run_script("rename_media.py", root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "__undated__fern.png" in result.stdout
    assert "__undated__garden_fern.png" not in result.stdout
