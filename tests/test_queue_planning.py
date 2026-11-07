from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pymo import __version__, migrate, queue
from pymo.managed_quarantine import destination_binding_sha256
from pymo.migration import policy_acceptance, policy_files, queue_manifest, queue_plan
from pymo.migration.policy_acceptance import publish_accepted, receipt_path
from pymo.migration.policy_plan import build_candidate
from pymo.migration.queue_manifest import PrivateArtifact
from pymo.migration.virtual import canonical_bytes


def write(path: Path, value: object) -> None:
    path.write_bytes(canonical_bytes(value))
    path.chmod(0o600)


def identity(path: Path) -> list[int]:
    value = path.stat()
    return [value.st_dev, value.st_ino]


def snapshot(root: Path) -> dict:
    return {
        str(p.relative_to(root)): (
            p.lstat().st_ino,
            p.lstat().st_mtime_ns,
            p.lstat().st_mode,
            p.read_bytes() if p.is_file() else None,
        )
        for p in root.rglob("*")
    }


def job(root: Path, number: int, *, authored: bool = False) -> dict:
    baseline = root / f"baseline-{number}"
    working = root / f"collection-{number}"
    baseline.mkdir()
    working.mkdir()
    private = root / "private"
    private.mkdir(mode=0o700, exist_ok=True)
    candidate = build_candidate(
        baseline, working, migrate._initial_options({"no_cache": True})
    )
    policy = candidate["policy"]
    policy_path = private / f"policy-{number}.json"
    if authored:
        publish_accepted(
            policy_path,
            policy,
            hashlib.sha256(canonical_bytes(candidate)).hexdigest(),
            (baseline, working),
        )
    else:
        policy.pop("plan_binding")
        policy["schema_version"] = 4
        write(policy_path, policy)
    return {
        "baseline": {"path": str(baseline), "identity": identity(baseline)},
        "working": {"path": str(working), "identity": identity(working)},
        "state_directory": str(private / f"state-{number}"),
        "policy": {
            "path": str(policy_path),
            "sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        },
        "disposition": "retained-in-place",
        "quarantine": None,
    }


def save_manifest(root: Path, entries: list[dict]) -> Path:
    path = root / "private" / "queue.json"
    write(path, {"schema_version": 1, "tool_version": __version__, "entries": entries})
    return path


def change_policy(entry: dict, mutate) -> None:
    path = Path(entry["policy"]["path"])
    value = json.loads(path.read_bytes())
    mutate(value)
    write(path, value)
    entry["policy"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def run(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pymo", *(str(a) for a in arguments)],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def test_complete_ordered_plan_is_private_deterministic_and_zero_write(
    tmp_path: Path,
) -> None:
    entries = [job(tmp_path, 1, authored=True), job(tmp_path, 2)]
    # Deliberately uninspectable content is not opened by declaration planning.
    (Path(entries[0]["working"]["path"]) / "private-photo.jpg").write_bytes(
        b"not media"
    )
    manifest = save_manifest(tmp_path, entries)
    before = snapshot(tmp_path)
    first = run("queue", "plan", manifest, "--json")
    second = run("--visibility", "full", "queue", "plan", manifest, "--json")
    assert first.returncode == second.returncode == 0, first.stderr + second.stderr
    assert first.stdout == second.stdout
    report = json.loads(first.stdout)
    assert report["schema_version"] == 1
    assert report["execution"] == "not-started"
    assert report["media_evidence"] == report["capacity"] == "not-checked"
    assert not report["destinations_reserved"] and not report["authority_created"]
    assert [j["ordinal"] for j in report["jobs"]] == [1, 2]
    assert [j["policy_kind"] for j in report["jobs"]] == ["authored", "manual"]
    steps = report["jobs"][0]["steps"]
    assert [s["stage"] for s in steps] == [
        s.identifier for s in queue_plan._stages()
    ] + ["final-signoff"]
    assert len([s for s in steps if s["decision"]]) == 10
    assert str(tmp_path) not in first.stdout + first.stderr
    assert "private-photo" not in first.stdout + first.stderr
    assert entries[0]["policy"]["sha256"] not in first.stdout
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "boolean-schema",
        "future-schema",
        "version",
        "empty",
        "non-list",
        "relative",
        "identity-bool",
        "identity-change",
        "unknown-job",
        "bad-digest",
        "bad-disposition",
        "unmanaged-target",
        "non-finite",
    ],
)
def test_strict_manifest_refusal(tmp_path: Path, mutation: str) -> None:
    entry = job(tmp_path, 1)
    manifest = save_manifest(tmp_path, [entry])
    value = json.loads(manifest.read_bytes())
    if mutation == "unknown":
        value["other"] = 1
    elif mutation == "boolean-schema":
        value["schema_version"] = True
    elif mutation == "future-schema":
        value["schema_version"] = 2
    elif mutation == "version":
        value["tool_version"] = "0.0.0"
    elif mutation == "empty":
        value["entries"] = []
    elif mutation == "non-list":
        value["entries"] = {}
    elif mutation == "relative":
        value["entries"][0]["working"]["path"] = "relative"
    elif mutation == "identity-bool":
        value["entries"][0]["working"]["identity"][0] = True
    elif mutation == "identity-change":
        value["entries"][0]["working"]["identity"][1] += 1
    elif mutation == "unknown-job":
        value["entries"][0]["unexpected"] = "sensitive"
    elif mutation == "bad-digest":
        value["entries"][0]["policy"]["sha256"] = "0" * 64
    elif mutation == "bad-disposition":
        value["entries"][0]["disposition"] = []
    elif mutation == "unmanaged-target":
        value["entries"][0]["quarantine"] = {}
    elif mutation == "non-finite":
        value["entries"][0]["working"]["identity"][0] = float("nan")
    manifest.write_text(json.dumps(value))
    before = snapshot(tmp_path)
    result = run("queue", "plan", manifest, "--json")
    assert result.returncode == 2
    assert result.stdout == ""
    assert str(tmp_path) not in result.stderr and "Traceback" not in result.stderr
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "partial",
        "reordered",
        "version",
        "root",
        "decision",
        "candidate",
        "unknown",
        "duplicate-key",
    ],
)
def test_policy_is_complete_exact_and_authorized(tmp_path: Path, mutation: str) -> None:
    entry = job(tmp_path, 1)

    def mutate(value: dict) -> None:
        if mutation == "partial":
            value["authorizations"].pop()
        elif mutation == "reordered":
            value["authorizations"].reverse()
        elif mutation == "version":
            value["tool_version"] = "other"
        elif mutation == "root":
            value["baseline"] = entry["working"]["path"]
        elif mutation == "decision":
            value["authorizations"][7]["decision"] = "confirm-quarantine"
        elif mutation == "candidate":
            value["kind"] = "unaccepted-migration-plan"
        elif mutation == "unknown":
            value["options"]["unexpected"] = True

    change_policy(entry, mutate)
    if mutation == "duplicate-key":
        path = Path(entry["policy"]["path"])
        path.write_bytes(b'{"schema_version":4,' + path.read_bytes()[1:])
        entry["policy"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = save_manifest(tmp_path, [entry])
    assert queue.main(["plan", str(manifest), "--json"]) == 2


@pytest.mark.parametrize(
    "mutation",
    [
        "shared-baseline",
        "cross-role",
        "nested-root",
        "shared-state",
        "state-in-root",
        "policy-in-other-root",
        "manifest-in-root",
        "case-alias",
        "unicode-alias",
        "occupied-state",
        "missing-parent",
        "symlink-root",
        "symlink-parent",
    ],
)
def test_global_namespace_conflicts_stop_before_policy_reads(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    first, second = entries
    if mutation == "shared-baseline":
        second["baseline"] = first["baseline"]
    elif mutation == "cross-role":
        second["working"] = first["baseline"]
    elif mutation == "nested-root":
        p = Path(first["working"]["path"]) / "nested"
        p.mkdir()
        second["baseline"] = {"path": str(p), "identity": identity(p)}
    elif mutation == "shared-state":
        second["state_directory"] = first["state_directory"]
    elif mutation == "state-in-root":
        second["state_directory"] = str(Path(first["working"]["path"]) / "state")
    elif mutation == "policy-in-other-root":
        second["policy"]["path"] = str(Path(first["working"]["path"]) / "file.json")
    elif mutation == "case-alias":
        second["state_directory"] = first["state_directory"].replace(
            "state-1", "STATE-1"
        )
    elif mutation == "unicode-alias":
        first["state_directory"] = str(tmp_path / "private" / "café")
        second["state_directory"] = str(tmp_path / "private" / "cafe\u0301")
    elif mutation == "occupied-state":
        Path(second["state_directory"]).mkdir(mode=0o700)
    elif mutation == "missing-parent":
        second["state_directory"] += "/nested"
    elif mutation == "symlink-root":
        p = tmp_path / "alias"
        p.symlink_to(first["baseline"]["path"], target_is_directory=True)
        second["baseline"]["path"] = str(p)
    elif mutation == "symlink-parent":
        p = tmp_path / "alias"
        p.symlink_to(tmp_path / "private", target_is_directory=True)
        second["state_directory"] = str(p / "state")
    manifest = save_manifest(tmp_path, entries)
    if mutation == "manifest-in-root":
        new = Path(first["baseline"]["path"]) / "manifest.json"
        manifest.rename(new)
        manifest = new
    original = PrivateArtifact.read.__func__
    opened = []

    def read(cls, path):
        opened.append(path)
        return original(cls, path)

    monkeypatch.setattr(PrivateArtifact, "read", classmethod(read))
    assert queue.main(["plan", str(manifest), "--json"]) == 2
    assert opened == [manifest]


@pytest.mark.parametrize(
    "mutation",
    [
        "public-manifest",
        "public-parent",
        "hardlink",
        "symlink",
        "duplicate-json",
        "oversize",
        "missing-receipt",
        "replaced-receipt",
    ],
)
def test_private_artifact_boundary(tmp_path: Path, mutation: str) -> None:
    entry = job(tmp_path, 1, authored=True)
    manifest = save_manifest(tmp_path, [entry])
    if mutation == "public-manifest":
        manifest.chmod(0o644)
    elif mutation == "public-parent":
        manifest.parent.chmod(0o755)
    elif mutation == "hardlink":
        os.link(manifest, manifest.with_suffix(".link"))
    elif mutation == "symlink":
        alias = manifest.with_suffix(".link")
        alias.symlink_to(manifest)
        manifest = alias
    elif mutation == "duplicate-json":
        manifest.write_bytes(b'{"schema_version":1,' + manifest.read_bytes()[1:])
    elif mutation == "oversize":
        manifest.write_bytes(b" " * (1024 * 1024 + 1))
    elif mutation == "missing-receipt":
        receipt_path(Path(entry["policy"]["path"])).rename(tmp_path / "saved-receipt")
    elif mutation == "replaced-receipt":
        receipt = receipt_path(Path(entry["policy"]["path"]))
        payload = receipt.read_bytes()
        receipt.rename(tmp_path / "saved-receipt")
        receipt.write_bytes(payload)
        receipt.chmod(0o600)
    before = snapshot(tmp_path)
    assert queue.main(["plan", str(manifest), "--json"]) == 2
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "mutation", ["manifest", "policy", "receipt", "root", "state", "parent"]
)
def test_late_changes_emit_no_successful_plan(
    tmp_path: Path, monkeypatch, capsys, mutation: str
) -> None:
    entry = job(tmp_path, 1, authored=True)
    manifest = save_manifest(tmp_path, [entry])
    original = queue_plan._steps

    def change(policy):
        result = original(policy)
        if mutation in {"manifest", "policy", "receipt"}:
            path = {
                "manifest": manifest,
                "policy": Path(entry["policy"]["path"]),
                "receipt": receipt_path(Path(entry["policy"]["path"])),
            }[mutation]
            payload = path.read_bytes()
            path.rename(tmp_path / "saved")
            path.write_bytes(payload)
            path.chmod(0o600)
        elif mutation == "root":
            path = Path(entry["working"]["path"])
            path.rename(tmp_path / "saved")
            path.mkdir()
        elif mutation == "state":
            Path(entry["state_directory"]).mkdir(mode=0o700)
        elif mutation == "parent":
            path = manifest.parent
            path.rename(tmp_path / "saved")
            path.symlink_to(tmp_path / "saved", target_is_directory=True)
        return result

    monkeypatch.setattr(queue_plan, "_steps", change)
    assert queue.main(["plan", str(manifest), "--json"]) == 2
    output = capsys.readouterr()
    assert output.out == ""


def managed(entry: dict, destination: Path, *, copy_mode: bool = False) -> None:
    entry["disposition"] = "retained-copy" if copy_mode else "managed-same-filesystem"
    entry["quarantine"] = {
        "destination": str(destination),
        "copy_reserve_bytes": 123 if copy_mode else None,
    }

    def mutate(policy):
        policy["options"]["quarantine_destination"] = str(destination)
        policy["options"]["quarantine_copy_reserve_bytes"] = 123 if copy_mode else None
        auth = policy["authorizations"][7]
        auth["decision"] = "quarantine-dups"
        auth["expected"]["quarantine_plan"] = {
            "method": "copy" if copy_mode else "rename",
            "copy_reserve_bytes": 123 if copy_mode else 0,
            "metadata_entries": 0,
            "metadata_unknown": 0,
            "status": 0,
            "files": 0,
            "directories": 1,
            "bytes": 0,
            "manifest_sha256": "0" * 64,
            "destination_sha256": destination_binding_sha256(destination),
            "destination_parent_device": destination.parent.stat().st_dev,
            "destination_parent_inode": destination.parent.stat().st_ino,
            "decision_digest": "migration-decision-v1:" + "0" * 64,
        }

    change_policy(entry, mutate)


def test_managed_and_external_dispositions_remain_explicit(tmp_path: Path) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    managed(entries[0], tmp_path / "quarantine")
    entries[1]["disposition"] = "external-quarantine"
    change_policy(
        entries[1],
        lambda p: p["authorizations"][7].update(decision="confirm-quarantine"),
    )
    manifest = save_manifest(tmp_path, entries)
    before = snapshot(tmp_path)
    report = queue_plan.build_queue_plan(manifest)
    assert len(report["jobs"][0]["steps"]) == 27
    assert report["jobs"][1]["human_external_quarantine_required"]
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "copy-same-device",
        "parent-identity",
        "destination-digest",
        "reserve",
        "method",
        "shared-target",
        "target-in-root",
        "occupied",
        "state-target",
    ],
)
def test_quarantine_bindings_and_cross_job_conflicts(
    tmp_path: Path, mutation: str
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    target = tmp_path / "quarantine"
    if mutation == "target-in-root":
        target = Path(entries[1]["baseline"]["path"]) / "quarantine"
    elif mutation == "state-target":
        target = Path(entries[1]["state_directory"])
    managed(entries[0], target, copy_mode=mutation == "copy-same-device")
    if mutation == "shared-target":
        managed(entries[1], target)
    elif mutation == "occupied":
        target.mkdir()
    elif mutation in {"parent-identity", "destination-digest", "reserve", "method"}:
        key, value = {
            "parent-identity": ("destination_parent_inode", 0),
            "destination-digest": ("destination_sha256", "f" * 64),
            "reserve": ("copy_reserve_bytes", 1),
            "method": ("method", "copy"),
        }[mutation]
        change_policy(
            entries[0],
            lambda p: p["authorizations"][7]["expected"]["quarantine_plan"].update(
                {key: value}
            ),
        )
    manifest = save_manifest(tmp_path, entries)
    before = snapshot(tmp_path)
    assert queue.main(["plan", str(manifest), "--json"]) == 2
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "arguments", [["--apply"], ["--run"], ["--show-files"], ["--show-ignored"]]
)
def test_queue_rejects_execution_and_disclosure(
    tmp_path: Path, arguments: list[str]
) -> None:
    manifest = save_manifest(tmp_path, [job(tmp_path, 1)])
    before = snapshot(tmp_path)
    result = run("queue", "plan", manifest, *arguments)
    assert result.returncode == 2
    assert snapshot(tmp_path) == before


