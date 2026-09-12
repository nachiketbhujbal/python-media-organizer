"""Private typed outcomes exchanged between migration children and coordinator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from pymo.migration.roots import (
    DirectoryIdentityError,
    existing_directories_are_disjoint,
)

# This identifies private version-bound coordinator outcome records. Stable
# migration-report schema 1 selects aggregates from them; it does not expose
# this internal record contract.
MIGRATION_OUTCOME_SCHEMA_VERSION = 2

# This identifies the deterministic private mutation-decision digest contract.
MIGRATION_DECISION_DIGEST_ALGORITHM = "migration-decision-v1"

OutcomeCategory = Literal[
    "scan", "validation", "transformation", "duplicates", "verification"
]
ResultKind = Literal["observed", "simulated", "preview"]


class MigrationOutcomeError(RuntimeError):
    """A private child outcome cannot be created or trusted safely."""


def add_outcome_argument(parser: argparse.ArgumentParser) -> None:
    """Add the private coordinator result path without publishing a CLI contract."""

    parser.add_argument(
        "--migration-outcome",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--migration-decision-digest",
        help=argparse.SUPPRESS,
    )


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MigrationOutcomeError(f"migration outcome has invalid {field}")
    return value


def _require_optional_str(value: object, field: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value):
        raise MigrationOutcomeError(f"migration outcome has invalid {field}")
    return value


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise MigrationOutcomeError(f"migration outcome has invalid {field}")
    return value


def _require_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise MigrationOutcomeError(f"migration outcome has invalid {field}")
    return value


def _require_exact_fields(
    value: object, expected: set[str], field: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise MigrationOutcomeError(f"migration outcome has invalid {field}")
    return value


def _validate_findings(value: object) -> None:
    if not isinstance(value, list):
        raise MigrationOutcomeError("migration outcome has invalid findings")
    for item in value:
        finding = _require_exact_fields(item, {"severity", "code", "count"}, "finding")
        if finding["severity"] not in {"info", "warning", "error"}:
            raise MigrationOutcomeError(
                "migration outcome has invalid finding severity"
            )
        _require_str(finding["code"], "finding code")
        _require_int(finding["count"], "finding count")


def _validate_cache(value: object) -> None:
    cache = _require_exact_fields(
        value,
        {"enabled", "reused", "computed", "persisted", "issue"},
        "cache",
    )
    _require_bool(cache["enabled"], "cache enabled")
    _require_int(cache["reused"], "cache reused")
    _require_int(cache["computed"], "cache computed")
    _require_int(cache["persisted"], "cache persisted")
    _require_optional_str(cache["issue"], "cache issue")


def _validate_scan(data: dict[str, Any]) -> None:
    inventory = _require_exact_fields(
        data,
        {
            "files",
            "directories",
            "bytes",
            "pictures",
            "videos",
            "audio",
            "other",
            "unknown",
            "ignored",
            "symbolic_links",
            "unreadable",
            "changed",
        },
        "scan data",
    )
    for field, value in inventory.items():
        _require_int(value, f"scan {field}")
    classified = sum(
        inventory[field]
        for field in ("pictures", "videos", "audio", "other", "unknown")
    )
    if classified != inventory["files"]:
        raise MigrationOutcomeError("migration outcome has inconsistent scan counts")


def _validate_validation(data: dict[str, Any]) -> None:
    value = _require_exact_fields(
        data,
        {
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
            "cache",
        },
        "validation data",
    )
    for field in (
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
    ):
        _require_int(value[field], f"validation {field}")
    _validate_findings(value["findings"])
    _validate_cache(value["cache"])
    if value["pictures"] + value["videos"] != value["media_files"]:
        raise MigrationOutcomeError(
            "migration outcome has inconsistent validation inventory"
        )
    evaluated = (
        value["media_files"]
        + value["other_files"]
        + value["symbolic_links"]
        + value["unreadable"]
        + value["changed"]
    )
    if (
        value["healthy"] > value["media_files"]
        or value["warning_only"] > evaluated
        or value["errors"] > evaluated
    ):
        raise MigrationOutcomeError(
            "migration outcome has inconsistent validation health"
        )
    if any(item["count"] > evaluated for item in value["findings"]):
        raise MigrationOutcomeError(
            "migration outcome has inconsistent validation findings"
        )


def _validate_transformation(data: dict[str, Any]) -> None:
    value = _require_exact_fields(
        data,
        {
            "operation",
            "files",
            "directories_created",
            "directories_removed",
            "decision_digest",
        },
        "transformation data",
    )
    if value["operation"] not in {"extension-correction", "organization", "rename"}:
        raise MigrationOutcomeError("migration outcome has invalid operation")
    for field in ("files", "directories_created", "directories_removed"):
        _require_int(value[field], f"transformation {field}")
    _validate_decision_digest(value["decision_digest"])


def _validate_duplicates(data: dict[str, Any]) -> None:
    value = _require_exact_fields(
        data,
        {
            "media_kind",
            "scanned_files",
            "scanned_bytes",
            "groups",
            "extra_copies",
            "duplicate_bytes",
            "skipped",
            "cache",
            "decision_digest",
        },
        "duplicate data",
    )
    if value["media_kind"] not in {"image", "video"}:
        raise MigrationOutcomeError("migration outcome has invalid media kind")
    for field in (
        "scanned_files",
        "scanned_bytes",
        "groups",
        "extra_copies",
        "duplicate_bytes",
        "skipped",
    ):
        _require_int(value[field], f"duplicate {field}")
    _validate_cache(value["cache"])
    _validate_decision_digest(value["decision_digest"])
    if (
        value["groups"] > value["extra_copies"]
        or value["extra_copies"] > value["scanned_files"]
        or value["duplicate_bytes"] > value["scanned_bytes"]
    ):
        raise MigrationOutcomeError(
            "migration outcome has inconsistent duplicate accounting"
        )


def _validate_verification(data: dict[str, Any]) -> None:
    value = _require_exact_fields(
        data,
        {
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
        },
        "verification data",
    )
    for field in (
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
    ):
        _require_int(value[field], f"verification {field}")
    _require_str(value["verdict"], "verification verdict")
    _require_str(value["disposition"], "verification disposition")
    if not isinstance(value["reasons"], list) or any(
        not isinstance(reason, str) or not reason for reason in value["reasons"]
    ):
        raise MigrationOutcomeError(
            "migration outcome has invalid verification reasons"
        )
    if (
        value["accounted_unique_streams"] + value["unaccounted_unique_streams"]
        != value["source_unique_streams"]
        or value["accounted_source_files"] + value["unaccounted_source_files"]
        != value["source_files"]
        or value["unsupported_unique_streams"] > value["unaccounted_unique_streams"]
        or value["unsupported_source_files"] > value["unaccounted_source_files"]
    ):
        raise MigrationOutcomeError(
            "migration outcome has inconsistent preservation accounting"
        )


def validate_outcome(
    value: object,
    *,
    expected_command: str | None = None,
    expected_status: int | None = None,
    expected_result_kind: ResultKind | None = None,
) -> dict[str, Any]:
    outcome = _require_exact_fields(
        value,
        {"schema_version", "command", "category", "result_kind", "status", "data"},
        "record",
    )
    if (
        type(outcome["schema_version"]) is not int
        or outcome["schema_version"] != MIGRATION_OUTCOME_SCHEMA_VERSION
    ):
        raise MigrationOutcomeError("migration outcome schema is unsupported")
    command = _require_str(outcome["command"], "command")
    if expected_command is not None and command != expected_command:
        raise MigrationOutcomeError(
            "migration outcome command does not match its stage"
        )
    category = outcome["category"]
    command_categories = {
        "scan": "scan",
        "validate": "validation",
        "correct-extensions": "transformation",
        "organize": "transformation",
        "rename": "transformation",
        "find-image-duplicates": "duplicates",
        "find-video-duplicates": "duplicates",
        "verify-migration": "verification",
    }
    if command not in command_categories or category != command_categories[command]:
        raise MigrationOutcomeError("migration outcome has invalid category")
    result_kind = outcome["result_kind"]
    if result_kind not in {"observed", "simulated", "preview"}:
        raise MigrationOutcomeError("migration outcome has invalid result kind")
    if expected_result_kind is not None and result_kind != expected_result_kind:
        raise MigrationOutcomeError(
            "migration outcome result kind does not match its stage"
        )
    status = _require_int(outcome["status"], "status")
    if status > 255:
        raise MigrationOutcomeError("migration outcome has invalid status")
    if expected_status is not None and status != expected_status:
        raise MigrationOutcomeError("migration outcome status does not match its child")
    if not isinstance(outcome["data"], dict):
        raise MigrationOutcomeError("migration outcome has invalid data")
    data = outcome["data"]
    validators = {
        "scan": _validate_scan,
        "validation": _validate_validation,
        "transformation": _validate_transformation,
        "duplicates": _validate_duplicates,
        "verification": _validate_verification,
    }
    validators[category](data)
    if category == "transformation":
        operations = {
            "correct-extensions": "extension-correction",
            "organize": "organization",
            "rename": "rename",
        }
        if data["operation"] != operations[command]:
            raise MigrationOutcomeError(
                "migration outcome operation does not match its command"
            )
    if category == "duplicates":
        expected_kind = "image" if command == "find-image-duplicates" else "video"
        if data["media_kind"] != expected_kind:
            raise MigrationOutcomeError(
                "migration outcome media kind does not match its command"
            )
    if category == "validation" and status != int(
        data["errors"] > 0 or data["cache"]["issue"] is not None
    ):
        raise MigrationOutcomeError(
            "migration outcome validation status does not match its health"
        )
    if category == "verification":
        verdict = data["verdict"]
        if verdict not in {"complete", "incomplete", "unproven"}:
            raise MigrationOutcomeError("migration outcome has invalid verdict")
        allowed_reasons = {
            "filesystem-evidence-incomplete",
            "unsupported-source-media",
            "media-equivalence-evidence-incomplete",
            "source-content-unaccounted",
        }
        reasons = data["reasons"]
        if len(reasons) != len(set(reasons)) or any(
            reason not in allowed_reasons for reason in reasons
        ):
            raise MigrationOutcomeError(
                "migration outcome has invalid verification reasons"
            )
        expected_disposition = (
            "eligible-for-human-quarantine-review"
            if verdict == "complete" and result_kind == "simulated"
            else (
                "eligible-for-human-signoff"
                if verdict == "complete"
                else "retain-source-and-resolve-findings"
            )
        )
        if data["disposition"] != expected_disposition:
            raise MigrationOutcomeError(
                "migration outcome has inconsistent verification disposition"
            )
        if status != int(verdict != "complete"):
            raise MigrationOutcomeError(
                "migration outcome verification status does not match its verdict"
            )
        if verdict == "complete" and (
            reasons
            or data["unaccounted_unique_streams"]
            or data["unaccounted_source_files"]
            or data["unsupported_unique_streams"]
            or data["unsupported_source_files"]
        ):
            raise MigrationOutcomeError(
                "migration outcome has inconsistent complete verdict"
            )
        if verdict != "complete" and not reasons:
            raise MigrationOutcomeError(
                "migration outcome has unexplained incomplete verdict"
            )
    return outcome


def _validate_decision_digest(value: object) -> str:
    prefix = f"{MIGRATION_DECISION_DIGEST_ALGORITHM}:"
    if (
        not isinstance(value, str)
        or not value.startswith(prefix)
        or len(value) != len(prefix) + 64
    ):
        raise MigrationOutcomeError("migration outcome has invalid decision digest")
    digest = value[len(prefix) :]
    if any(character not in "0123456789abcdef" for character in digest):
        raise MigrationOutcomeError("migration outcome has invalid decision digest")
    return value


def decision_digest(operation: str, decisions: Sequence[Mapping[str, object]]) -> str:
    """Hash a deterministic private mutation plan without exposing its paths."""

    payload = json.dumps(
        {
            "algorithm": MIGRATION_DECISION_DIGEST_ALGORITHM,
            "operation": operation,
            "decisions": list(decisions),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return (
        f"{MIGRATION_DECISION_DIGEST_ALGORITHM}:{hashlib.sha256(payload).hexdigest()}"
    )


def decision_digest_matches(expected: str | None, observed: str) -> bool:
    """Return whether a coordinator-bound apply still matches its preview."""

    return expected is None or expected == observed


def outcome_record(
    command: str,
    category: OutcomeCategory,
    result_kind: ResultKind,
    status: int,
    data: dict[str, Any],
) -> dict[str, Any]:
    value = {
        "schema_version": MIGRATION_OUTCOME_SCHEMA_VERSION,
        "command": command,
        "category": category,
        "result_kind": result_kind,
        "status": status,
        "data": data,
    }
    return validate_outcome(value)


def scan_data(report: dict[str, Any]) -> dict[str, int]:
    inventory = report["inventory"]
    kinds = inventory["kinds"]
    return {
        "files": inventory["files"],
        "directories": inventory["directories"],
        "bytes": inventory["bytes"],
        "pictures": kinds["picture"]["files"],
        "videos": kinds["video"]["files"],
        "audio": kinds["audio"]["files"],
        "other": kinds["other"]["files"],
        "unknown": kinds["unknown"]["files"],
        "ignored": inventory["ignored_entry_points"],
        "symbolic_links": inventory["symbolic_links"],
        "unreadable": inventory["unreadable_entries"],
        "changed": inventory["changed_entries"],
    }


def validation_data(report: dict[str, Any]) -> dict[str, Any]:
    inventory = report["inventory"]
    health = report["health"]
    cache = report["cache"]
    return {
        "media_files": inventory["media_files"],
        "media_bytes": inventory["media_bytes"],
        "pictures": inventory["pictures"],
        "videos": inventory["videos"],
        "other_files": inventory["other_files"],
        "symbolic_links": inventory["symbolic_links_skipped"],
        "unreadable": inventory["unreadable_entries"],
        "changed": inventory["changed_during_discovery"],
        "healthy": health["healthy_files"],
        "warning_only": health["files_with_warnings"],
        "errors": health["files_with_errors"],
        "findings": [
            {
                "severity": finding["severity"],
                "code": finding["code"],
                "count": finding["count"],
            }
            for finding in report["findings"]
        ],
        "cache": {
            "enabled": cache["enabled"],
            "reused": cache["records_reused"],
            "computed": cache["fresh_validation_files"],
            "persisted": cache["records_written"],
            "issue": cache["issue"],
        },
    }


def verification_data(report: dict[str, Any]) -> dict[str, Any]:
    source = report["source"]
    destination = report["destination"]
    preservation = report["preservation"]
    review = report["simulation"]["destination_review_tree"]
    return {
        "source_files": source["hashed_files"],
        "source_bytes": source["hashed_bytes"],
        "source_unique_streams": preservation["source_unique_streams"],
        "accounted_unique_streams": preservation["accounted_unique_streams"],
        "accounted_source_files": preservation["accounted_source_files"],
        "unaccounted_unique_streams": preservation["unaccounted_unique_streams"],
        "unaccounted_source_files": preservation["unaccounted_source_files"],
        "unsupported_unique_streams": preservation["unsupported_unique_streams"],
        "unsupported_source_files": preservation["unsupported_source_files"],
        "destination_files": destination["hashed_files"],
        "destination_bytes": destination["hashed_bytes"],
        "review_files": 0 if review is None else review["hashed_files"],
        "review_bytes": 0 if review is None else review["hashed_bytes"],
        "verdict": preservation["verdict"],
        "disposition": preservation["disposition"],
        "reasons": list(preservation["reasons"]),
    }


def _require_external_private_parent(path: Path, roots: tuple[Path, ...]) -> Path:
    try:
        parent = path.expanduser().parent.resolve()
    except (OSError, RuntimeError) as error:
        raise MigrationOutcomeError(
            "migration outcome destination cannot be resolved safely"
        ) from error
    if not parent.is_dir() or parent.is_symlink():
        raise MigrationOutcomeError(
            "migration outcome destination parent is not a safe directory"
        )
    for root in roots:
        try:
            disjoint = existing_directories_are_disjoint(root, parent)
        except DirectoryIdentityError as error:
            raise MigrationOutcomeError(str(error)) from error
        if not disjoint:
            raise MigrationOutcomeError(
                "migration outcome destination must be outside every collection"
            )
    return parent / path.name


def _directory_identity_from_stat(value: os.stat_result) -> tuple[int, int]:
    return (value.st_dev, value.st_ino)


def _file_identity_from_stat(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _require_pinned_parent_current(
    parent: Path, descriptor: int, expected: tuple[int, int]
) -> None:
    try:
        opened = os.fstat(descriptor)
        current = os.stat(parent, follow_symlinks=False)
    except OSError as error:
        raise MigrationOutcomeError(
            "migration outcome parent changed during access"
        ) from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or _directory_identity_from_stat(opened) != expected
        or _directory_identity_from_stat(current) != expected
    ):
        raise MigrationOutcomeError("migration outcome parent changed during access")


@contextmanager
def _pinned_outcome_parent(path: Path) -> Iterator[tuple[int, str, Path]]:
    if path.name in {"", ".", ".."}:
        raise MigrationOutcomeError("migration outcome destination is unsafe")
    parent = path.parent
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(parent, flags)
    except OSError as error:
        raise MigrationOutcomeError(
            "migration outcome parent cannot be opened safely"
        ) from error
    try:
        try:
            metadata = os.fstat(descriptor)
        except OSError as error:
            raise MigrationOutcomeError(
                "migration outcome parent cannot be inspected safely"
            ) from error
        if not stat.S_ISDIR(metadata.st_mode):
            raise MigrationOutcomeError(
                "migration outcome parent is not a safe directory"
            )
        identity = _directory_identity_from_stat(metadata)
        _require_pinned_parent_current(parent, descriptor, identity)
        yield descriptor, path.name, parent
        _require_pinned_parent_current(parent, descriptor, identity)
    finally:
        os.close(descriptor)


def _require_parent_outside_roots(
    parent: Path, descriptor: int, roots: tuple[Path, ...]
) -> None:
    try:
        metadata = os.fstat(descriptor)
    except OSError as error:
        raise MigrationOutcomeError(
            "migration outcome parent cannot be inspected safely"
        ) from error
    expected = _directory_identity_from_stat(metadata)
    for root in roots:
        try:
            disjoint = existing_directories_are_disjoint(root, parent)
        except DirectoryIdentityError as error:
            raise MigrationOutcomeError(str(error)) from error
        if not disjoint:
            raise MigrationOutcomeError(
                "migration outcome destination must be outside every collection"
            )
    _require_pinned_parent_current(parent, descriptor, expected)


def write_outcome(path: Path | None, value: dict[str, Any], *roots: Path) -> None:
    if path is None:
        return
    validated = validate_outcome(value)
    destination = _require_external_private_parent(path, tuple(roots))
    payload = (
        json.dumps(validated, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    if len(payload) > 1024 * 1024:
        raise MigrationOutcomeError("migration outcome is too large")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with _pinned_outcome_parent(destination) as (
        parent_descriptor,
        name,
        parent,
    ):
        _require_parent_outside_roots(parent, parent_descriptor, tuple(roots))
        descriptor: int | None = None
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=parent_descriptor)
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written == 0:
                    raise OSError("short migration outcome write")
                view = view[written:]
            os.fsync(descriptor)
            metadata = os.fstat(descriptor)
            current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_mode & 0o077
                or _file_identity_from_stat(current)
                != _file_identity_from_stat(metadata)
            ):
                raise OSError("unsafe migration outcome destination")
            os.fsync(parent_descriptor)
            _require_parent_outside_roots(parent, parent_descriptor, tuple(roots))
        except OSError as error:
            raise MigrationOutcomeError(
                "migration outcome could not be saved safely"
            ) from error
        finally:
            if descriptor is not None:
                os.close(descriptor)


def read_outcome(
    path: Path,
    *,
    expected_command: str,
    expected_status: int,
    expected_result_kind: ResultKind | None = None,
) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with _pinned_outcome_parent(path) as (parent_descriptor, name, _):
        try:
            descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        except OSError as error:
            raise MigrationOutcomeError(
                "migration outcome cannot be read safely"
            ) from error
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_mode & 0o077
                or metadata.st_size > 1024 * 1024
            ):
                raise MigrationOutcomeError("migration outcome file is unsafe")
            initial = _file_identity_from_stat(metadata)
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, 65536):
                chunks.append(chunk)
            final = os.fstat(descriptor)
            current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            if (
                _file_identity_from_stat(final) != initial
                or _file_identity_from_stat(current) != initial
            ):
                raise MigrationOutcomeError("migration outcome changed during read")
        except OSError as error:
            raise MigrationOutcomeError(
                "migration outcome cannot be read safely"
            ) from error
        finally:
            os.close(descriptor)
    try:
        value = json.loads(b"".join(chunks))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MigrationOutcomeError("migration outcome is not valid JSON") from error
    return validate_outcome(
        value,
        expected_command=expected_command,
        expected_status=expected_status,
        expected_result_kind=expected_result_kind,
    )
