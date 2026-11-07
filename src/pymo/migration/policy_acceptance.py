"""Separate create-once acceptance evidence for authored policy authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pymo import __version__
from pymo.migration.outcome import _require_external_private_parent
from pymo.migration.policy_files import publish_private, read_private_identity
from pymo.migration.preauthorization import (
    MigrationPreauthorizationError,
    _object_without_duplicate_keys,
    _require_exact_fields,
    _validate_sha256,
)
from pymo.migration.virtual import canonical_bytes

# Independent on-disk acceptance contract; an unaccepted candidate has none.
POLICY_ACCEPTANCE_SCHEMA_VERSION = 1


def receipt_path(policy_path: Path) -> Path:
    return policy_path.with_name(policy_path.name + ".acceptance.json")


def publish_accepted(
    output: Path,
    proposed: dict[str, Any],
    candidate_sha256: str,
    roots: tuple[Path, Path],
) -> None:
    path = _require_external_private_parent(output, roots)
    record = receipt_path(path)
    if record.exists() or record.is_symlink():
        raise MigrationPreauthorizationError("acceptance destination is occupied")
    policy = {
        **proposed,
        "acceptance": {"candidate_sha256": candidate_sha256, "record": str(record)},
    }
    payload = canonical_bytes(policy)
    # Presence of this file alone grants no authority. Receipt publication is
    # reached only after the exact published policy has passed verification.
    publish_private(path, payload, roots)
    actual, identity = read_private_identity(path)
    if actual != payload:
        raise MigrationPreauthorizationError("published policy bytes changed")
    receipt = {
        "schema_version": POLICY_ACCEPTANCE_SCHEMA_VERSION,
        "kind": "accepted-migration-policy",
        "tool_version": __version__,
        "candidate_sha256": candidate_sha256,
        "policy_path": str(path),
        "policy_sha256": hashlib.sha256(payload).hexdigest(),
        "policy_identity": list(identity[:2]),
    }
    # The receipt binds its own exclusively allocated inode before publication.
    # A same-byte replacement cannot inherit that identity after a failed rename.
    publish_private(
        record,
        lambda allocated: canonical_bytes(
            {**receipt, "record_identity": list(allocated)}
        ),
        roots,
    )
    accepted = load_acceptance(path, payload, policy["acceptance"])
    accepted.require_current()
    if read_private_identity(path) != (payload, identity):
        raise MigrationPreauthorizationError(
            "accepted policy changed during publication"
        )


@dataclass(frozen=True)
class PolicyAcceptance:
    policy_path: Path
    policy_payload: bytes
    policy_identity: tuple[int, ...]
    path: Path
    payload: bytes
    identity: tuple[int, ...]

    def require_current(self) -> None:
        try:
            if read_private_identity(self.policy_path) != (
                self.policy_payload,
                self.policy_identity,
            ) or read_private_identity(self.path) != (self.payload, self.identity):
                raise MigrationPreauthorizationError(
                    "policy acceptance evidence changed"
                )
        except (OSError, ValueError, RuntimeError) as error:
            raise MigrationPreauthorizationError(
                "policy acceptance evidence cannot be verified"
            ) from error


def load_acceptance(path: Path, payload: bytes, value: object) -> PolicyAcceptance:
    declaration = _require_exact_fields(
        value, {"candidate_sha256", "record"}, "acceptance declaration"
    )
    _validate_sha256(declaration["candidate_sha256"], "accepted candidate")
    expected_path = receipt_path(path)
    if declaration["record"] != str(expected_path):
        raise MigrationPreauthorizationError("acceptance path does not match policy")
    current, policy_identity = read_private_identity(path)
    if current != payload:
        raise MigrationPreauthorizationError("policy changed before acceptance check")
    recorded, identity = read_private_identity(expected_path)
    record = json.loads(recorded, object_pairs_hook=_object_without_duplicate_keys)
    expected = {
        "schema_version": POLICY_ACCEPTANCE_SCHEMA_VERSION,
        "kind": "accepted-migration-policy",
        "tool_version": __version__,
        "candidate_sha256": declaration["candidate_sha256"],
        "policy_path": str(path),
        "policy_sha256": hashlib.sha256(payload).hexdigest(),
        "policy_identity": list(policy_identity[:2]),
        "record_identity": list(identity[:2]),
    }
    if (
        not isinstance(record, dict)
        or type(record.get("schema_version")) is not int
        or canonical_bytes(record) != canonical_bytes(expected)
    ):
        raise MigrationPreauthorizationError(
            "policy acceptance evidence does not match"
        )
    return PolicyAcceptance(
        path, payload, policy_identity, expected_path, recorded, identity
    )