def test_global_logging_rejected_before_creation_and_late_job_failure_has_no_plan(
    tmp_path: Path,
) -> None:
    entries = [job(tmp_path, 1), job(tmp_path, 2)]
    manifest = save_manifest(tmp_path, entries)
    log = tmp_path / "log"
    assert run("--log-file", log, "queue", "plan", manifest).returncode == 2
    assert not log.exists()
    entries[1]["policy"]["sha256"] = "0" * 64
    save_manifest(tmp_path, entries)
    result = run("queue", "plan", manifest, "--json")
    assert result.returncode == 2 and result.stdout == ""


def test_human_plan_and_shared_private_parent(tmp_path: Path) -> None:
    manifest = save_manifest(tmp_path, [job(tmp_path, 1), job(tmp_path, 2)])
    result = run("--no-timestamps", "queue", "plan", manifest)
    assert result.returncode == 0
    assert "2 jobs in declared sequential order" in result.stdout
    assert "Media evidence and capacity were not checked" in result.stdout
    assert str(tmp_path) not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "leaf", ["manifest.json", "policy.json", "policy.json.acceptance.json"]
)
@pytest.mark.parametrize("when", ["ancestor-open", "leaf-open"])
def test_transient_ancestor_link_never_opens_outside_artifact(
    tmp_path: Path, monkeypatch, leaf: str, when: str
) -> None:
    anchor = tmp_path / "anchor"
    parent = anchor / "private"
    outside = tmp_path / "outside"
    for root in (anchor, outside):
        root.mkdir(mode=0o700)
        (root / "private").mkdir(mode=0o700)
        write(root / "private" / leaf, {"origin": root.name})
    expected_outside = identity(outside / "private" / leaf)
    original_open = os.open
    outside_opened = False
    swapped = False
    parent_opens = 0
    saved = tmp_path / "saved"

    def guarded_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal outside_opened, swapped, parent_opens
        spelling = os.fspath(path)
        if spelling == str(parent):
            parent_opens += 1
        # Exercise both the previous full-path reopen and the corrected
        # component-relative traversal with the same adversarial substitution.
        trigger = (
            spelling == leaf
            if when == "leaf-open"
            else spelling == "anchor" or (spelling == str(parent) and parent_opens == 2)
        )
        if trigger and not swapped:
            anchor.rename(saved)
            anchor.symlink_to(outside, target_is_directory=True)
            swapped = True
        descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
        value = os.fstat(descriptor)
        if [value.st_dev, value.st_ino] == expected_outside:
            outside_opened = True
        return descriptor

    monkeypatch.setattr(os, "open", guarded_open)
    try:
        with pytest.raises((OSError, RuntimeError)):
            PrivateArtifact.read(parent / leaf)
    finally:
        if swapped:
            anchor.unlink()  # synthetic attack link only
            saved.rename(anchor)
    assert swapped
    assert not outside_opened


