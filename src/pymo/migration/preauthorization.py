"""Strict private policy for deliberately unattended migration checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pymo.migration.coordinator_state import (
    MigrationCoordinatorError,
    MigrationState,
    _options_from_json,
)

# This identifies the public pre-authorization policy compatibility contract.
MIGRATION_PREAUTHORIZATION_SCHEMA_VERSION = 1


class MigrationPreauthorizationError(RuntimeError):
    """A pre-authorization policy cannot be trusted or interpreted safely."""


class MigrationPreauthorizationMismatch(RuntimeError):
    """A valid policy does not authorize the observed checkpoint."""


_VALIDATION_CHECKPOINTS = {
    "baseline-validation",
    "working-validation",
    "final-working-validation",
}
_APPLY_PREVIEWS = {
    "extension-apply": "extension-preview",
    "organize-apply": "organize-preview",
    "rename-apply": "rename-preview",
    "image-duplicates-apply": "image-duplicates-preview",
    "video-duplicates-apply": "video-duplicates-preview",
}
_CHECKPOINT_ORDER = {
    "baseline-validation": 2,
    "working-validation": 3,
    "extension-apply": 6,
    "organize-apply": 9,
    "rename-apply": 12,
    "image-duplicates-apply": 15,
    "video-duplicates-apply": 18,
    "external-quarantine": 21,
    "final-working-validation": 22,
    "final-signoff": 24,
}


def _require_exact_fields(
    value: object, expected: set[str], field: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise MigrationPreauthorizationError(
            f"pre-authorization policy has invalid {field}"
        )
    return value


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise MigrationPreauthorizationError(
            f"pre-authorization policy has invalid {field}"
        )
    return value


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MigrationPreauthorizationError(
            f"pre-authorization policy has invalid {field}"
        )
    return value


def _require_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise MigrationPreauthorizationError(
            f"pre-authorization policy has invalid {field}"
        )
    return value


def _validate_findings(value: object) -> None:
    if not isinstance(value, list):
        raise MigrationPreauthorizationError(
            "pre-authorization policy has invalid expected findings"
        )
    keys: list[tuple[str, str]] = []
    for item in value:
        finding = _require_exact_fields(
            item, {"severity", "code", "count"}, "expected finding"
        )
        severity = _require_string(finding["severity"], "finding severity")
        if severity not in {"info", "warning", "error"}:
            raise MigrationPreauthorizationError(
                "pre-authorization policy has invalid finding severity"
            )
        code = _require_string(finding["code"], "finding code")
        if not code.replace("_", "").replace("-", "").isalnum():
            raise MigrationPreauthorizationError(
                "pre-authorization policy has unsafe finding code"
            )
        if _require_int(finding["count"], "finding count") == 0:
            raise MigrationPreauthorizationError(
                "pre-authorization policy has zero-count finding"
            )
        keys.append((severity, code))
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise MigrationPreauthorizationError(
            "pre-authorization policy findings must be unique and sorted"
        )


def _validate_validation_expected(value: object) -> dict[str, Any]:
    expected = _require_exact_fields(
        value,
        {
            "status",
            "media_files",
            "media_bytes",
            "pictures",
            "videos",
            "other_files",
            "symbolic_links",
            "unreadable",
            "changed",
            "healthy",
            "warning_only",
            "errors",
            "findings",
            "cache_issue",
        },
        "validation expectation",
    )
    for field in expected.keys() - {"findings", "cache_issue"}:
        _require_int(expected[field], f"validation {field}")
    if expected["status"] not in {0, 1}:
        raise MigrationPreauthorizationError(
            "pre-authorization policy has invalid validation status"
        )
    _validate_findings(expected["findings"])
    if _require_bool(expected["cache_issue"], "validation cache issue"):
        raise MigrationPreauthorizationError(
            "pre-authorization policy cannot accept a validation cache issue"
        )
    if expected["unreadable"] or expected["changed"]:
        raise MigrationPreauthorizationError(
            "pre-authorization policy cannot accept incomplete validation discovery"
        )
    if expected["pictures"] + expected["videos"] != expected["media_files"]:
        raise MigrationPreauthorizationError(
            "pre-authorization policy has inconsistent validation inventory"
        )
    if expected["status"] != int(expected["errors"] > 0):
        raise MigrationPreauthorizationError(
            "pre-authorization policy has inconsistent validation status"
        )
    return expected


def _validate_transformation_expected(value: object) -> dict[str, Any]:
    expected = _require_exact_fields(
        value,
        {
            "status",
            "operation",
            "files",
            "directories_created",
            "directories_removed",
            "decision_digest",
        },
        "transformation expectation",
    )
    if expected["status"] != 0:
        raise MigrationPreauthorizationError(
            "pre-authorization policy can apply only a successful preview"
        )
    if expected["operation"] not in {
        "extension-correction",
        "organization",
        "rename",
    }:
        raise MigrationPreauthorizationError(
            "pre-authorization policy has invalid transformation operation"
        )
    for field in ("files", "directories_created", "directories_removed"):
        _require_int(expected[field], f"transformation {field}")
    _validate_decision_digest(expected["decision_digest"])
    return expected


def _validate_duplicate_expected(value: object) -> dict[str, Any]:
    expected = _require_exact_fields(
        value,
        {
            "status",
            "media_kind",
            "scanned_files",
            "scanned_bytes",
            "groups",
            "extra_copies",
            "duplicate_bytes",
            "skipped",
            "cache_issue",
            "decision_digest",
        },
        "duplicate expectation",
    )
    if expected["status"] != 0:
        raise MigrationPreauthorizationError(
            "pre-authorization policy can apply only a successful duplicate preview"
        )
    if expected["media_kind"] not in {"image", "video"}:
        raise MigrationPreauthorizationError(
            "pre-authorization policy has invalid duplicate media kind"
        )
    for field in (
        "scanned_files",
        "scanned_bytes",
        "groups",
        "extra_copies",
        "duplicate_bytes",
        "skipped",
    ):
        _require_int(expected[field], f"duplicate {field}")
    if _require_bool(expected["cache_issue"], "duplicate cache issue"):
        raise MigrationPreauthorizationError(
            "pre-authorization policy cannot accept a duplicate cache issue"
        )
    _validate_decision_digest(expected["decision_digest"])
    return expected


def _validate_decision_digest(value: object) -> str:
    prefix = "migration-decision-v1:"
    if (
        not isinstance(value, str)
        or not value.startswith(prefix)
        or len(value) != len(prefix) + 64
        or any(
            character not in "0123456789abcdef" for character in value[len(prefix) :]
        )
    ):
        raise MigrationPreauthorizationError(
            "pre-authorization policy has invalid decision digest"
        )
    return value


def _validate_quarantine_expected(value: object) -> dict[str, Any]:
    expected = _require_exact_fields(
        value,
        {"status", "review_files", "review_bytes", "verdict", "disposition"},
        "quarantine expectation",
    )
    if expected["status"] != 0:
        raise MigrationPreauthorizationError(
            "pre-authorization policy requires a successful quarantine simulation"
        )
    _require_int(expected["review_files"], "quarantine review files")
    _require_int(expected["review_bytes"], "quarantine review bytes")
    if (
        expected["verdict"] != "complete"
        or expected["disposition"] != "eligible-for-human-quarantine-review"
    ):
        raise MigrationPreauthorizationError(
            "pre-authorization policy requires complete simulated preservation"
        )
    return expected


def _validate_signoff_expected(value: object) -> dict[str, Any]:
    fields = {
        "status",
        "source_files",
        "source_bytes",
        "source_unique_streams",
        "accounted_unique_streams",
        "accounted_source_files",
        "unaccounted_unique_streams",
        "unaccounted_source_files",
        "unsupported_unique_streams",
        "unsupported_source_files",
        "destination_files",
        "destination_bytes",
        "review_files",
        "review_bytes",
        "verdict",
        "disposition",
        "reasons",
    }
    expected = _require_exact_fields(value, fields, "final sign-off expectation")
    for field in fields - {"verdict", "disposition", "reasons"}:
        _require_int(expected[field], f"final verification {field}")
    if not isinstance(expected["reasons"], list) or expected["reasons"]:
        raise MigrationPreauthorizationError(
            "pre-authorization policy requires final verification without reasons"
        )
    if (
        expected["status"] != 0
        or expected["verdict"] != "complete"
        or expected["disposition"] != "eligible-for-human-signoff"
        or expected["unaccounted_unique_streams"]
        or expected["unaccounted_source_files"]
        or expected["unsupported_unique_streams"]
        or expected["unsupported_source_files"]
    ):
        raise MigrationPreauthorizationError(
            "pre-authorization policy requires complete final preservation"
        )
    return expected


def _validate_authorization(value: object) -> tuple[str, dict[str, Any]]:
    item = _require_exact_fields(
        value, {"checkpoint", "decision", "expected"}, "authorization"
    )
    checkpoint = _require_string(item["checkpoint"], "checkpoint")
    decision = _require_string(item["decision"], "decision")
    if checkpoint in _VALIDATION_CHECKPOINTS:
        if decision != "accept-validation":
            raise MigrationPreauthorizationError(
                "pre-authorization policy has an unrecognized validation decision"
            )
        expected = _validate_validation_expected(item["expected"])
    elif checkpoint in _APPLY_PREVIEWS:
        if decision != "apply":
            raise MigrationPreauthorizationError(
                "pre-authorization policy has an unrecognized apply decision"
            )
        if checkpoint.startswith(("image-duplicates", "video-duplicates")):
            expected = _validate_duplicate_expected(item["expected"])
            expected_kind = "image" if checkpoint.startswith("image-") else "video"
            if expected["media_kind"] != expected_kind:
                raise MigrationPreauthorizationError(
                    "pre-authorization policy duplicate kind does not match its checkpoint"
                )
        else:
            expected = _validate_transformation_expected(item["expected"])
            operations = {
                "extension-apply": "extension-correction",
                "organize-apply": "organization",
                "rename-apply": "rename",
            }
            if expected["operation"] != operations[checkpoint]:
                raise MigrationPreauthorizationError(
                    "pre-authorization policy operation does not match its checkpoint"
                )
    elif checkpoint == "external-quarantine":
        if decision != "confirm-quarantine":
            raise MigrationPreauthorizationError(
                "pre-authorization policy has an unrecognized quarantine decision"
            )
        expected = _validate_quarantine_expected(item["expected"])
    elif checkpoint == "final-signoff":
        if decision != "signoff":
            raise MigrationPreauthorizationError(
                "pre-authorization policy has an unrecognized sign-off decision"
            )
        expected = _validate_signoff_expected(item["expected"])
    else:
        raise MigrationPreauthorizationError(
            "pre-authorization policy has an unknown checkpoint"
        )
    return checkpoint, expected


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MigrationPreauthorizationError(
                "pre-authorization policy contains a duplicate JSON key"
            )
        result[key] = value
    return result


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_private_policy(path: Path) -> tuple[bytes, tuple[int, ...]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise MigrationPreauthorizationError(
            "pre-authorization policy cannot be read safely"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_mode & 0o077
            or metadata.st_size > 1024 * 1024
        ):
            raise MigrationPreauthorizationError(
                "pre-authorization policy file is unsafe or not private"
            )
        initial = _file_identity(metadata)
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 65536):
            total += len(chunk)
            if total > 1024 * 1024:
                raise MigrationPreauthorizationError(
                    "pre-authorization policy file is too large"
                )
            chunks.append(chunk)
        final = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if _file_identity(final) != initial or _file_identity(current) != initial:
            raise MigrationPreauthorizationError(
                "pre-authorization policy changed during access"
            )
        payload = b"".join(chunks)
        if not payload:
            raise MigrationPreauthorizationError("pre-authorization policy is empty")
        return payload, initial
    except OSError as error:
        raise MigrationPreauthorizationError(
            "pre-authorization policy cannot be inspected safely"
        ) from error
    finally:
        os.close(descriptor)


def _validation_projection(outcome: dict[str, Any]) -> dict[str, Any]:
    data = outcome["data"]
    return {
        "status": outcome["status"],
        "media_files": data["media_files"],
        "media_bytes": data["media_bytes"],
        "pictures": data["pictures"],
        "videos": data["videos"],
        "other_files": data["other_files"],
        "symbolic_links": data["symbolic_links"],
        "unreadable": data["unreadable"],
        "changed": data["changed"],
        "healthy": data["healthy"],
        "warning_only": data["warning_only"],
        "errors": data["errors"],
        "findings": sorted(
            data["findings"], key=lambda item: (item["severity"], item["code"])
        ),
        "cache_issue": data["cache"]["issue"] is not None,
    }


def _apply_projection(outcome: dict[str, Any]) -> dict[str, Any]:
    data = outcome["data"]
    if outcome["category"] == "transformation":
        return {"status": outcome["status"], **data}
    return {
        "status": outcome["status"],
        "media_kind": data["media_kind"],
        "scanned_files": data["scanned_files"],
        "scanned_bytes": data["scanned_bytes"],
        "groups": data["groups"],
        "extra_copies": data["extra_copies"],
        "duplicate_bytes": data["duplicate_bytes"],
        "skipped": data["skipped"],
        "cache_issue": data["cache"]["issue"] is not None,
        "decision_digest": data["decision_digest"],
    }


def _quarantine_projection(outcome: dict[str, Any]) -> dict[str, Any]:
    data = outcome["data"]
    return {
        "status": outcome["status"],
        "review_files": data["review_files"],
        "review_bytes": data["review_bytes"],
        "verdict": data["verdict"],
        "disposition": data["disposition"],
    }


def _signoff_projection(outcome: dict[str, Any]) -> dict[str, Any]:
    return {"status": outcome["status"], **outcome["data"]}


@dataclass(frozen=True)
class MigrationPreauthorization:
    path: Path
    payload_sha256: str
    file_identity: tuple[int, ...]
    tool_version: str
    baseline: Path
    working: Path
    options: dict[str, bool | int | str | None]
    authorizations: dict[str, dict[str, Any]]

    def require_current(self) -> None:
        payload, identity = _read_private_policy(self.path)
        if (
            identity != self.file_identity
            or hashlib.sha256(payload).hexdigest() != self.payload_sha256
        ):
            raise MigrationPreauthorizationError(
                "pre-authorization policy changed during unattended execution"
            )

    def require_run_binding(self, state: MigrationState) -> None:
        if (
            self.tool_version != state.tool_version
            or self.baseline != state.baseline
            or self.working != state.working
            or self.options != state.options.as_json()
        ):
            raise MigrationPreauthorizationError(
                "pre-authorization policy does not match the migration binding"
            )

    def require_binding(self, state: MigrationState) -> None:
        self.require_run_binding(state)
        if self.payload_sha256 != state.unattended_policy_sha256:
            raise MigrationPreauthorizationError(
                "pre-authorization policy does not match the migration binding"
            )

    def require_checkpoint(self, checkpoint: str, outcome: dict[str, Any]) -> None:
        expected = self.authorizations.get(checkpoint)
        if expected is None:
            raise MigrationPreauthorizationMismatch(
                f"checkpoint {checkpoint} is not pre-authorized"
            )
        if checkpoint in _VALIDATION_CHECKPOINTS:
            observed = _validation_projection(outcome)
        elif checkpoint in _APPLY_PREVIEWS:
            observed = _apply_projection(outcome)
        elif checkpoint == "external-quarantine":
            observed = _quarantine_projection(outcome)
        elif checkpoint == "final-signoff":
            observed = _signoff_projection(outcome)
        else:  # pragma: no cover - parsed policies cannot reach this branch.
            raise MigrationPreauthorizationError(
                "pre-authorization policy reached an unknown checkpoint"
            )
        if observed != expected:
            raise MigrationPreauthorizationMismatch(
                f"observed result for {checkpoint} differs from its pre-authorization"
            )


def load_preauthorization(
    requested: Path, *, roots: tuple[Path, Path]
) -> MigrationPreauthorization:
    try:
        expanded = requested.expanduser()
        if expanded.is_symlink():
            raise MigrationPreauthorizationError(
                "pre-authorization policy must not be a symbolic link"
            )
        path = expanded.resolve()
    except (OSError, RuntimeError) as error:
        raise MigrationPreauthorizationError(
            "pre-authorization policy path cannot be resolved safely"
        ) from error
    if path.name in {"", ".", ".."}:
        raise MigrationPreauthorizationError("pre-authorization policy path is unsafe")
    for root in roots:
        try:
            canonical_root = root.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise MigrationPreauthorizationError(
                "pre-authorization collection root cannot be resolved safely"
            ) from error
        if path.is_relative_to(canonical_root):
            raise MigrationPreauthorizationError(
                "pre-authorization policy must be outside both collections"
            )

    payload, identity = _read_private_policy(path)
    try:
        value = json.loads(payload, object_pairs_hook=_object_without_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MigrationPreauthorizationError(
            "pre-authorization policy is not valid JSON"
        ) from error
    policy = _require_exact_fields(
        value,
        {
            "schema_version",
            "tool_version",
            "baseline",
            "working",
            "options",
            "authorizations",
        },
        "record",
    )
    if policy["schema_version"] != MIGRATION_PREAUTHORIZATION_SCHEMA_VERSION:
        raise MigrationPreauthorizationError(
            "pre-authorization policy schema is unsupported"
        )
    tool_version = _require_string(policy["tool_version"], "tool version")
    baseline_value = _require_string(policy["baseline"], "baseline")
    working_value = _require_string(policy["working"], "working collection")
    baseline = Path(baseline_value)
    working = Path(working_value)
    if not baseline.is_absolute() or not working.is_absolute():
        raise MigrationPreauthorizationError(
            "pre-authorization policy collection roots must be absolute"
        )
    try:
        options = _options_from_json(policy["options"]).as_json()
    except MigrationCoordinatorError as error:
        raise MigrationPreauthorizationError(
            "pre-authorization policy options are malformed"
        ) from error
    values = policy["authorizations"]
    if not isinstance(values, list):
        raise MigrationPreauthorizationError(
            "pre-authorization policy authorizations are malformed"
        )
    parsed = [_validate_authorization(item) for item in values]
    checkpoints = [checkpoint for checkpoint, _ in parsed]
    if len(checkpoints) != len(set(checkpoints)):
        raise MigrationPreauthorizationError(
            "pre-authorization policy contains duplicate checkpoints"
        )
    if checkpoints != sorted(checkpoints, key=_CHECKPOINT_ORDER.__getitem__):
        raise MigrationPreauthorizationError(
            "pre-authorization policy checkpoints are out of workflow order"
        )
    return MigrationPreauthorization(
        path=path,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        file_identity=identity,
        tool_version=tool_version,
        baseline=baseline,
        working=working,
        options=options,
        authorizations=dict(parsed),
    )


def apply_preview_stage(checkpoint: str) -> str:
    """Return the preview stage that an apply checkpoint must match."""

    try:
        return _APPLY_PREVIEWS[checkpoint]
    except KeyError as error:
        raise MigrationPreauthorizationError(
            "pre-authorization policy reached an unknown apply checkpoint"
        ) from error
