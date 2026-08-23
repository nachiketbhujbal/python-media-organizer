"""Versioned displayed-pixel image evidence in the shared cache."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from pymo.cache import service as cache_service
from pymo.cache.hashes import build_hash_observations
from pymo.file_safety import FileState
from pymo.image_content import DISPLAYED_PIXEL_ALGORITHM

# These values identify persisted derived evidence. Changing displayed-pixel
# normalization requires a new algorithm identifier.
IMAGE_PIXEL_EVIDENCE_TYPE = "displayed-pixels"
IMAGE_PIXEL_ALGORITHM = DISPLAYED_PIXEL_ALGORITHM


class ImageCacheError(RuntimeError):
    """Cached displayed-pixel evidence cannot be used safely."""


def encode_pixel_hash(digest: str) -> str:
    """Return the canonical persisted payload for one pixel digest."""

    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ImageCacheError("invalid displayed-pixel digest")
    return json.dumps({"digest": digest}, sort_keys=True, separators=(",", ":"))


def decode_pixel_payload(payload_json: str) -> str:
    """Validate and decode one displayed-pixel payload."""

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise ImageCacheError(
            "cached displayed-pixel fingerprint contains invalid evidence"
        ) from error
    if not isinstance(payload, dict) or set(payload) != {"digest"}:
        raise ImageCacheError(
            "cached displayed-pixel fingerprint contains invalid evidence"
        )
    digest = payload["digest"]
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ImageCacheError(
            "cached displayed-pixel fingerprint contains invalid evidence"
        )
    return digest


def decode_pixel_evidence(
    records: list[cache_service.DerivedEvidence],
) -> dict[str, str]:
    """Decode compatible evidence keyed by complete-file SHA-256."""

    decoded: dict[str, str] = {}
    for record in records:
        if record.file_sha256 in decoded:
            raise ImageCacheError(
                "cached displayed-pixel fingerprint contains duplicate evidence"
            )
        decoded[record.file_sha256] = decode_pixel_payload(record.payload_json)
    return decoded


def load_cached_pixel_hashes(database: Path, runtime: str) -> dict[str, str]:
    """Load compatible displayed-pixel fingerprints through coordinated access."""

    try:
        contents = cache_service.read_coordinated_cache(database)
        if contents is None:
            return {}
        records = [
            record
            for record in contents.evidence
            if record.evidence_type == IMAGE_PIXEL_EVIDENCE_TYPE
            and record.algorithm == IMAGE_PIXEL_ALGORITHM
            and record.runtime == runtime
        ]
        return decode_pixel_evidence(records)
    except (cache_service.CacheError, sqlite3.Error, OSError) as error:
        raise ImageCacheError("displayed-pixel cache cannot be read safely") from error


def build_pixel_evidence(
    runtime: str, values: dict[str, str]
) -> tuple[cache_service.DerivedEvidence, ...]:
    """Build normalized pixel records for one atomic publication."""

    return tuple(
        cache_service.DerivedEvidence(
            file_sha256=file_hash,
            evidence_type=IMAGE_PIXEL_EVIDENCE_TYPE,
            algorithm=IMAGE_PIXEL_ALGORITHM,
            runtime=runtime,
            payload_json=encode_pixel_hash(pixel_hash),
        )
        for file_hash, pixel_hash in sorted(values.items())
    )


def publish_image_analysis_batch(
    root: Path,
    database: Path,
    runtime: str,
    hashes: Iterable[tuple[Path, FileState, str]],
    pixels: dict[str, str],
) -> None:
    """Publish image byte observations and pixel evidence in one transaction."""

    observations = build_hash_observations(root, hashes)
    evidence = build_pixel_evidence(runtime, pixels)
    if not observations and not evidence:
        return

    def update(connection: sqlite3.Connection) -> None:
        cache_service.upsert_file_observations(connection, observations)
        cache_service.upsert_derived_evidence(connection, evidence)

    try:
        cache_service.publish_cache_update(database, update)
    except cache_service.CacheError as error:
        raise ImageCacheError(
            "displayed-pixel cache cannot be updated safely"
        ) from error