def test_replaced_parent_cannot_inherit_observed_queue_binding(
    tmp_path: Path, monkeypatch
) -> None:
    parent = tmp_path / "private"
    other = tmp_path / "other"
    for path in (parent, other):
        path.mkdir(mode=0o700)
        write(path / "manifest.json", {"origin": path.name})
    original = queue_manifest.read_private_identity
    original_open = os.open
    outside_identity = identity(other / "manifest.json")
    outside_opened = False

    def observed_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal outside_opened
        fd = original_open(path, flags, mode, dir_fd=dir_fd)
        value = os.fstat(fd)
        outside_opened |= [value.st_dev, value.st_ino] == outside_identity
        return fd

    def swap(path, **kwargs):
        parent.rename(tmp_path / "saved")
        other.rename(parent)
        try:
            return original(path, **kwargs)
        finally:
            parent.rename(other)
            (tmp_path / "saved").rename(parent)

    monkeypatch.setattr(os, "open", observed_open)
    monkeypatch.setattr(queue_manifest, "read_private_identity", swap)
    with pytest.raises(RuntimeError):
        PrivateArtifact.read(parent / "manifest.json")
    assert not outside_opened


def test_retained_copy_plan_with_controlled_distinct_device_topology(
    tmp_path: Path, monkeypatch
) -> None:
    entry = job(tmp_path, 1)
    managed(entry, tmp_path / "quarantine", copy_mode=True)
    working = Path(entry["working"]["path"])
    original = queue_manifest.observe_endpoint
    entry["working"]["identity"][0] += 1

    def distinct(path, *, missing=False):
        observed = original(path, missing=missing)
        if path == working and not missing:
            return replace(
                observed,
                ancestry=(
                    (observed.identity[0] + 1, observed.identity[1]),
                    *observed.ancestry[1:],
                ),
            )
        return observed

    monkeypatch.setattr(queue_manifest, "observe_endpoint", distinct)
    monkeypatch.setattr(queue_plan, "observe_endpoint", distinct)
    manifest = save_manifest(tmp_path, [entry])
    before = snapshot(tmp_path)
    result = queue_plan.build_queue_plan(manifest)
    assert result["jobs"][0]["disposition"] == "retained-copy"
    assert len(result["jobs"][0]["steps"]) == 27
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "phase",
    [
        "initial-policy",
        "parse-policy",
        "parse-receipt",
        "receipt-bookkeeping",
        "current-receipt",
    ],
)
def test_queue_never_rebinds_nested_artifacts_to_a_replaced_parent(
    tmp_path: Path, monkeypatch, capsys, phase: str
) -> None:
    entry = job(tmp_path, 1, authored=True)
    manifest = save_manifest(tmp_path, [entry])
    parent = manifest.parent
    other = tmp_path / "other-private"
    other.mkdir(mode=0o700)
    for item in parent.iterdir():
        (other / item.name).write_bytes(item.read_bytes())
        (other / item.name).chmod(0o600)
    unrelated = {tuple(identity(p)) for p in other.iterdir()}
    outside_opened = False
    swapped = False
    original_open = os.open
    original_read = policy_acceptance.read_private_identity
    original_artifact = PrivateArtifact.read.__func__
    policy_path = Path(entry["policy"]["path"])
    receipt = receipt_path(policy_path)
    receipt_reads = 0

    def observed_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal outside_opened
        fd = original_open(path, flags, mode, dir_fd=dir_fd)
        value = os.fstat(fd)
        outside_opened |= (value.st_dev, value.st_ino) in unrelated
        return fd

    def substitute(callback):
        nonlocal swapped
        assert not swapped
        swapped = True
        parent.rename(tmp_path / "saved-private")
        other.rename(parent)
        try:
            return callback()
        finally:
            parent.rename(other)
            (tmp_path / "saved-private").rename(parent)

    def nested_read(path, **kwargs):
        nonlocal receipt_reads
        if path == receipt:
            receipt_reads += 1
        trigger = (
            (phase == "parse-policy" and path == policy_path)
            or (phase == "parse-receipt" and path == receipt)
            or (phase == "current-receipt" and path == receipt and receipt_reads == 2)
        )
        if trigger and not swapped:
            return substitute(lambda: original_read(path, **kwargs))
        return original_read(path, **kwargs)

    def artifact_read(cls, path, **kwargs):
        trigger = (phase == "initial-policy" and path == policy_path) or (
            phase == "receipt-bookkeeping" and path == receipt
        )
        if trigger and not swapped:
            return substitute(lambda: original_artifact(cls, path, **kwargs))
        return original_artifact(cls, path, **kwargs)

    monkeypatch.setattr(os, "open", observed_open)
    monkeypatch.setattr(policy_acceptance, "read_private_identity", nested_read)
    monkeypatch.setattr(PrivateArtifact, "read", classmethod(artifact_read))
    assert queue.main(["plan", str(manifest), "--json"]) == 2
    assert capsys.readouterr().out == ""
    assert swapped and not outside_opened


def test_private_reader_preserves_relative_parent_locator(
    tmp_path: Path, monkeypatch
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    nested = private / "nested"
    nested.mkdir(mode=0o700)
    artifact = private / "candidate.json"
    write(artifact, {"synthetic": True})
    monkeypatch.chdir(nested)
    assert policy_files.read_private(Path("../candidate.json")) == artifact.read_bytes()
