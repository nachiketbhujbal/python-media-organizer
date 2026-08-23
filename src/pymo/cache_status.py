"""Read-only health and coverage reporting for pymo's derived cache."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from pymo import cache as cache_service
from pymo.collection import CollectionLayout
from pymo.duplicates import videos
from pymo.logging_config import emit as print
from pymo.progress import format_bytes

# This value identifies the stable machine-readable cache-status contract.
CACHE_STATUS_REPORT_SCHEMA_VERSION = 1


def _base_report(location: str) -> dict[str, object]:
    return {
        "schema_version": CACHE_STATUS_REPORT_SCHEMA_VERSION,
        "cache": {
            "location": location,
            "state": "missing",
            "format": None,
            "cache_schema_version": None,
            "bytes": 0,
            "evidence_records": 0,
            "evidence_types": {},
            "evidence_namespaces": 0,
            "evidence_compatibility": {
                "algorithm_compatible": 0,
                "stale_algorithm": 0,
                "unknown_type": 0,
                "runtime_checked": False,
            },
            "evidence_coverage": {
                "linked_to_observation": 0,
                "linked_to_current_observation": 0,
                "unlinked": 0,
            },
            "file_observations": {
                "total": 0,
                "current": 0,
                "stale": 0,
                "unreadable": 0,
            },
            "legacy_migration_pending": False,
            "issue": None,
        },
        "writes_performed": False,
    }


def _observation_state(root: Path, record: cache_service.FileObservation) -> str:
    relative = PurePosixPath(record.relative_path)
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    directory_descriptor: int | None = None
    try:
        directory_descriptor = os.open(root, directory_flags)
        for part in relative.parts[:-1]:
            next_descriptor = os.open(
                part, directory_flags, dir_fd=directory_descriptor
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        value = os.stat(
            relative.name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return "stale"
    except OSError:
        return "unreadable"
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
    if not stat.S_ISREG(value.st_mode):
        return "stale"
    observed = (
        record.device,
        record.inode,
        record.size,
        record.modified_ns,
        record.changed_ns,
    )
    current = (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
    return "current" if observed == current else "stale"


def inspect_cache_status(
    root: Path, database: Path, *, location: str
) -> tuple[dict[str, object], int]:
    """Return one path-private report and its health exit status."""

    report = _base_report(location)
    cache = report["cache"]
    assert isinstance(cache, dict)
    try:
        with cache_service.read_cache_snapshot(database) as snapshot:
            if snapshot is None:
                return report, 0
            connection = snapshot.connection
            cache["bytes"] = snapshot.state.size
            contents = cache_service.read_cache_contents(connection)
            schema = contents.schema_kind
            cache["state"] = "healthy"
            if schema == "legacy-video":
                cache["format"] = "legacy-video"
                cache["legacy_migration_pending"] = True
            elif schema == "current":
                cache["format"] = "shared"
                cache["cache_schema_version"] = cache_service.SCHEMA_VERSION
            else:
                raise cache_service.CacheError("SQLite cache has no schema")
            evidence = contents.evidence
            observations = contents.observations

            exact_video = [
                record
                for record in evidence
                if record.evidence_type == cache_service.LEGACY_VIDEO_EVIDENCE_TYPE
            ]
            videos.decode_video_evidence(exact_video)
            type_counts = Counter(record.evidence_type for record in evidence)
            cache["evidence_records"] = len(evidence)
            cache["evidence_types"] = dict(sorted(type_counts.items()))
            cache["evidence_namespaces"] = len(
                {
                    (record.evidence_type, record.algorithm, record.runtime)
                    for record in evidence
                }
            )
            compatible = sum(
                record.algorithm == videos.FINGERPRINT_ALGORITHM
                for record in exact_video
            )
            compatibility = cache["evidence_compatibility"]
            assert isinstance(compatibility, dict)
            compatibility.update(
                {
                    "algorithm_compatible": compatible,
                    "stale_algorithm": len(exact_video) - compatible,
                    "unknown_type": len(evidence) - len(exact_video),
                }
            )

            observed_states = [
                (record, _observation_state(root, record)) for record in observations
            ]
            observation_counts = Counter(state for _record, state in observed_states)
            observation_report = cache["file_observations"]
            assert isinstance(observation_report, dict)
            observation_report.update(
                {
                    "total": len(observations),
                    "current": observation_counts["current"],
                    "stale": observation_counts["stale"],
                    "unreadable": observation_counts["unreadable"],
                }
            )

            linked_hashes = {
                record.byte_sha256
                for record, _state in observed_states
                if record.byte_sha256 is not None
            }
            current_hashes = {
                record.byte_sha256
                for record, state in observed_states
                if record.byte_sha256 is not None and state == "current"
            }
            linked = sum(record.file_sha256 in linked_hashes for record in evidence)
            current = sum(record.file_sha256 in current_hashes for record in evidence)
            coverage = cache["evidence_coverage"]
            assert isinstance(coverage, dict)
            coverage.update(
                {
                    "linked_to_observation": linked,
                    "linked_to_current_observation": current,
                    "unlinked": len(evidence) - linked,
                }
            )
    except (cache_service.CacheError, videos.VideoInspectionError):
        cache["state"] = "invalid"
        cache["issue"] = "unsafe-unreadable-or-incompatible"
        return report, 1
    return report, 0


def print_report(report: dict[str, object]) -> None:
    cache = report["cache"]
    assert isinstance(cache, dict)
    print("Derived cache status:")
    print(f"  State: {cache['state']}")
    print(f"  Location: {cache['location']}")
    if cache["state"] == "missing":
        print("  Cache file: not created")
    elif cache["state"] == "invalid":
        print("  Cache file: present but unsafe, unreadable, or incompatible")
    else:
        format_name = (
            f"shared schema {cache['cache_schema_version']}"
            if cache["format"] == "shared"
            else "legacy exact-video schema"
        )
        print(f"  Format: {format_name}")
        print(f"  Storage: {format_bytes(int(cache['bytes']))}")
        print(f"  Evidence records: {cache['evidence_records']}")
        print(f"  Evidence namespaces: {cache['evidence_namespaces']}")
        compatibility = cache["evidence_compatibility"]
        assert isinstance(compatibility, dict)
        print(
            "  Algorithm compatibility: "
            f"{compatibility['algorithm_compatible']} current; "
            f"{compatibility['stale_algorithm']} stale; "
            f"{compatibility['unknown_type']} unknown-type"
        )
        print("  Runtime compatibility: not checked by cache status")
        evidence_types = cache["evidence_types"]
        assert isinstance(evidence_types, dict)
        if evidence_types:
            print("  Evidence types:")
            for evidence_type, count in evidence_types.items():
                print(f"    {json.dumps(evidence_type)}: {count}")
        observations = cache["file_observations"]
        assert isinstance(observations, dict)
        print(
            "  File observations: "
            f"{observations['total']} total; {observations['current']} current; "
            f"{observations['stale']} stale; "
            f"{observations['unreadable']} unreadable"
        )
        coverage = cache["evidence_coverage"]
        assert isinstance(coverage, dict)
        print(
            "  Evidence coverage: "
            f"{coverage['linked_to_observation']} linked; "
            f"{coverage['linked_to_current_observation']} linked to current files; "
            f"{coverage['unlinked']} unlinked"
        )
        if cache["legacy_migration_pending"]:
            print("  Migration: pending until the next successful cache write")
    print("  Read-only: no cache, lock, media, or action state was written.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pymo cache", description="Inspect derived cache state."
    )
    parser.add_argument("action", choices=("status",))
    parser.add_argument("folder", type=Path, help="media-collection root")
    parser.add_argument(
        "--cache",
        type=Path,
        help="inspect this cache file instead of the collection-local default",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit one machine-readable JSON report instead of terminal text",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = args.folder.expanduser().resolve()
    except (OSError, RuntimeError):
        root = args.folder.expanduser()
    if not root.is_dir():
        if args.json:
            report = _base_report("explicit" if args.cache else "collection-local")
            cache = report["cache"]
            assert isinstance(cache, dict)
            cache["state"] = "invalid"
            cache["issue"] = "collection-not-directory"
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        else:
            print("Media-collection root is not a directory.", file=sys.stderr)
        return 2
    if args.cache is None:
        database = CollectionLayout(root).derived_cache
        location = "collection-local"
    else:
        database = Path(os.path.abspath(args.cache.expanduser()))
        location = "explicit"
    report, status = inspect_cache_status(root, database, location=location)
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print_report(report)
    return status
