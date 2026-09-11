from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pymo.migration.outcome import (
    MigrationOutcomeError,
    outcome_record,
    read_outcome,
    validate_outcome,
    write_outcome,
)


def scan_outcome() -> dict[str, object]:
    return outcome_record(
        "scan",
        "scan",
        "observed",
        0,
        {
            "files": 3,
            "directories": 1,
            "bytes": 12,
            "pictures": 2,
            "videos": 1,
            "audio": 0,
            "other": 0,
            "unknown": 0,
            "ignored": 1,
            "symbolic_links": 0,
            "unreadable": 0,
            "changed": 0,
        },
    )


def verification_outcome() -> dict[str, object]:
    return outcome_record(
        "verify-migration",
        "verification",
        "observed",
        0,
        {
            "source_files": 3,
            "source_bytes": 12,
            "source_unique_streams": 2,
            "accounted_unique_streams": 2,
            "accounted_source_files": 3,
            "unaccounted_unique_streams": 0,
            "unaccounted_source_files": 0,
            "unsupported_unique_streams": 0,
            "unsupported_source_files": 0,
            "destination_files": 2,
            "destination_bytes": 8,
            "review_files": 0,
            "review_bytes": 0,
            "verdict": "complete",
            "disposition": "eligible-for-human-signoff",
            "reasons": [],
        },
    )


def test_private_outcome_round_trip_is_path_private_and_no_replace(
    tmp_path: Path,
) -> None:
    collection = tmp_path / "collection"
    private = tmp_path / "private"
    collection.mkdir()
    private.mkdir()
    destination = private / "stage.outcome.json"

    write_outcome(destination, scan_outcome(), collection)

    assert destination.stat().st_mode & 0o777 == 0o600
    assert str(collection) not in destination.read_text(encoding="utf-8")
    assert (
        read_outcome(
            destination,
            expected_command="scan",
            expected_status=0,
            expected_result_kind="observed",
        )["data"]["files"]
        == 3
    )
    before = destination.read_bytes()
    with pytest.raises(MigrationOutcomeError, match="could not be saved safely"):
        write_outcome(destination, scan_outcome(), collection)
    assert destination.read_bytes() == before


def test_outcome_destination_cannot_be_inside_collection(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    collection.mkdir()
    destination = collection / "stage.outcome.json"

    with pytest.raises(MigrationOutcomeError, match="outside every collection"):
        write_outcome(destination, scan_outcome(), collection)

    assert not destination.exists()


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.update(schema_version=True),
        lambda value: value.update(category="verification"),
        lambda value: value.update(result_kind="preview"),
        lambda value: value.update(status=256),
        lambda value: value["data"].update(files=-1),
        lambda value: value["data"].update(pictures=3),
        lambda value: value["data"].update(secret_path="private"),
    ),
)
def test_outcome_reader_rejects_malformed_or_mismatched_records(
    tmp_path: Path, mutation: Callable[[dict[str, Any]], None]
) -> None:
    path = tmp_path / "stage.outcome.json"
    value = scan_outcome()
    mutation(value)
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(MigrationOutcomeError):
        read_outcome(
            path,
            expected_command="scan",
            expected_status=0,
            expected_result_kind="observed",
        )


def test_outcome_reader_rejects_symbolic_link(tmp_path: Path) -> None:
    target = tmp_path / "target.outcome.json"
    target.write_text(json.dumps(scan_outcome()), encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "link.outcome.json"
    link.symlink_to(target)

    with pytest.raises(MigrationOutcomeError, match="cannot be read safely"):
        read_outcome(link, expected_command="scan", expected_status=0)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value["data"].update(unaccounted_unique_streams=1),
        lambda value: value["data"].update(
            disposition="eligible-for-human-quarantine-review"
        ),
        lambda value: value.update(status=1),
        lambda value: value["data"].update(verdict="unproven"),
        lambda value: value["data"].update(reasons=["unknown-reason"]),
    ),
)
def test_outcome_rejects_inconsistent_preservation_claims(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    value = verification_outcome()
    mutation(value)

    with pytest.raises(MigrationOutcomeError):
        validate_outcome(value)
