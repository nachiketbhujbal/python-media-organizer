"""Create-once private binding for one unattended migration policy."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pymo.migration.coordinator_state import (
    MigrationCoordinatorError,
    MigrationState,
    _options_from_json,
)
from pymo.migration.preauthorization import (
    MigrationPreauthorization,
    MigrationPreauthorizationError,
)

# This identifies the private create-once policy-binding compatibility contract.
UNATTENDED_POLICY_BINDING_SCHEMA_VERSION = 1
UNATTENDED_POLICY_BINDING_FILENAME = "pymo-unattended-policy-binding.json"
_MAX_BINDING_BYTES = 1024 * 1024


def unattended_policy_binding_path(log_dir: Path) -> Path:
    """Return the fixed create-once binding location for a migration run."""

    return log_dir / UNATTENDED_POLICY_BINDING_FILENAME


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MigrationPreauthorizationError(
                "unattended policy binding contains a duplicate JSON key"
            )
        result[key] = value
    return result


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _ancestor_is_safe(
    parent: os.stat_result, child: os.stat_result, effective_uid: int
) -> bool:
    trusted_owners = {0, effective_uid}
    if parent.st_uid not in trusted_owners or child.st_uid not in trusted_owners:
        return False
    if not parent.st_mode & 0o022:
        return True
    return bool(parent.st_mode & stat.S_ISVTX)


def _open_log_directory(log_dir: Path) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(log_dir, flags)
        opened = os.fstat(descriptor)
        current = os.stat(log_dir, follow_symlinks=False)
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise MigrationPreauthorizationError(
            "unattended policy binding directory cannot be opened safely"
        ) from error
    assert descriptor is not None
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
        or opened.st_uid != os.geteuid()
        or opened.st_mode & 0o077
    ):
        os.close(descriptor)
        raise MigrationPreauthorizationError(
            "unattended policy binding directory is unsafe or not private"
        )
    child = opened
    ancestor = log_dir
    while ancestor.parent != ancestor:
        ancestor = ancestor.parent
        try:
            parent = os.stat(ancestor, follow_symlinks=False)
        except OSError as error:
            os.close(descriptor)
            raise MigrationPreauthorizationError(
                "unattended policy binding ancestry cannot be inspected safely"
            ) from error
        if not stat.S_ISDIR(parent.st_mode):
            os.close(descriptor)
            raise MigrationPreauthorizationError(
                "unattended policy binding ancestry is unsafe"
            )
        if not _ancestor_is_safe(parent, child, os.geteuid()):
            os.close(descriptor)
            raise MigrationPreauthorizationError(
                "unattended policy binding ancestry is writable by another user"
            )
        child = parent
    return descriptor


def require_private_unattended_log_directory(log_dir: Path) -> None:
    """Require an owner-private directory with non-substitutable ancestry."""

    descriptor = _open_log_directory(log_dir)
    os.close(descriptor)


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written == 0:
            raise OSError("short unattended policy binding write")
        view = view[written:]


def _require_sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise MigrationPreauthorizationError(
            "unattended policy binding has an invalid policy digest"
        )
    return value


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise MigrationPreauthorizationError(
            f"unattended policy binding has an invalid {field}"
        )
    return value


def _require_timestamp(value: object) -> str:
    result = _require_string(value, "creation time")
    try:
        parsed = datetime.fromisoformat(result)
    except ValueError as error:
        raise MigrationPreauthorizationError(
            "unattended policy binding has an invalid creation time"
        ) from error
    if parsed.tzinfo is None:
        raise MigrationPreauthorizationError(
            "unattended policy binding has a timezone-free creation time"
        )
    return result


@dataclass(frozen=True)
class UnattendedPolicyBinding:
    """The independent create-once authority bound to one coordinator run."""

    tool_version: str
    baseline: Path
    working: Path
    options: dict[str, bool | int | str | None]
    created_at: str
    policy_sha256: str

    def as_json(self) -> dict[str, object]:
        return {
            "schema_version": UNATTENDED_POLICY_BINDING_SCHEMA_VERSION,
            "tool_version": self.tool_version,
            "baseline": str(self.baseline),
            "working": str(self.working),
            "options": self.options,
            "created_at": self.created_at,
            "policy_sha256": self.policy_sha256,
        }

    def require_run_binding(
        self, state: MigrationState, policy: MigrationPreauthorization
    ) -> None:
        if (
            self.tool_version != state.tool_version
            or self.baseline != state.baseline
            or self.working != state.working
            or self.options != state.options.as_json()
            or self.created_at != state.created_at
            or self.policy_sha256 != policy.payload_sha256
        ):
            raise MigrationPreauthorizationError(
                "unattended policy binding does not match the migration run"
            )

    def require(self, state: MigrationState, policy: MigrationPreauthorization) -> None:
        self.require_run_binding(state, policy)
        if self.policy_sha256 != state.unattended_policy_sha256:
            raise MigrationPreauthorizationError(
                "unattended policy binding does not match the migration run"
            )


def _binding_for(
    state: MigrationState, policy: MigrationPreauthorization
) -> UnattendedPolicyBinding:
    policy.require_run_binding(state)
    return UnattendedPolicyBinding(
        tool_version=state.tool_version,
        baseline=state.baseline,
        working=state.working,
        options=state.options.as_json(),
        created_at=state.created_at,
        policy_sha256=policy.payload_sha256,
    )


def create_unattended_policy_binding(
    log_dir: Path, state: MigrationState, policy: MigrationPreauthorization
) -> None:
    """Create and sync the run's policy binding without replacement."""

    binding = _binding_for(state, policy)
    payload = (
        json.dumps(binding.as_json(), sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
    )
    directory = _open_log_directory(log_dir)
    descriptor: int | None = None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(
            UNATTENDED_POLICY_BINDING_FILENAME,
            flags,
            0o600,
            dir_fd=directory,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_mode & 0o077
        ):
            raise OSError("unsafe unattended policy binding target")
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.fsync(directory)
    except OSError as error:
        raise MigrationPreauthorizationError(
            "unattended policy binding could not be created without replacement"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def _read_unattended_policy_binding(log_dir: Path) -> bytes:
    directory = _open_log_directory(log_dir)
    descriptor: int | None = None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(
            UNATTENDED_POLICY_BINDING_FILENAME, flags, dir_fd=directory
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_mode & 0o077
            or metadata.st_size > _MAX_BINDING_BYTES
        ):
            raise MigrationPreauthorizationError(
                "unattended policy binding is unsafe or not private"
            )
        initial = _identity(metadata)
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 65536):
            total += len(chunk)
            if total > _MAX_BINDING_BYTES:
                raise MigrationPreauthorizationError(
                    "unattended policy binding is too large"
                )
            chunks.append(chunk)
        final = os.fstat(descriptor)
        current = os.stat(
            UNATTENDED_POLICY_BINDING_FILENAME,
            dir_fd=directory,
            follow_symlinks=False,
        )
        if _identity(final) != initial or _identity(current) != initial:
            raise MigrationPreauthorizationError(
                "unattended policy binding changed during access"
            )
        payload = b"".join(chunks)
        if not payload:
            raise MigrationPreauthorizationError("unattended policy binding is empty")
        return payload
    except OSError as error:
        raise MigrationPreauthorizationError(
            "unattended policy binding cannot be read safely"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def load_unattended_policy_binding(log_dir: Path) -> UnattendedPolicyBinding:
    """Load one strict private create-once policy binding."""

    try:
        value = json.loads(
            _read_unattended_policy_binding(log_dir),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MigrationPreauthorizationError(
            "unattended policy binding is not valid JSON"
        ) from error
    expected = {
        "schema_version",
        "tool_version",
        "baseline",
        "working",
        "options",
        "created_at",
        "policy_sha256",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise MigrationPreauthorizationError(
            "unattended policy binding record is malformed"
        )
    if value["schema_version"] != UNATTENDED_POLICY_BINDING_SCHEMA_VERSION:
        raise MigrationPreauthorizationError(
            "unattended policy binding schema is unsupported"
        )
    tool_version = _require_string(value["tool_version"], "tool version")
    baseline = Path(_require_string(value["baseline"], "baseline"))
    working = Path(_require_string(value["working"], "working collection"))
    if not baseline.is_absolute() or not working.is_absolute():
        raise MigrationPreauthorizationError(
            "unattended policy binding collection roots must be absolute"
        )
    try:
        options = _options_from_json(value["options"]).as_json()
    except MigrationCoordinatorError as error:
        raise MigrationPreauthorizationError(
            "unattended policy binding options are malformed"
        ) from error
    return UnattendedPolicyBinding(
        tool_version=tool_version,
        baseline=baseline,
        working=working,
        options=options,
        created_at=_require_timestamp(value["created_at"]),
        policy_sha256=_require_sha256(value["policy_sha256"]),
    )


def require_unattended_policy_binding(
    log_dir: Path, state: MigrationState, policy: MigrationPreauthorization
) -> UnattendedPolicyBinding:
    """Require the independent record, restart state, and policy to agree."""

    binding = load_unattended_policy_binding(log_dir)
    binding.require(state, policy)
    return binding
