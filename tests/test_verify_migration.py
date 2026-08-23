from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

from pymo.collection import CollectionLayout
from pymo.config import load_config
from pymo.migration import images as migration_images
from pymo.migration import inventory
from pymo.migration.coverage import compare_byte_inventories

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"


def write_image(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (4, 3), color).save(path)


def run_verify(*arguments: object) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(SOURCE_ROOT)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pymo",
            "--no-timestamps",
            "verify-migration",
            *(str(item) for item in arguments),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def files_under(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def test_verify_migration_is_path_independent_private_and_zero_write(
    tmp_path: Path,
) -> None:
    source = tmp_path / "baseline"
    destination = tmp_path / "working"
    (source / "incoming").mkdir(parents=True)
    (destination / "pics").mkdir(parents=True)
    (source / "incoming" / "original-a.bin").write_bytes(b"alpha")
    (source / "original-b.bin").write_bytes(b"beta")
    (destination / "pics" / "renamed-001.bin").write_bytes(b"beta")
    (destination / "renamed-002.bin").write_bytes(b"alpha")
    before_source = files_under(source)
    before_destination = files_under(destination)

    result = run_verify(source, destination, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == 2
    assert report["direction"] == "source-to-destination"
    assert report["contract"] == "unique-byte-stream"
    assert report["coverage"]["verdict"] == "complete"
    assert report["coverage"]["represented_unique_streams"] == 2
    assert report["coverage"]["missing_unique_streams"] == 0
    assert report["writes_performed"] is False
    assert "baseline" not in result.stdout
    assert "working" not in result.stdout
    assert "original-a.bin" not in result.stdout
    assert "renamed-001.bin" not in result.stdout
    assert files_under(source) == before_source
    assert files_under(destination) == before_destination
    for root in (source, destination):
        layout = CollectionLayout(root)
        assert not layout.derived_cache.exists()
        assert not layout.derived_cache_lock.exists()
        assert not layout.action_log.exists()


def test_verify_migration_separates_unique_coverage_from_multiplicity_and_extras(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "copy-one.bin").write_bytes(b"same")
    (source / "copy-two.bin").write_bytes(b"same")
    (source / "unique.bin").write_bytes(b"unique")
    (destination / "retained.bin").write_bytes(b"same")
    (destination / "moved.bin").write_bytes(b"unique")
    (destination / "additional.bin").write_bytes(b"destination only")

    result = run_verify(source, destination, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["coverage"]["verdict"] == "complete"
    assert report["coverage"]["source_files"] == 3
    assert report["coverage"]["represented_source_files"] == 3
    assert report["multiplicity"]["source_duplicate_copies"] == 1
    assert report["multiplicity"]["reduced_copies"] == 1
    assert report["multiplicity"]["reduced_copy_bytes"] == 4
    assert report["destination_only"]["unique_streams"] == 1
    assert report["destination_only"]["files"] == 1


def test_missing_and_destination_only_paths_require_explicit_disclosure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "missing-private-name.bin").write_bytes(b"not copied")
    (destination / "extra-private-name.bin").write_bytes(b"extra")

    private = run_verify(source, destination)
    disclosed = run_verify(source, destination, "--show-files", "--json")

    assert private.returncode == disclosed.returncode == 1
    assert "INCOMPLETE" in private.stdout
    assert "missing-private-name.bin" not in private.stdout + private.stderr
    assert "extra-private-name.bin" not in private.stdout + private.stderr
    report = json.loads(disclosed.stdout)
    assert report["coverage"]["verdict"] == "incomplete"
    assert report["coverage"]["missing_source_paths"] == ["missing-private-name.bin"]
    assert report["destination_only"]["paths"] == ["extra-private-name.bin"]


def test_source_policy_exclusion_is_explicit_but_v050_verdict_is_scope_relative(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "media.bin").write_bytes(b"media")
    (destination / "media.bin").write_bytes(b"media")
    (source / ".DS_Store").write_bytes(b"excluded state")

    private = run_verify(source, destination, "--json")
    disclosed = run_verify(source, destination, "--show-ignored", "--json")

    assert private.returncode == disclosed.returncode == 0
    private_report = json.loads(private.stdout)
    assert private_report["coverage"]["verdict"] == "complete"
    assert private_report["scope"]["policy_ignored_content_proven"] is False
    assert private_report["source"]["ignored_entry_points"] == 1
    assert private_report["source"]["ignored_paths"] == []
    assert json.loads(disclosed.stdout)["source"]["ignored_paths"] == [".DS_Store"]


def test_pymo_state_is_outside_the_byte_contract_and_does_not_block_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "media.bin").write_bytes(b"media")
    (destination / "media.bin").write_bytes(b"media")
    layout = CollectionLayout(source)
    layout.config.write_text("version = 1\n", encoding="utf-8")
    layout.derived_cache.write_bytes(b"disposable")
    layout.action_log.write_text("authoritative but out of scope\n", encoding="utf-8")

    result = run_verify(source, destination, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["coverage"]["verdict"] == "complete"
    assert report["source"]["tool_state_entries"] == 3
    assert layout.derived_cache.read_bytes() == b"disposable"
    assert layout.action_log.read_text(encoding="utf-8") == (
        "authoritative but out of scope\n"
    )


def test_symbolic_links_are_not_followed_and_make_source_evidence_unproven(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    outside = tmp_path / "outside.bin"
    source.mkdir()
    destination.mkdir()
    outside.write_bytes(b"outside")
    (source / "media.bin").write_bytes(b"media")
    (destination / "media.bin").write_bytes(b"media")
    (source / "linked.bin").symlink_to(outside)

    result = run_verify(source, destination, "--show-files", "--json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["coverage"]["verdict"] == "unproven"
    assert report["source"]["symbolic_links"] == 1
    assert report["source"]["problem_paths"] == [
        {"category": "symbolic-link", "path": "linked.bin"}
    ]


def test_verify_migration_rejects_same_or_nested_roots_without_state(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    nested = source / "nested"
    nested.mkdir(parents=True)

    same = run_verify(source, source)
    overlapping = run_verify(source, nested)

    assert same.returncode == overlapping.returncode == 2
    assert "distinct, non-nested" in same.stderr
    assert "distinct, non-nested" in overlapping.stderr
    assert files_under(source) == {}


def test_changed_hash_input_is_omitted_and_reported(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    media = root / "changing.bin"
    media.write_bytes(b"before")
    discovery = inventory.discover_tree(root, load_config(root))

    def change_during_hash(descriptor: int) -> str:
        digest = hashlib.sha256(os.read(descriptor, 1024)).hexdigest()
        media.write_bytes(b"after")
        return digest

    monkeypatch.setattr(inventory, "sha256_descriptor", change_during_hash)

    result = inventory.hash_tree(discovery, 15, show_progress=False)

    assert result.files == ()
    assert [issue.category for issue in result.changed] == ["changed-during-hash"]
    assert result.evidence_complete is False


def test_traversal_failure_is_counted_and_makes_coverage_unproven(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "media.bin").write_bytes(b"media")
    (destination / "media.bin").write_bytes(b"media")
    real_walk = inventory.os.walk

    def incomplete_walk(root, *, topdown, onerror):
        onerror(OSError("synthetic traversal failure"))
        yield from real_walk(root, topdown=topdown, onerror=onerror)

    monkeypatch.setattr(inventory.os, "walk", incomplete_walk)
    source_discovery = inventory.discover_tree(source, load_config(source))
    monkeypatch.setattr(inventory.os, "walk", real_walk)
    destination_discovery = inventory.discover_tree(
        destination, load_config(destination)
    )
    source_inventory = inventory.hash_tree(source_discovery, 15, show_progress=False)
    destination_inventory = inventory.hash_tree(
        destination_discovery, 15, show_progress=False
    )

    coverage = compare_byte_inventories(source_inventory, destination_inventory)

    assert source_inventory.traversal_errors == 1
    assert coverage.represented_unique_streams == 1
    assert coverage.verdict == "unproven"
    assert coverage.reasons == ("source-inventory-incomplete",)


def test_unreadable_hash_does_not_abort_healthy_neighbors(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    healthy = root / "healthy.bin"
    unreadable = root / "unreadable.bin"
    healthy.write_bytes(b"healthy")
    unreadable.write_bytes(b"unreadable")
    failed_inode = unreadable.stat().st_ino
    real_hash = inventory.sha256_descriptor

    def selectively_fail(descriptor: int) -> str:
        if os.fstat(descriptor).st_ino == failed_inode:
            raise OSError("synthetic read failure")
        return real_hash(descriptor)

    monkeypatch.setattr(inventory, "sha256_descriptor", selectively_fail)
    discovery = inventory.discover_tree(root, load_config(root))

    result = inventory.hash_tree(discovery, 15, show_progress=False)

    assert [entry.path for entry in result.files] == [healthy]
    assert [issue.path for issue in result.unreadable] == [unreadable]
    assert result.evidence_complete is False


def test_missing_content_with_incomplete_destination_is_unproven(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    outside = tmp_path / "outside.bin"
    source.mkdir()
    destination.mkdir()
    outside.write_bytes(b"outside")
    (source / "missing.bin").write_bytes(b"missing")
    (destination / "uninspected.bin").symlink_to(outside)

    result = run_verify(source, destination, "--json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["coverage"]["verdict"] == "unproven"
    assert report["coverage"]["reasons"] == ["destination-inventory-incomplete"]
    assert report["coverage"]["missing_unique_streams"] == 1


def test_metadata_or_format_varied_image_is_reported_as_exact_pixel_coverage(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    write_image(source / "garden.png", (12, 34, 56))
    write_image(destination / "renamed-garden.bmp", (12, 34, 56))
    before_source = files_under(source)
    before_destination = files_under(destination)

    result = run_verify(source, destination, "--json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["coverage"]["verdict"] == "incomplete"
    assert report["coverage"]["missing_unique_streams"] == 1
    assert report["image_content"]["verdict"] == "complete"
    assert report["image_content"]["eligible_source_unique_streams"] == 1
    assert report["image_content"]["represented_unique_streams"] == 1
    assert report["image_content"]["missing_unique_streams"] == 0
    assert "garden.png" not in result.stdout
    assert "renamed-garden.bmp" not in result.stdout
    assert files_under(source) == before_source
    assert files_under(destination) == before_destination


def test_different_displayed_pixels_are_reported_separately_from_missing_bytes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    write_image(source / "source.png", (1, 2, 3))
    write_image(destination / "destination.bmp", (3, 2, 1))

    result = run_verify(source, destination, "--show-files", "--json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    images = report["image_content"]
    assert images["verdict"] == "incomplete"
    assert images["reasons"] == ["image-content-missing"]
    assert images["missing_source_paths"] == ["source.png"]


def test_unreadable_source_image_makes_image_layer_unproven(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "damaged.png").write_bytes(b"not an image")
    write_image(destination / "candidate.png", (1, 2, 3))

    result = run_verify(source, destination, "--show-files", "--json")

    assert result.returncode == 1
    images = json.loads(result.stdout)["image_content"]
    assert images["verdict"] == "unproven"
    assert images["reasons"] == ["source-image-evidence-incomplete"]
    assert images["uninspectable_source_unique_streams"] == 1
    assert images["source_problem_paths"] == [
        {"category": "unreadable-image-content", "path": "damaged.png"}
    ]


def test_unreadable_destination_image_can_hide_a_pixel_representative(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    write_image(source / "source.png", (1, 2, 3))
    (destination / "unknown.png").write_bytes(b"not an image")

    result = run_verify(source, destination, "--show-files", "--json")

    assert result.returncode == 1
    images = json.loads(result.stdout)["image_content"]
    assert images["verdict"] == "unproven"
    assert images["reasons"] == ["destination-image-evidence-incomplete"]
    assert images["destination_uninspectable_unique_streams"] == 1
    assert images["destination_problem_paths"] == [
        {"category": "unreadable-image-content", "path": "unknown.png"}
    ]


def test_byte_represented_images_do_not_require_pixel_inspection(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    write_image(source / "source.png", (1, 2, 3))
    (destination / "renamed.png").write_bytes((source / "source.png").read_bytes())
    source_inventory = inventory.hash_tree(
        inventory.discover_tree(source, load_config(source)), 15, show_progress=False
    )
    destination_inventory = inventory.hash_tree(
        inventory.discover_tree(destination, load_config(destination)),
        15,
        show_progress=False,
    )

    def reject_decode(_descriptor: int) -> str:
        raise AssertionError("byte-represented content should not be decoded")

    monkeypatch.setattr(migration_images, "displayed_pixel_hash", reject_decode)
    result = migration_images.compare_image_content(
        source_inventory,
        destination_inventory,
        load_config(source).image_duplicates.extensions,
        15,
        show_progress=False,
    )

    assert result.verdict == "not-needed"
    assert result.eligible_source_unique_streams == 0


def test_image_changed_after_byte_inventory_is_unproven(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    source_image = source / "source.png"
    write_image(source_image, (1, 2, 3))
    write_image(destination / "destination.bmp", (1, 2, 3))
    source_inventory = inventory.hash_tree(
        inventory.discover_tree(source, load_config(source)), 15, show_progress=False
    )
    destination_inventory = inventory.hash_tree(
        inventory.discover_tree(destination, load_config(destination)),
        15,
        show_progress=False,
    )
    write_image(source_image, (9, 8, 7))

    result = migration_images.compare_image_content(
        source_inventory,
        destination_inventory,
        load_config(source).image_duplicates.extensions,
        15,
        show_progress=False,
    )

    assert result.verdict == "unproven"
    assert result.uninspectable_source_unique_streams == 1
    assert [issue.category for issue in result.source_issues] == [
        "changed-during-image-inspection"
    ]
