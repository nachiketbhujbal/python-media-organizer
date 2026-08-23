"""Directional exact-byte coverage between two stable tree inventories."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pymo.migration.inventory import HashedEntry, TreeInventory

ByteIdentity = tuple[int, str]
CoverageVerdict = Literal["complete", "incomplete", "unproven"]


@dataclass(frozen=True)
class ByteCoverage:
    verdict: CoverageVerdict
    reasons: tuple[str, ...]
    source_unique_streams: int
    represented_unique_streams: int
    missing_unique_streams: int
    source_unique_bytes: int
    represented_unique_bytes: int
    missing_unique_bytes: int
    source_files: int
    represented_source_files: int
    missing_source_files: tuple[Path, ...]
    destination_only_unique_streams: int
    destination_only_files: tuple[Path, ...]
    destination_only_bytes: int
    source_duplicate_copies: int
    source_duplicate_bytes: int
    destination_duplicate_copies: int
    destination_duplicate_bytes: int
    reduced_copies: int
    reduced_copy_bytes: int
    added_copies: int
    added_copy_bytes: int


def _groups(
    entries: tuple[HashedEntry, ...],
) -> dict[ByteIdentity, tuple[HashedEntry, ...]]:
    grouped: dict[ByteIdentity, list[HashedEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.identity].append(entry)
    return {identity: tuple(values) for identity, values in grouped.items()}


def _duplicate_facts(
    groups: dict[ByteIdentity, tuple[HashedEntry, ...]],
) -> tuple[int, int]:
    copies = sum(max(0, len(entries) - 1) for entries in groups.values())
    byte_count = sum(
        identity[0] * max(0, len(entries) - 1) for identity, entries in groups.items()
    )
    return copies, byte_count


def compare_byte_inventories(
    source: TreeInventory, destination: TreeInventory
) -> ByteCoverage:
    """Account for every readable unique source byte stream in the destination."""

    source_groups = _groups(source.files)
    destination_groups = _groups(destination.files)
    source_identities = set(source_groups)
    destination_identities = set(destination_groups)
    represented = source_identities & destination_identities
    missing = source_identities - destination_identities
    destination_only = destination_identities - source_identities

    reasons: list[str] = []
    if not source.evidence_complete:
        reasons.append("source-inventory-incomplete")
        verdict: CoverageVerdict = "unproven"
    elif missing and not destination.evidence_complete:
        reasons.append("destination-inventory-incomplete")
        verdict = "unproven"
    elif missing:
        reasons.append("source-byte-streams-missing")
        verdict = "incomplete"
    else:
        verdict = "complete"

    source_counts = Counter(
        {identity: len(entries) for identity, entries in source_groups.items()}
    )
    destination_counts = Counter(
        {identity: len(entries) for identity, entries in destination_groups.items()}
    )
    reduced_copies = 0
    reduced_bytes = 0
    added_copies = 0
    added_bytes = 0
    for identity in represented:
        difference = source_counts[identity] - destination_counts[identity]
        if difference > 0:
            reduced_copies += difference
            reduced_bytes += difference * identity[0]
        elif difference < 0:
            added_copies -= difference
            added_bytes -= difference * identity[0]

    source_duplicate_copies, source_duplicate_bytes = _duplicate_facts(source_groups)
    destination_duplicate_copies, destination_duplicate_bytes = _duplicate_facts(
        destination_groups
    )
    missing_paths = tuple(
        entry.path for identity in sorted(missing) for entry in source_groups[identity]
    )
    destination_only_paths = tuple(
        entry.path
        for identity in sorted(destination_only)
        for entry in destination_groups[identity]
    )
    return ByteCoverage(
        verdict=verdict,
        reasons=tuple(reasons),
        source_unique_streams=len(source_groups),
        represented_unique_streams=len(represented),
        missing_unique_streams=len(missing),
        source_unique_bytes=sum(identity[0] for identity in source_groups),
        represented_unique_bytes=sum(identity[0] for identity in represented),
        missing_unique_bytes=sum(identity[0] for identity in missing),
        source_files=len(source.files),
        represented_source_files=sum(
            len(source_groups[identity]) for identity in represented
        ),
        missing_source_files=missing_paths,
        destination_only_unique_streams=len(destination_only),
        destination_only_files=destination_only_paths,
        destination_only_bytes=sum(
            entry.size
            for identity in destination_only
            for entry in destination_groups[identity]
        ),
        source_duplicate_copies=source_duplicate_copies,
        source_duplicate_bytes=source_duplicate_bytes,
        destination_duplicate_copies=destination_duplicate_copies,
        destination_duplicate_bytes=destination_duplicate_bytes,
        reduced_copies=reduced_copies,
        reduced_copy_bytes=reduced_bytes,
        added_copies=added_copies,
        added_copy_bytes=added_bytes,
    )
