"""Versioned media-validation evidence in the shared derived cache."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pymo.cache import service as cache_service
from pymo.cache.hashes import build_hash_observations
from pymo.file_safety import FileState

VALIDATION_EVIDENCE_TYPE = "media-validation"
VALIDATION_STANDARD_ALGORITHM = "media-validation-standard-v1"
VALIDATION_FULL_ALGORITHM = "media-validation-full-v1"

ValidationProfile = Literal["standard", "full"]
ValidationKind = Literal["picture", "video"]
ValidationSeverity = Literal["error", "warning", "info"]


class ValidationCacheError(RuntimeError):
    """Cached validation evidence cannot be used or published safely."""


@dataclass(frozen=True)
class ValidationFindingValue:
    severity: ValidationSeverity
    code: str
    description: str


@dataclass(frozen=True)
class ValidationEvidenceValue:
    path: Path
    state: FileState
    byte_sha256: str
    kind: ValidationKind
    profile: ValidationProfile
    runtime: str
    completed_at: str
    findings: tuple[ValidationFindingValue, ...]
    animated_or_multipage: bool


def validation_algorithm(profile: ValidationProfile) -> str:
    return (
        VALIDATION_FULL_ALGORITHM
        if profile == "full"
        else VALIDATION_STANDARD_ALGORITHM
    )


def validation_runtime(
    *,
    kind: ValidationKind,
    extension: str,
    extension_kind: ValidationKind | None,
    detected_kind: str,
    pillow: str | None,
    ffprobe: str | None,
    ffmpeg: str | None,
) -> str:
    """Build the canonical runtime and classification-context namespace."""

    return json.dumps(
        {
            "detected_kind": detected_kind,
            "extension": extension,
            "extension_kind": extension_kind,
            "ffmpeg": ffmpeg,
            "ffprobe": ffprobe,
            "kind": kind,
            "pillow": pillow,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def decode_validation_runtime(runtime: str) -> dict[str, object]:
    """Strictly validate one runtime and classification-context namespace."""

    try:
        payload = json.loads(runtime)
    except json.JSONDecodeError as error:
        raise ValidationCacheError(
            "cached media validation contains an invalid runtime"
        ) from error
    expected_keys = {
        "detected_kind",
        "extension",
        "extension_kind",
        "ffmpeg",
        "ffprobe",
        "kind",
        "pillow",
    }
    strings_or_none = (
        (payload.get("ffmpeg"), payload.get("ffprobe"), payload.get("pillow"))
        if isinstance(payload, dict)
        else ()
    )
    if (
        not isinstance(payload, dict)
        or set(payload) != expected_keys
        or payload["kind"] not in {"picture", "video"}
        or payload["extension_kind"] not in {None, "picture", "video"}
        or not isinstance(payload["detected_kind"], str)
        or not payload["detected_kind"]
        or not isinstance(payload["extension"], str)
        or any(
            value is not None and (not isinstance(value, str) or not value)
            for value in strings_or_none
        )
        or any(
            "\0" in value
            for value in (
                payload["detected_kind"],
                payload["extension"],
                *(value for value in strings_or_none if isinstance(value, str)),
            )
        )
        or (payload["kind"] == "picture" and payload["pillow"] is None)
        or (
            payload["kind"] == "picture"
            and (payload["ffprobe"] is not None or payload["ffmpeg"] is not None)
        )
        or (payload["kind"] == "video" and payload["pillow"] is not None)
        or (payload["ffmpeg"] is not None and payload["ffprobe"] is None)
        or json.dumps(payload, sort_keys=True, separators=(",", ":")) != runtime
    ):
        raise ValidationCacheError(
            "cached media validation contains an invalid runtime"
        )
    return payload


def completed_timestamp() -> str:
    """Return a canonical UTC completion timestamp."""

    return datetime.now(UTC).isoformat(timespec="microseconds")


def _outcome(findings: Sequence[ValidationFindingValue]) -> str:
    severities = {finding.severity for finding in findings}
    if "error" in severities:
        return "error"
    if "warning" in severities:
        return "warning"
    return "healthy"


def encode_validation_payload(value: ValidationEvidenceValue) -> str:
    """Return one canonical, path-private persisted validation result."""

    return json.dumps(
        {
            "animated_or_multipage": value.animated_or_multipage,
            "completed_at": value.completed_at,
            "findings": [
                {
                    "code": finding.code,
                    "description": finding.description,
                    "severity": finding.severity,
                }
                for finding in value.findings
            ],
            "kind": value.kind,
            "outcome": _outcome(value.findings),
            "profile": value.profile,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def decode_validation_payload(payload_json: str, algorithm: str) -> dict[str, object]:
    """Strictly validate one persisted validation result."""

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise ValidationCacheError(
            "cached media validation contains invalid evidence"
        ) from error
    expected_keys = {
        "animated_or_multipage",
        "completed_at",
        "findings",
        "kind",
        "outcome",
        "profile",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValidationCacheError("cached media validation contains invalid evidence")
    profile = payload["profile"]
    expected_profile = "full" if algorithm == VALIDATION_FULL_ALGORITHM else "standard"
    if (
        algorithm
        not in {
            VALIDATION_STANDARD_ALGORITHM,
            VALIDATION_FULL_ALGORITHM,
        }
        or profile != expected_profile
    ):
        raise ValidationCacheError("cached media validation contains invalid evidence")
    if payload["kind"] not in {"picture", "video"} or not isinstance(
        payload["animated_or_multipage"], bool
    ):
        raise ValidationCacheError("cached media validation contains invalid evidence")
    completed_at = payload["completed_at"]
    try:
        parsed = datetime.fromisoformat(completed_at)
    except (TypeError, ValueError) as error:
        raise ValidationCacheError(
            "cached media validation contains invalid evidence"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValidationCacheError("cached media validation contains invalid evidence")
    findings = payload["findings"]
    if not isinstance(findings, list):
        raise ValidationCacheError("cached media validation contains invalid evidence")
    decoded_findings: list[ValidationFindingValue] = []
    for finding in findings:
        if (
            not isinstance(finding, dict)
            or set(finding) != {"code", "description", "severity"}
            or finding["severity"] not in {"error", "warning", "info"}
            or not isinstance(finding["code"], str)
            or not finding["code"]
            or not isinstance(finding["description"], str)
            or not finding["description"]
            or "\0" in finding["code"]
            or "\0" in finding["description"]
        ):
            raise ValidationCacheError(
                "cached media validation contains invalid evidence"
            )
        decoded_findings.append(
            ValidationFindingValue(
                finding["severity"], finding["code"], finding["description"]
            )
        )
    if payload["outcome"] != _outcome(decoded_findings):
        raise ValidationCacheError("cached media validation contains invalid evidence")
    return payload


def validate_evidence_records(
    records: Iterable[cache_service.DerivedEvidence],
) -> None:
    """Validate every known media-validation record in cache contents."""

    for record in records:
        if record.evidence_type == VALIDATION_EVIDENCE_TYPE:
            payload = decode_validation_payload(record.payload_json, record.algorithm)
            runtime = decode_validation_runtime(record.runtime)
            if payload["kind"] != runtime["kind"]:
                raise ValidationCacheError(
                    "cached media validation contains invalid evidence"
                )


def build_validation_evidence(
    values: Iterable[ValidationEvidenceValue],
) -> tuple[cache_service.DerivedEvidence, ...]:
    """Build normalized derived evidence from completed validations."""

    records = tuple(
        cache_service.DerivedEvidence(
            file_sha256=value.byte_sha256,
            evidence_type=VALIDATION_EVIDENCE_TYPE,
            algorithm=validation_algorithm(value.profile),
            runtime=value.runtime,
            payload_json=encode_validation_payload(value),
        )
        for value in values
    )
    validate_evidence_records(records)
    return records


def preflight_validation_cache(database: Path) -> None:
    """Validate existing validation evidence without creating cache state."""

    try:
        with cache_service.read_cache_snapshot(database) as snapshot:
            if snapshot is None:
                return
            contents = cache_service.read_cache_contents(snapshot.connection)
            validate_evidence_records(contents.evidence)
    except (cache_service.CacheError, sqlite3.Error, OSError) as error:
        raise ValidationCacheError(
            "media-validation cache cannot be read safely"
        ) from error


def publish_validation_batch(
    root: Path,
    database: Path,
    values: Iterable[ValidationEvidenceValue],
) -> None:
    """Publish validation observations and results in one atomic update."""

    materialized = tuple(values)
    if not materialized:
        return
    observations = build_hash_observations(
        root,
        ((value.path, value.state, value.byte_sha256) for value in materialized),
    )
    evidence = build_validation_evidence(materialized)

    def update(connection: sqlite3.Connection) -> None:
        cache_service.upsert_file_observations(connection, observations)
        cache_service.upsert_derived_evidence(connection, evidence)

    try:
        cache_service.publish_cache_update(database, update)
    except cache_service.CacheError as error:
        raise ValidationCacheError(
            "media-validation cache cannot be updated safely"
        ) from error
