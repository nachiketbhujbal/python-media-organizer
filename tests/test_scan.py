from __future__ import annotations

import errno
import json
import os
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
    assert "Run pymo validate" in result.stdout
    assert "Run pymo correct-extensions" in result.stdout
    assert "Run pymo organize" in result.stdout
    assert "Run pymo rename" in result.stdout
    assert (
        result.stdout.index("Run pymo validate")
        < result.stdout.index("Run pymo correct-extensions")
        < result.stdout.index("Run pymo organize")
        < result.stdout.index("Run pymo rename")
    )
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
    assert exact["cache_hits"] == 0
    assert exact["computed_hashes"] == exact["hashed_files"]
    assert report["derived_state"]["action_log_present"] is False
    assert report["derived_state"]["video_cache_present"] is False
    assert report["recommendations"][:4] == [
        "Run pymo validate before applying changes.",
        "Run pymo correct-extensions after reviewing its dry run.",
        "Run pymo organize after reviewing its dry run.",
        "Run pymo rename after reviewing its dry run.",
    ]
    assert not CollectionLayout(root).derived_cache.exists()
    assert not CollectionLayout(root).derived_cache_lock.exists()


def test_scan_cache_selector_requires_checksum_profile(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()

    result = run_script("scan.py", root, "--cache", tmp_path / "cache.sqlite3")

    assert result.returncode == 2
    assert "--cache requires --checksums" in result.stderr
    assert list(root.iterdir()) == []


def test_scan_records_directory_walk_errors_without_writing_state(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    blocked = root / "closed"

    def inaccessible_walk(
        _root: Path, *, topdown: bool, onerror
    ) -> list[tuple[str, list[str], list[str]]]:
        assert topdown
        onerror(OSError(errno.EACCES, "permission denied", str(blocked)))
        return []

    monkeypatch.setattr(scan.os, "walk", inaccessible_walk)

    report = scan.build_report(root, load_config(root), 1, False, False, False)

    assert report["inventory"]["files"] == 0
    assert report["inventory"]["unreadable_entries"] == 1
    assert report["warnings"] == ["1 entry or entries could not be read safely."]
    assert report["recommendations"][:2] == [
        "Run pymo validate before applying changes.",
        "Review symbolic links and unreadable entries first.",
    ]
    assert not action_log_path(root).exists()
    assert not CollectionLayout(root).video_cache.exists()


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
    original_sha256 = scan._sha256_descriptor

    def hash_then_change(descriptor: int) -> str:
        digest = original_sha256(descriptor)
        first.write_bytes(first.read_bytes() + b"changed")
        return digest

    monkeypatch.setattr(scan, "_sha256_descriptor", hash_then_change)

    report = scan.build_report(root, load_config(root), 1, True, False, False)
    exact = report["duplicate_potential"]["exact_bytes"]

    assert report["inventory"]["files"] == 1
    assert report["inventory"]["changed_entries"] == 1
    assert exact["groups"] == 0
    assert exact["hashed_files"] == 1
    assert exact["changed_files"] == 1
    assert report["duplicate_potential"]["pictures"]["candidate_files"] == 0


def test_checksum_scan_pins_the_original_file_during_a_path_swap(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    first = root / "first.png"
    second = root / "second.png"
    Image.new("RGB", (2, 2), "blue").save(first)
    shutil.copyfile(first, second)
    original_bytes = first.read_bytes()
    replacement = tmp_path / "replacement.png"
    Image.new("RGB", (2, 2), "orange").save(replacement)
    displaced = root / "displaced.png"
    real_sha256 = scan._sha256_descriptor
    calls = 0
    observed = b""

    def swap_first_path(descriptor: int) -> str:
        nonlocal calls, observed
        calls += 1
        if calls == 1:
            first.rename(displaced)
            first.symlink_to(replacement)
            observed = os.pread(descriptor, len(original_bytes), 0)
        return real_sha256(descriptor)

    monkeypatch.setattr(scan, "_sha256_descriptor", swap_first_path)

    report = scan.build_report(root, load_config(root), 1, True, False, False)

    assert observed == original_bytes
    assert observed != replacement.read_bytes()
    assert report["inventory"]["changed_entries"] == 1
    assert report["duplicate_potential"]["exact_bytes"]["groups"] == 0
