from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from pymo import __version__, migrate, policy
from pymo.migration.policy_plan import build_candidate
from pymo.migration.preauthorization import load_preauthorization
from pymo.migration.virtual import PolicyPlanningError, canonical_bytes


def run(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pymo", *(str(a) for a in arguments)],
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )


def collection_pair(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.chmod(0o700)
    baseline = tmp_path / "baseline"
    working = tmp_path / "collection"
    (tmp_path / "private").mkdir(mode=0o700)
    baseline.mkdir()
    working.mkdir()
    return baseline, working


def snapshot(root: Path) -> dict[str, tuple[int, int, bytes | None]]:
    return {
        str(p.relative_to(root)): (
            p.lstat().st_ino,
            p.lstat().st_mtime_ns,
            p.read_bytes() if p.is_file() else None,
        )
        for p in root.rglob("*")
    }


def media(baseline: Path, working: Path) -> None:
    nested = baseline / "nested"
    nested.mkdir()
    Image.new("RGB", (8, 8), "red").save(nested / "wrong.jpg", format="PNG")
    meta = PngInfo()
    meta.add_text("comment", "synthetic variation")
    Image.new("RGB", (8, 8), "red").save(nested / "copy.png", pnginfo=meta)
    Image.new("RGB", (8, 8), "blue").save(nested / "distinct.png")
    (nested / "note.txt").write_text("synthetic non-media")
    shutil.copytree(baseline, working, dirs_exist_ok=True)


def save_candidate(tmp_path: Path, baseline: Path, working: Path) -> tuple[Path, dict]:
    value = build_candidate(
        baseline, working, migrate._initial_options({"no_cache": True})
    )
    path = tmp_path / "private" / "candidate.json"
    path.write_bytes(canonical_bytes(value))
    path.chmod(0o600)
    return path, value


def accept_candidate(candidate: Path, accepted: Path) -> None:
    assert (
        policy.main(
            [
                "accept",
                str(candidate),
                "--sha256",
                hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "--output",
                str(accepted),
                "--apply",
            ]
        )
        == 0
    )


@pytest.mark.parametrize("with_media", [False, True])
def test_plan_accept_and_actual_workflow_agree(
    tmp_path: Path, with_media: bool
) -> None:
    baseline, working = collection_pair(tmp_path)
    if with_media:
        media(baseline, working)
    before = (snapshot(baseline), snapshot(working))
    candidate, value = save_candidate(tmp_path, baseline, working)
    assert (snapshot(baseline), snapshot(working)) == before
    assert value["kind"] == "unaccepted-migration-plan"
    assert len(value["policy"]["authorizations"]) == 10
    accepted = tmp_path / "private" / "accepted.json"
    sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    assert (
        policy.main(
            ["accept", str(candidate), "--sha256", sha, "--output", str(accepted)]
        )
        == 0
    )
    assert not accepted.exists()
    assert (
        policy.main(
            [
                "accept",
                str(candidate),
                "--sha256",
                sha,
                "--output",
                str(accepted),
                "--apply",
            ]
        )
        == 0
    )
    assert accepted.stat().st_mode & 0o777 == 0o600
    assert (
        load_preauthorization(accepted, roots=(baseline, working)).tool_version
        == __version__
    )
    assert (snapshot(baseline), snapshot(working)) == before
    logs = tmp_path / "logs"
    result = run(
        "migrate",
        baseline,
        working,
        "--no-cache",
        "--log-dir",
        logs,
        "--unattended",
        accepted,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Pre-authorized final sign-off recorded" in result.stdout
    assert snapshot(baseline) == before[0]
    if with_media:
        assert len(list((working / "dups" / "pics").iterdir())) == 1
        assert sorted(
            p.read_bytes()
            for p in working.rglob("*")
            if p.is_file() and not p.name.endswith("actions-log.jsonl")
        ) == sorted(p.read_bytes() for p in baseline.rglob("*") if p.is_file())


@pytest.mark.parametrize(
    "change", ["bytes", "name", "replacement", "root", "added", "config"]
)
def test_accept_refuses_changed_target(tmp_path: Path, change: str) -> None:
    baseline, working = collection_pair(tmp_path)
    media(baseline, working)
    candidate, _ = save_candidate(tmp_path, baseline, working)
    source = working / "nested" / "note.txt"
    if change == "bytes":
        source.write_text("different non-media")
    elif change == "name":
        source.rename(source.with_name("different.txt"))
    elif change == "replacement":
        replacement = working / "replacement"
        replacement.write_bytes(source.read_bytes())
        os.replace(replacement, source)
    elif change == "root":
        working.rename(working.with_name("old"))
        shutil.copytree(working.with_name("old"), working)
    elif change == "added":
        (working / "extra.txt").write_text("added")
    else:
        (working / ".pymo.toml").write_text("[ignore]\npatterns = ['extra.txt']\n")
    accepted = tmp_path / "private" / "accepted.json"
    assert (
        policy.main(
            [
                "accept",
                str(candidate),
                "--sha256",
                hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "--output",
                str(accepted),
                "--apply",
            ]
        )
        == 2
    )
    assert not accepted.exists()


def test_draft_is_not_authority_and_wrong_digest_never_writes(tmp_path: Path) -> None:
    baseline, working = collection_pair(tmp_path)
    candidate, _ = save_candidate(tmp_path, baseline, working)
    result = run(
        "migrate",
        baseline,
        working,
        "--no-cache",
        "--log-dir",
        tmp_path / "logs",
        "--unattended",
        candidate,
    )
    assert result.returncode == 2
    assert not (tmp_path / "logs").exists()
    accepted = tmp_path / "private" / "accepted.json"
    assert (
        policy.main(
            [
                "accept",
                str(candidate),
                "--sha256",
                "0" * 64,
                "--output",
                str(accepted),
                "--apply",
            ]
        )
        == 2
    )
    assert not accepted.exists()


def test_planning_refuses_underivable_quarantine(tmp_path: Path) -> None:
    baseline, working = collection_pair(tmp_path)
    with pytest.raises(PolicyPlanningError, match="quarantine"):
        build_candidate(
            baseline,
            working,
            migrate._initial_options(
                {"no_cache": True, "quarantine_destination": str(tmp_path / "retained")}
            ),
        )


def test_cli_preview_private_review_and_no_replace(tmp_path: Path) -> None:
    baseline, working = collection_pair(tmp_path)
    media(baseline, working)
    candidate = tmp_path / "private" / "candidate.json"
    before = snapshot(working)
    preview = run("policy", "plan", baseline, working, "--output", candidate)
    assert preview.returncode == 0, preview.stderr
    assert not candidate.exists()
    assert str(working) not in preview.stdout + preview.stderr
    assert "wrong.jpg" not in preview.stdout + preview.stderr
    saved = run("policy", "plan", baseline, working, "--output", candidate, "--apply")
    assert saved.returncode == 0, saved.stderr
    payload = candidate.read_bytes()
    assert run("policy", "review", candidate).returncode == 0
    assert (
        run(
            "policy", "plan", baseline, working, "--output", candidate, "--apply"
        ).returncode
        == 2
    )
    assert candidate.read_bytes() == payload
    assert snapshot(working) == before


@pytest.mark.parametrize("attack", ["bytes", "added", "identity"])
def test_accepted_policy_refuses_changed_execution_target(
    tmp_path: Path, attack: str
) -> None:
    baseline, working = collection_pair(tmp_path)
    media(baseline, working)
    _candidate, _ = save_candidate(tmp_path, baseline, working)
    accepted = tmp_path / "private" / "accepted.json"
    accept_candidate(_candidate, accepted)
    source = working / "nested" / "note.txt"
    if attack == "bytes":
        source.write_text("different media-independent evidence")
    elif attack == "added":
        (working / "extra.txt").write_text("extra")
    else:
        source.rename(source.with_suffix(".saved"))
        source.write_text("synthetic non-media")
    before = snapshot(working)
    result = run(
        "migrate",
        baseline,
        working,
        "--no-cache",
        "--log-dir",
        tmp_path / "logs",
        "--unattended",
        accepted,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert snapshot(working) == before
    assert not list((tmp_path / "logs").glob("*outcome*"))


def test_virtual_collisions_and_ignored_directories_match_real_execution(
    tmp_path: Path,
) -> None:
    baseline, working = collection_pair(tmp_path)
    for folder in ("a", "b", "pics", "empty", "protected"):
        (baseline / folder).mkdir()
    Image.new("RGB", (5, 5), "red").save(baseline / "a" / "same.png")
    Image.new("RGB", (5, 5), "blue").save(baseline / "b" / "same.png")
    Image.new("RGB", (5, 5), "green").save(baseline / "pics" / "same.png")
    (baseline / "protected" / ".DS_Store").write_bytes(b"synthetic ignored")
    shutil.copytree(baseline, working, dirs_exist_ok=True)
    _candidate, _ = save_candidate(tmp_path, baseline, working)
    accepted = tmp_path / "private" / "accepted.json"
    accept_candidate(_candidate, accepted)
    result = run(
        "migrate",
        baseline,
        working,
        "--no-cache",
        "--log-dir",
        tmp_path / "logs",
        "--unattended",
        accepted,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Pre-authorized final sign-off recorded" in result.stdout
    assert (working / "protected" / ".DS_Store").read_bytes() == b"synthetic ignored"


@pytest.mark.parametrize(
    "unsafe", ["symlink", "corrupt", "animated", "occupied", "case-alias", "journal"]
)
def test_incomplete_plan_never_publishes(tmp_path: Path, unsafe: str) -> None:
    baseline, working = collection_pair(tmp_path)
    media(baseline, working)
    if unsafe == "symlink":
        (working / "unsafe").symlink_to(baseline)
    elif unsafe == "corrupt":
        (working / "bad.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    elif unsafe == "animated":
        Image.new("RGB", (2, 2), "red").save(
            working / "animated.gif",
            save_all=True,
            append_images=[Image.new("RGB", (2, 2), "blue")],
        )
    elif unsafe == "occupied":
        (working / "pics").write_text("occupied")
    elif unsafe == "case-alias":
        (working / "PICS").mkdir()
    else:
        (working / f"{working.name}-actions-log.jsonl").write_text("{}\n")
    output = tmp_path / "private" / "candidate.json"
    result = run("policy", "plan", baseline, working, "--output", output, "--apply")
    assert result.returncode == 2, result.stdout + result.stderr
    assert not output.exists()
    assert "Traceback" not in result.stderr
    assert str(working) not in result.stdout + result.stderr


def test_real_video_plan_matches_remux_execution(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("native media tools unavailable")
    baseline, working = collection_pair(tmp_path)
    first = baseline / "source.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=16x16:r=5:d=0.4",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            str(first),
        ],
        check=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(first),
            "-c",
            "copy",
            str(baseline / "remux.mov"),
        ],
        check=True,
    )
    shutil.copytree(baseline, working, dirs_exist_ok=True)
    _candidate, value = save_candidate(tmp_path, baseline, working)
    expected = {
        a["checkpoint"]: a["expected"] for a in value["policy"]["authorizations"]
    }
    assert expected["video-duplicates-apply"]["extra_copies"] == 1
    accepted = tmp_path / "private" / "accepted.json"
    accept_candidate(_candidate, accepted)
    result = run(
        "migrate",
        baseline,
        working,
        "--no-cache",
        "--log-dir",
        tmp_path / "logs",
        "--unattended",
        accepted,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Pre-authorized final sign-off recorded" in result.stdout
    assert len(list((working / "dups" / "vids").iterdir())) == 1


@pytest.mark.parametrize(
    "attack",
    [
        "duplicate-key",
        "extra-field",
        "wrong-kind",
        "wrong-version",
        "symlink",
        "hardlink",
        "public",
    ],
)
def test_malformed_or_unsafe_candidates_cannot_authorize(
    tmp_path: Path, attack: str
) -> None:
    baseline, working = collection_pair(tmp_path)
    candidate, value = save_candidate(tmp_path, baseline, working)
    if attack == "duplicate-key":
        candidate.write_bytes(
            candidate.read_bytes().replace(
                b'"schema_version":1', b'"schema_version":1,"schema_version":1'
            )
        )
    elif attack == "extra-field":
        value["authority"] = True
        candidate.write_bytes(canonical_bytes(value))
    elif attack == "wrong-kind":
        value["kind"] = "accepted"
        candidate.write_bytes(canonical_bytes(value))
    elif attack == "wrong-version":
        value["policy"]["tool_version"] = "0.0.0"
        candidate.write_bytes(canonical_bytes(value))
    elif attack == "symlink":
        original = candidate.with_name("original.json")
        candidate.rename(original)
        candidate.symlink_to(original)
    elif attack == "hardlink":
        os.link(candidate, candidate.with_name("second.json"))
    else:
        candidate.chmod(0o644)
    accepted = tmp_path / "private" / "accepted.json"
    assert (
        policy.main(
            [
                "accept",
                str(candidate),
                "--sha256",
                hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "--output",
                str(accepted),
                "--apply",
            ]
        )
        == 2
    )
    assert not accepted.exists()


def test_interrupted_artifact_write_never_publishes_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pymo.migration import policy_files

    baseline, working = collection_pair(tmp_path)
    destination = tmp_path / "private" / "policy.json"

    def interrupt(_fd: int) -> None:
        raise OSError("synthetic interrupted sync")

    monkeypatch.setattr(policy_files.os, "fsync", interrupt)
    with pytest.raises(OSError):
        policy_files.publish_private(
            destination, b'{"test":"synthetic"}\n', (baseline, working)
        )
    assert not destination.exists()
    scratch = list(destination.parent.glob(".pymo-policy-*.tmp"))
    assert len(scratch) == 1
    assert scratch[0].stat().st_mode & 0o777 == 0o600


def test_late_artifact_collision_preserves_both_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pymo.migration import policy_files

    baseline, working = collection_pair(tmp_path)
    destination = tmp_path / "private" / "policy.json"
    rename_no_replace = policy_files._atomic_rename_without_replace

    def collide(source_fd: int, source: str, target_fd: int, target: str) -> None:
        destination.write_bytes(b"existing operator file")
        rename_no_replace(source_fd, source, target_fd, target)

    monkeypatch.setattr(policy_files, "_atomic_rename_without_replace", collide)
    with pytest.raises(RuntimeError):
        policy_files.publish_private(destination, b"new artifact", (baseline, working))
    assert destination.read_bytes() == b"existing operator file"
    assert len(list(destination.parent.glob(".pymo-policy-*.tmp"))) == 1


def test_changed_namespace_between_children_stops_before_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collection_pair(tmp_path)
    media(baseline, working)
    _candidate, _ = save_candidate(tmp_path, baseline, working)
    accepted = tmp_path / "private" / "accepted.json"
    accept_candidate(_candidate, accepted)
    original = migrate._run_next

    def alter(*args, **kwargs):
        result = original(*args, **kwargs)
        (working / "unexpected.txt").write_text("synthetic late addition")
        return result

    monkeypatch.setattr(migrate, "_run_next", alter)
    result = migrate.main(
        [
            str(baseline),
            str(working),
            "--no-cache",
            "--log-dir",
            str(tmp_path / "logs"),
            "--unattended",
            str(accepted),
        ]
    )
    assert result == 2
    assert (working / "nested" / "wrong.jpg").exists()
    assert not (working / f"{working.name}-actions-log.jsonl").exists()


def test_collection_configuration_and_existing_review_tree_are_modeled(
    tmp_path: Path,
) -> None:
    baseline, working = collection_pair(tmp_path)
    media(baseline, working)
    for root in (baseline, working):
        (root / ".pymo.toml").write_text(
            'version = 1\n[ignore]\nfiles = ["retained-note.txt"]\n'
        )
        (root / "retained-note.txt").write_text("protected synthetic note")
    (working / "dups" / "pics").mkdir(parents=True)
    Image.new("RGB", (8, 8), "blue").save(working / "dups" / "pics" / "existing.png")
    _candidate, _ = save_candidate(tmp_path, baseline, working)
    accepted = tmp_path / "private" / "accepted.json"
    accept_candidate(_candidate, accepted)
    result = run(
        "migrate",
        baseline,
        working,
        "--no-cache",
        "--log-dir",
        tmp_path / "logs",
        "--unattended",
        accepted,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Pre-authorized final sign-off recorded" in result.stdout
    assert (working / "retained-note.txt").read_text() == "protected synthetic note"


def test_descriptor_reads_do_not_follow_a_swapped_logical_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pymo.classification import Classifier
    from pymo.config import load_config
    from pymo.migration.virtual import VirtualCollection

    baseline, working = collection_pair(tmp_path)
    media(baseline, working)
    view = VirtualCollection.capture(working, load_config(working))
    source = working / "nested" / "distinct.png"
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside payload must never be read")
    classifier = Classifier(view.config.classification)
    classify = classifier.classify
    read_payload = []

    def swap(path, descriptor=None):
        source.rename(source.with_suffix(".original"))
        source.symlink_to(outside)
        assert descriptor is not None
        read_payload.append(os.pread(descriptor, 8, 0))
        return classify(path, descriptor)

    monkeypatch.setattr(classifier, "classify", swap)
    from pymo.file_safety import FileChangedError

    with pytest.raises(FileChangedError):
        view.classify(source, classifier)
    assert read_payload == [b"\x89PNG\r\n\x1a\n"]
    assert outside.read_bytes() == b"outside payload must never be read"


def test_authored_run_resumes_after_completed_child_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline, working = collection_pair(tmp_path)
    _candidate, _ = save_candidate(tmp_path, baseline, working)
    accepted = tmp_path / "private" / "accepted.json"
    accept_candidate(_candidate, accepted)
    original = migrate._run_next

    def interrupt(*args, **kwargs):
        original(*args, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(migrate, "_run_next", interrupt)
    logs = tmp_path / "logs"
    with pytest.raises(KeyboardInterrupt):
        migrate.main(
            [
                str(baseline),
                str(working),
                "--no-cache",
                "--log-dir",
                str(logs),
                "--unattended",
                str(accepted),
            ]
        )
    assert migrate._load_state(logs / "pymo-migration-state.json").next_stage == 1
    result = run("migrate", "--resume", logs, "--unattended", accepted)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Pre-authorized final sign-off recorded" in result.stdout


@pytest.mark.parametrize("location", ["collection", "public"])
def test_candidate_output_requires_external_private_parent(
    tmp_path: Path, location: str
) -> None:
    baseline, working = collection_pair(tmp_path)
    parent = working if location == "collection" else tmp_path / "private"
    if location == "public":
        parent.chmod(0o755)
    destination = parent / "candidate.json"
    result = run(
        "policy", "plan", baseline, working, "--output", destination, "--apply"
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert not destination.exists()
    assert not list(working.rglob(".pymo-policy-*"))


@pytest.mark.parametrize(
    "layout", ["dups-file", "review-kind-file", "protected-nested-source"]
)
def test_underivable_duplicate_layout_is_rejected_before_candidate(
    tmp_path: Path, layout: str
) -> None:
    baseline, working = collection_pair(tmp_path)
    if layout == "dups-file":
        (working / "dups").write_text("reserved regular file")
    elif layout == "review-kind-file":
        (working / "dups").mkdir()
        (working / "dups" / "pics").write_text("reserved regular file")
    else:
        (working / "pics" / "nested").mkdir(parents=True)
        (working / "pics" / "nested" / ".DS_Store").write_text("ignored")
    with pytest.raises(PolicyPlanningError):
        build_candidate(baseline, working, migrate._initial_options({"no_cache": True}))


def test_extracted_candidate_policy_is_not_authority(tmp_path: Path) -> None:
    baseline, working = collection_pair(tmp_path)
    candidate, value = save_candidate(tmp_path, baseline, working)
    extracted = candidate.with_name("extracted.json")
    extracted.write_bytes(canonical_bytes(value["policy"]))
    extracted.chmod(0o600)
    result = run(
        "migrate",
        baseline,
        working,
        "--no-cache",
        "--log-dir",
        tmp_path / "logs",
        "--unattended",
        extracted,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert not (tmp_path / "logs").exists()
    assert snapshot(baseline) == snapshot(working) == {}


@pytest.mark.parametrize("boundary", ["policy", "receipt"])
def test_scratch_substitution_never_publishes_usable_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    from pymo.migration import policy_files
    from pymo.migration.policy_acceptance import receipt_path
    from pymo.migration.preauthorization import MigrationPreauthorizationError

    baseline, working = collection_pair(tmp_path)
    candidate, _ = save_candidate(tmp_path, baseline, working)
    other = candidate.with_name("other.json")
    accept_candidate(candidate, other)
    output = candidate.with_name("accepted.json")
    target_path = output if boundary == "policy" else receipt_path(output)
    substituted = (other if boundary == "policy" else receipt_path(other)).read_bytes()
    atomic = policy_files._atomic_rename_without_replace

    def swap(source_fd, source, target_fd, target):
        if target == target_path.name:
            os.rename(
                source, source + ".held", src_dir_fd=source_fd, dst_dir_fd=source_fd
            )
            fd = os.open(
                source, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=source_fd
            )
            try:
                os.write(fd, substituted)
            finally:
                os.close(fd)
        atomic(source_fd, source, target_fd, target)

    monkeypatch.setattr(policy_files, "_atomic_rename_without_replace", swap)
    assert (
        policy.main(
            [
                "accept",
                str(candidate),
                "--sha256",
                hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "--output",
                str(output),
                "--apply",
            ]
        )
        == 2
    )
    assert target_path.read_bytes() == substituted
    assert list(output.parent.glob(".pymo-policy-*.held"))
    with pytest.raises(MigrationPreauthorizationError):
        load_preauthorization(output, roots=(baseline, working))
    result = run(
        "migrate",
        baseline,
        working,
        "--no-cache",
        "--log-dir",
        tmp_path / "logs",
        "--unattended",
        output,
    )
    assert result.returncode == 2
    assert not (tmp_path / "logs").exists()
    assert snapshot(baseline) == snapshot(working) == {}


def test_interruption_after_policy_publication_grants_no_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pymo.migration import policy_acceptance
    from pymo.migration.preauthorization import MigrationPreauthorizationError

    baseline, working = collection_pair(tmp_path)
    candidate, _ = save_candidate(tmp_path, baseline, working)
    output = candidate.with_name("accepted.json")
    publish = policy_acceptance.publish_private

    def interrupt(path, payload, roots):
        if path == policy_acceptance.receipt_path(output):
            raise OSError("synthetic interruption before receipt")
        publish(path, payload, roots)

    monkeypatch.setattr(policy_acceptance, "publish_private", interrupt)
    assert (
        policy.main(
            [
                "accept",
                str(candidate),
                "--sha256",
                hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "--output",
                str(output),
                "--apply",
            ]
        )
        == 2
    )
    assert output.exists()
    assert not policy_acceptance.receipt_path(output).exists()
    with pytest.raises(MigrationPreauthorizationError):
        load_preauthorization(output, roots=(baseline, working))


@pytest.mark.parametrize(
    "attack",
    ["missing", "wrong-hash", "duplicate-key", "symlink", "hardlink", "public"],
)
def test_acceptance_receipt_is_required_and_strict(tmp_path: Path, attack: str) -> None:
    import json

    from pymo.migration.policy_acceptance import receipt_path
    from pymo.migration.preauthorization import MigrationPreauthorizationError

    baseline, working = collection_pair(tmp_path)
    candidate, _ = save_candidate(tmp_path, baseline, working)
    output = candidate.with_name("accepted.json")
    accept_candidate(candidate, output)
    receipt = receipt_path(output)
    saved = receipt.with_suffix(".saved")
    receipt.rename(saved)
    if attack == "wrong-hash":
        value = json.loads(saved.read_bytes())
        value["policy_sha256"] = "0" * 64
        receipt.write_bytes(canonical_bytes(value))
        receipt.chmod(0o600)
    elif attack == "duplicate-key":
        receipt.write_bytes(
            saved.read_bytes().replace(b"{", b'{"kind":"accepted-migration-policy",', 1)
        )
        receipt.chmod(0o600)
    elif attack == "symlink":
        receipt.symlink_to(saved)
    elif attack == "hardlink":
        os.link(saved, receipt)
    elif attack == "public":
        receipt.write_bytes(saved.read_bytes())
        receipt.chmod(0o644)
    with pytest.raises(MigrationPreauthorizationError):
        load_preauthorization(output, roots=(baseline, working))
    result = run(
        "migrate",
        baseline,
        working,
        "--no-cache",
        "--log-dir",
        tmp_path / "logs",
        "--unattended",
        output,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert not (tmp_path / "logs").exists()


def test_receipt_replacement_during_execution_is_rejected(tmp_path: Path) -> None:
    from pymo.migration.policy_acceptance import receipt_path
    from pymo.migration.preauthorization import MigrationPreauthorizationError

    baseline, working = collection_pair(tmp_path)
    candidate, _ = save_candidate(tmp_path, baseline, working)
    output = candidate.with_name("accepted.json")
    accept_candidate(candidate, output)
    authorized = load_preauthorization(output, roots=(baseline, working))
    receipt = receipt_path(output)
    replacement = receipt.with_suffix(".replacement")
    replacement.write_bytes(receipt.read_bytes())
    replacement.chmod(0o600)
    os.replace(replacement, receipt)
    with pytest.raises(MigrationPreauthorizationError):
        authorized.require_current()
