"""Strict private queue declarations and no-follow endpoint observations."""

from __future__ import annotations

import json
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pymo import __version__
from pymo.migration.policy_files import read_private_identity
from pymo.migration.preauthorization import (
    _object_without_duplicate_keys,
    _require_exact_fields,
    _validate_sha256,
)
from pymo.migration.unattended_binding import require_private_unattended_log_directory

# Public declaration contract; incompatible field or meaning changes increment it.
QUEUE_MANIFEST_SCHEMA_VERSION = 1


class QueuePlanningError(RuntimeError):
    """The complete declaration cannot be validated without ambiguity."""


def absolute_path(value: object) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise QueuePlanningError("invalid path declaration")
    path = Path(value)
    if not path.is_absolute() or str(path) != value or ".." in path.parts:
        raise QueuePlanningError("paths must be normalized and absolute")
    return path


def identity_pair(value: object) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(part) is not int or part < 0 for part in value)
    ):
        raise QueuePlanningError("invalid directory identity")
    return value[0], value[1]


@dataclass(frozen=True)
class Endpoint:
    path: Path
    # Ordered from leaf directory (or leaf parent) to filesystem root.
    ancestry: tuple[tuple[int, int], ...]
    missing: bool

    @property
    def identity(self) -> tuple[int, int]:
        return self.ancestry[0]

    def require_current(self) -> None:
        if observe_endpoint(self.path, missing=self.missing) != self:
            raise QueuePlanningError("an endpoint changed during planning")


def observe_endpoint(path: Path, *, missing: bool = False) -> Endpoint:
    """Observe only metadata, rejecting links at every directory component."""
    if missing:
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise QueuePlanningError("a destination is already occupied")
    current = path.parent if missing else path
    ancestry: list[tuple[int, int]] = []
    while True:
        value = current.lstat()
        if not stat.S_ISDIR(value.st_mode):
            raise QueuePlanningError("directory ancestry is unsafe")
        ancestry.append((value.st_dev, value.st_ino))
        if current.parent == current:
            break
        current = current.parent
    # Canonical spelling avoids ambiguous policy bindings without accepting links.
    existing = path.parent if missing else path
    if existing.resolve(strict=True) != existing:
        raise QueuePlanningError("directory spelling must be canonical")
    return Endpoint(path, tuple(ancestry), missing)


def endpoints_overlap(first: Endpoint, second: Endpoint) -> bool:
    if not first.missing and first.identity in second.ancestry:
        return True
    if not second.missing and second.identity in first.ancestry:
        return True
    if first.missing and second.missing and first.identity == second.identity:
        # There is no inode to compare for absent leaves. Conservatively reject
        # normalization/case aliases even on a case-sensitive filesystem.
        return unicodedata.normalize("NFD", first.path.name).casefold() == (
            unicodedata.normalize("NFD", second.path.name).casefold()
        )
    return False


@dataclass(frozen=True)
class PrivateArtifact:
    path: Path
    payload: bytes
    identity: tuple[int, ...]
    parent: Endpoint

    @classmethod
    def read(cls, path: Path) -> PrivateArtifact:
        parent = observe_endpoint(path.parent)
        payload, identity = read_private_identity(
            path, expected_ancestry=parent.ancestry
        )
        parent.require_current()
        return cls(path, payload, identity, parent)

    def require_current(self) -> None:
        self.parent.require_current()
        if read_private_identity(self.path, expected_ancestry=self.parent.ancestry) != (
            self.payload,
            self.identity,
        ):
            raise QueuePlanningError("a private declaration changed during planning")


@dataclass(frozen=True)
class QueueJob:
    baseline: Path
    baseline_identity: tuple[int, int]
    working: Path
    working_identity: tuple[int, int]
    state_directory: Path
    policy: Path
    policy_sha256: str
    disposition: str
    quarantine_destination: Path | None
    copy_reserve_bytes: int | None


def _job(value: object) -> QueueJob:
    entry = _require_exact_fields(
        value,
        {
            "baseline",
            "working",
            "state_directory",
            "policy",
            "disposition",
            "quarantine",
        },
        "queue entry",
    )
    roots = [
        _require_exact_fields(entry[key], {"path", "identity"}, "queue root")
        for key in ("baseline", "working")
    ]
    policy = _require_exact_fields(entry["policy"], {"path", "sha256"}, "queue policy")
    disposition = entry["disposition"]
    if not isinstance(disposition, str) or disposition not in {
        "retained-in-place",
        "managed-same-filesystem",
        "retained-copy",
        "external-quarantine",
    }:
        raise QueuePlanningError("unsupported duplicate disposition")
    destination = None
    reserve = None
    if disposition in {"managed-same-filesystem", "retained-copy"}:
        quarantine = _require_exact_fields(
            entry["quarantine"],
            {"destination", "copy_reserve_bytes"},
            "queue quarantine",
        )
        destination = absolute_path(quarantine["destination"])
        reserve = quarantine["copy_reserve_bytes"]
        if disposition == "retained-copy":
            if type(reserve) is not int or reserve < 0:
                raise QueuePlanningError(
                    "copy mode requires an explicit nonnegative reserve"
                )
        elif reserve is not None:
            raise QueuePlanningError("rename mode does not accept a copy reserve")
    elif entry["quarantine"] is not None:
        raise QueuePlanningError("this disposition has no managed destination")
    return QueueJob(
        absolute_path(roots[0]["path"]),
        identity_pair(roots[0]["identity"]),
        absolute_path(roots[1]["path"]),
        identity_pair(roots[1]["identity"]),
        absolute_path(entry["state_directory"]),
        absolute_path(policy["path"]),
        _validate_sha256(policy["sha256"], "queue policy digest"),
        disposition,
        destination,
        reserve,
    )


def _reject_constant(value: str) -> Any:
    raise QueuePlanningError("non-finite JSON is not supported")


def parse_manifest(artifact: PrivateArtifact) -> tuple[QueueJob, ...]:
    if len(artifact.payload) > 1024 * 1024:
        raise QueuePlanningError("manifest exceeds one MiB")
    value = json.loads(
        artifact.payload,
        object_pairs_hook=_object_without_duplicate_keys,
        parse_constant=_reject_constant,
    )
    manifest = _require_exact_fields(
        value, {"schema_version", "tool_version", "entries"}, "queue manifest"
    )
    if (
        type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != QUEUE_MANIFEST_SCHEMA_VERSION
        or manifest["tool_version"] != __version__
    ):
        raise QueuePlanningError("manifest schema or installed version differs")
    entries = manifest["entries"]
    if not isinstance(entries, list) or not entries:
        raise QueuePlanningError("a queue must contain at least one entry")
    return tuple(_job(entry) for entry in entries)


def private_state_destination(path: Path) -> Endpoint:
    result = observe_endpoint(path, missing=True)
    require_private_unattended_log_directory(path.parent)
    return result
