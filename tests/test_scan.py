from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from pymo import scan
from pymo.action_log import action_log_path
from pymo.collection import CollectionLayout
from pymo.config import load_config


def make_collection(root: Path) -> None:
    pics = root / "pics"
    vids = root / "vids"
    incoming = root / "incoming"
    review = root / "dups" / "pics"
    pics.mkdir(parents=True)
    vids.mkdir()
    incoming.mkdir()
    review.mkdir(parents=True)

    Image.new("RGB", (3, 2), "green").save(pics / "ready.png")
    duplicate = incoming / "first.png"
    Image.new("RGB", (2, 2), "blue").save(duplicate)
    shutil.copyfile(duplicate, incoming / "second.png")
    Image.new("RGB", (4, 2), "orange").save(review / "review.png")
    (vids / "ready.mp4").write_bytes(b"")
    (incoming / "notes.txt").write_text("garden notes", encoding="utf-8")
    (pics / ".DS_Store").write_bytes(b"view state")


def test_fast_scan_reports_inventory_without_revealing_paths_or_writing_state(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    make_collection(root)
    before = sorted(path.relative_to(root) for path in root.rglob("*"))

    result = run_script("scan.py", root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Collection scan" in result.stdout
    assert "Files: 6" in result.stdout
    assert "Pictures: 4 file(s)" in result.stdout
    assert "Videos: 1 file(s)" in result.stdout
    assert "Proposed organizer moves: 3 file(s)" in result.stdout
    assert "Pictures: 1 same-size group(s)" in result.stdout
    assert "Exact-byte checks: not requested" in result.stdout
    assert "Run pymo organize" in result.stdout
    assert "first.png" not in result.stdout
    assert ".DS_Store" not in result.stdout
    assert sorted(path.relative_to(root) for path in root.rglob("*")) == before
    assert not action_log_path(root).exists()
    assert not CollectionLayout(root).video_cache.exists()


def test_checksum_scan_emits_stable_json_and_opt_in_ignored_paths(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    make_collection(root)

    result = run_script(
        "scan.py", root, "--checksums", "--show-ignored", "--json", "--workers", "2"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == 1
    assert report["profile"] == "checksums"
    assert report["workers"] == 2
    assert report["inventory"]["files"] == 6
    assert report["inventory"]["ignored_entry_points"] == 1
    assert report["ignored_paths"] == ["pics/.DS_Store"]
    exact = report["duplicate_potential"]["exact_bytes"]
    assert exact["groups"] == 1
    assert exact["extra_copies"] == 1
    assert exact["reclaimable_bytes"] > 0
    assert report["derived_state"]["action_log_present"] is False
    assert report["derived_state"]["video_cache_present"] is False


def test_scan_rejects_unsafe_worker_counts(tmp_path: Path, run_script) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()

    for workers in ("0", "33"):
        result = run_script("scan.py", root, "--workers", workers)

        assert result.returncode == 2
        assert "--workers must be between 1 and 32" in result.stderr


def test_scan_omits_a_file_changed_during_classification(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    path = root / "changing.png"
    Image.new("RGB", (2, 2), "green").save(path)
    original_classify = scan.Classifier.classify

    def classify_then_change(classifier, target: Path) -> tuple[str, str]:
        result = original_classify(classifier, target)
        target.write_bytes(target.read_bytes() + b"changed")
        return result

    monkeypatch.setattr(scan.Classifier, "classify", classify_then_change)

    report = scan.build_report(root, load_config(root), 1, False, False, False)

    assert report["inventory"]["files"] == 0
    assert report["inventory"]["changed_entries"] == 1
    assert "changed during the scan and were omitted" in report["warnings"][0]


def test_checksum_scan_excludes_a_file_changed_while_hashing(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    first = root / "first.png"
    second = root / "second.png"
    Image.new("RGB", (2, 2), "blue").save(first)
    shutil.copyfile(first, second)
    original_sha256 = scan._sha256

    def hash_then_change(path: Path) -> str:
        digest = original_sha256(path)
        if path == first:
            path.write_bytes(path.read_bytes() + b"changed")
        return digest

    monkeypatch.setattr(scan, "_sha256", hash_then_change)

    report = scan.build_report(root, load_config(root), 1, True, False, False)
    exact = report["duplicate_potential"]["exact_bytes"]

    assert report["inventory"]["files"] == 1
    assert report["inventory"]["changed_entries"] == 1
    assert exact["groups"] == 0
    assert exact["hashed_files"] == 1
    assert exact["changed_files"] == 1
    assert report["duplicate_potential"]["pictures"]["candidate_files"] == 0
