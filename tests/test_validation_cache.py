from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from pymo import validate
from pymo.action_log import action_log_path
from pymo.cache import service as cache_service
from pymo.cache import status as cache_status
from pymo.cache.validation import (
    VALIDATION_EVIDENCE_TYPE,
    VALIDATION_FULL_ALGORITHM,
    VALIDATION_STANDARD_ALGORITHM,
    ValidationCacheError,
    ValidationEvidenceValue,
    ValidationFindingValue,
    decode_validation_payload,
    decode_validation_runtime,
    encode_validation_payload,
)
from pymo.collection import CollectionLayout


def validation_records(
    database: Path,
) -> tuple[cache_service.CacheContents, list[cache_service.DerivedEvidence]]:
    contents = cache_service.read_coordinated_cache(database)
    assert contents is not None
    records = [
        record
        for record in contents.evidence
        if record.evidence_type == VALIDATION_EVIDENCE_TYPE
    ]
    return contents, records


def test_default_validation_records_fresh_path_private_evidence(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    media = root / "fern.png"
    Image.new("RGB", (3, 2), "green").save(media)
    original = media.read_bytes()
    layout = CollectionLayout(root)

    result = run_script("validate.py", root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "Fresh validation evidence will be cached (collection-local)" in result.stdout
    )
    assert "1 validated file record(s) written" in result.stdout
    assert media.read_bytes() == original
    assert layout.derived_cache.is_file()
    assert layout.derived_cache_lock.is_file()
    assert not layout.dups.exists()
    assert not action_log_path(root).exists()

    contents, records = validation_records(layout.derived_cache)
    assert len(records) == 1
    record = records[0]
    assert record.algorithm == VALIDATION_STANDARD_ALGORITHM
    assert record.file_sha256 == hashlib.sha256(original).hexdigest()
    payload = decode_validation_payload(record.payload_json, record.algorithm)
    runtime = decode_validation_runtime(record.runtime)
    assert payload["outcome"] == "healthy"
    assert payload["profile"] == "standard"
    assert payload["kind"] == runtime["kind"] == "picture"
    assert datetime.fromisoformat(str(payload["completed_at"])).tzinfo is not None
    assert len(contents.observations) == 1
    assert contents.observations[0].relative_path == "fern.png"
    assert contents.observations[0].byte_sha256 == record.file_sha256
    status_report, status_code = cache_status.inspect_cache_status(
        root, layout.derived_cache, location="collection-local"
    )
    assert status_code == 0
    assert status_report["cache"]["evidence_types"] == {"media-validation": 1}
    assert status_report["cache"]["evidence_compatibility"] == {
        "algorithm_compatible": 1,
        "stale_algorithm": 0,
        "unknown_type": 0,
        "runtime_checked": False,
    }


def test_validation_no_cache_retains_the_zero_state_boundary(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    media = root / "cedar.png"
    Image.new("RGB", (2, 2), "blue").save(media)
    before = media.read_bytes()

    result = run_script("validate.py", root, "--no-cache")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Validation cache disabled: no records read or written" in result.stdout
    assert media.read_bytes() == before
    assert sorted(path.name for path in root.iterdir()) == ["cedar.png"]


def test_validation_can_write_only_to_an_explicit_external_cache(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    Image.new("RGB", (2, 2), "green").save(root / "willow.png")
    external = tmp_path / "derived"
    external.mkdir()
    database = external / "portable.sqlite3"

    result = run_script("validate.py", root, "--cache", database)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Fresh validation evidence will be cached (explicit)" in result.stdout
    assert database.is_file()
    assert database.with_name(f"{database.name}.lock").is_file()
    assert not CollectionLayout(root).derived_cache.exists()
    assert not CollectionLayout(root).derived_cache_lock.exists()
    assert not action_log_path(root).exists()
    assert sorted(path.name for path in root.iterdir()) == ["willow.png"]
    assert str(root) not in result.stdout + result.stderr


def test_full_validation_never_uses_an_old_healthy_result_as_current_health(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    media = root / "orchid.png"
    Image.new("RGB", (2, 2), "green").save(media)
    layout = CollectionLayout(root)

    healthy = run_script("validate.py", root, "--full")
    media.write_bytes(b"damaged image content")
    damaged = run_script("validate.py", root, "--full")

    assert healthy.returncode == 0, healthy.stdout + healthy.stderr
    assert damaged.returncode == 1, damaged.stdout + damaged.stderr
    assert "ERROR invalid_image: 1 file(s)" in damaged.stdout
    contents, records = validation_records(layout.derived_cache)
    full = [
        record for record in records if record.algorithm == VALIDATION_FULL_ALGORITHM
    ]
    assert len(full) == 2
    outcomes = {
        decode_validation_payload(record.payload_json, record.algorithm)["outcome"]
        for record in full
    }
    assert outcomes == {"healthy", "error"}
    assert (
        contents.observations[0].byte_sha256
        == hashlib.sha256(media.read_bytes()).hexdigest()
    )


def test_validation_context_keeps_identical_bytes_with_distinct_extensions(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    first = root / "maple.png"
    second = root / "maple.jpg"
    Image.new("RGB", (2, 2), "green").save(first)
    second.write_bytes(first.read_bytes())

    result = run_script("validate.py", root)

    assert result.returncode == 0, result.stdout + result.stderr
    contents, records = validation_records(CollectionLayout(root).derived_cache)
    assert len(records) == 2
    assert len({record.runtime for record in records}) == 2
    assert {
        decode_validation_runtime(record.runtime)["extension"] for record in records
    } == {
        ".jpg",
        ".png",
    }
    assert len(contents.observations) == 2


def test_cache_status_rejects_malformed_validation_evidence(tmp_path: Path) -> None:
    database = CollectionLayout(tmp_path).derived_cache
    connection = sqlite3.connect(database)
    cache_service.initialize_schema(connection)
    cache_service.upsert_derived_evidence(
        connection,
        (
            cache_service.DerivedEvidence(
                file_sha256="a" * 64,
                evidence_type=VALIDATION_EVIDENCE_TYPE,
                algorithm=VALIDATION_STANDARD_ALGORITHM,
                runtime="{}",
                payload_json=json.dumps({"bad": True}),
            ),
        ),
    )
    connection.commit()
    connection.close()
    original = database.read_bytes()

    report, result = cache_status.inspect_cache_status(
        tmp_path, database, location="collection-local"
    )

    assert result == 1
    assert report["cache"]["state"] == "invalid"
    assert database.read_bytes() == original
    assert not CollectionLayout(tmp_path).derived_cache_lock.exists()


def test_invalid_existing_validation_evidence_stops_before_media_reads(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    media = root / "harbor.png"
    Image.new("RGB", (2, 2), "green").save(media)
    database = CollectionLayout(root).derived_cache
    connection = sqlite3.connect(database)
    cache_service.initialize_schema(connection)
    cache_service.upsert_derived_evidence(
        connection,
        (
            cache_service.DerivedEvidence(
                file_sha256="a" * 64,
                evidence_type=VALIDATION_EVIDENCE_TYPE,
                algorithm=VALIDATION_STANDARD_ALGORITHM,
                runtime="{}",
                payload_json='{"bad":true}',
            ),
        ),
    )
    connection.commit()
    connection.close()
    cache_before = database.read_bytes()
    media_before = media.read_bytes()

    result = run_script("validate.py", root)

    assert result.returncode == 1
    assert "Validation cache cannot be used safely" in result.stderr
    assert media.read_bytes() == media_before
    assert database.read_bytes() == cache_before
    assert not action_log_path(root).exists()


@pytest.mark.parametrize(
    ("runtime", "match"),
    [
        ("not-json", "invalid runtime"),
        ("{}", "invalid runtime"),
        (
            '{"detected_kind":"picture","extension":".png",'
            '"extension_kind":"picture","ffmpeg":null,"ffprobe":null,'
            '"kind":"picture","pillow":null}',
            "invalid runtime",
        ),
    ],
)
def test_validation_runtime_rejects_malformed_namespaces(
    runtime: str, match: str
) -> None:
    with pytest.raises(ValidationCacheError, match=match):
        decode_validation_runtime(runtime)


def test_validation_payload_rejects_an_inconsistent_outcome(tmp_path: Path) -> None:
    value = ValidationEvidenceValue(
        path=tmp_path / "fern.png",
        state=validate.FileState(1, 2, 3, 4, 5),
        byte_sha256="a" * 64,
        kind="picture",
        profile="standard",
        runtime="runtime",
        completed_at="2026-08-23T00:00:00.000000+00:00",
        findings=(ValidationFindingValue("error", "invalid", "invalid media"),),
        animated_or_multipage=False,
    )
    payload = json.loads(encode_validation_payload(value))
    payload["outcome"] = "healthy"

    with pytest.raises(ValidationCacheError, match="invalid evidence"):
        decode_validation_payload(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            VALIDATION_STANDARD_ALGORITHM,
        )


def test_validation_publication_retains_completed_batches_after_later_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "media-collection"
    root.mkdir()
    paths = [root / "fern.png", root / "willow.png"]
    for path, color in zip(paths, ("green", "blue"), strict=True):
        Image.new("RGB", (2, 2), color).save(path)
    results = tuple(
        validate.ValidationResult(
            candidate=validate.MediaCandidate(
                root=root,
                path=path,
                state=validate.FileState.capture(path),
                kind="picture",
                extension_kind="picture",
                detected_kind="picture",
            ),
            findings=(),
            byte_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            completed_at="2026-08-23T00:00:00.000000+00:00",
        )
        for path in paths
    )
    database = CollectionLayout(root).derived_cache
    publish = validate.publish_validation_batch
    calls = 0

    def fail_second(*args, **kwargs) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValidationCacheError("synthetic publication failure")
        publish(*args, **kwargs)

    monkeypatch.setattr(validate, "publish_validation_batch", fail_second)

    written, issue = validate.publish_validation_results(
        root,
        database,
        results,
        "standard",
        None,
        None,
        1,
    )

    assert written == 1
    assert issue == "validation evidence could not be published safely"
    contents, records = validation_records(database)
    assert len(contents.observations) == 1
    assert len(records) == 1
