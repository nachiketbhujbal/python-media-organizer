"""Exact displayed-image coverage for byte-missing source content."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError
from PIL import __version__ as pillow_version

from pymo.file_safety import FileChangedError, open_stable_file
from pymo.image_content import DISPLAYED_PIXEL_ALGORITHM, displayed_pixel_hash
from pymo.logging_config import emit as print
from pymo.migration.coverage import ByteIdentity
from pymo.migration.inventory import HashedEntry, TreeInventory
from pymo.progress import ProgressMeter

ImageCoverageVerdict = Literal["complete", "incomplete", "unproven", "not-needed"]


@dataclass(frozen=True)
class ImageInspectionIssue:
    path: Path
    category: str


@dataclass(frozen=True)
class PixelEntry:
    path: Path
    byte_identity: ByteIdentity
    pixel_sha256: str


@dataclass(frozen=True)
class ImageContentCoverage:
    verdict: ImageCoverageVerdict
    reasons: tuple[str, ...]
    algorithm: str
    runtime: str
    eligible_source_unique_streams: int
    eligible_source_files: int
    represented_unique_streams: int
    represented_source_files: tuple[Path, ...]
    missing_unique_streams: int
    missing_source_files: tuple[Path, ...]
    uninspectable_source_unique_streams: int
    source_issues: tuple[ImageInspectionIssue, ...]
    destination_candidate_unique_streams: int
    uninspectable_destination_unique_streams: int
    destination_issues: tuple[ImageInspectionIssue, ...]


def _groups(
    entries: tuple[HashedEntry, ...], extensions: frozenset[str]
) -> dict[ByteIdentity, tuple[HashedEntry, ...]]:
    grouped: dict[ByteIdentity, list[HashedEntry]] = defaultdict(list)
    for entry in entries:
        if entry.path.suffix.lower() in extensions:
            grouped[entry.identity].append(entry)
    return {
        identity: tuple(sorted(values, key=lambda item: str(item.path).casefold()))
        for identity, values in grouped.items()
    }


def _issue(path: Path, error: BaseException) -> ImageInspectionIssue:
    if isinstance(error, FileChangedError):
        category = "changed-during-image-inspection"
    elif isinstance(
        error, (Image.DecompressionBombError, Image.DecompressionBombWarning)
    ):
        category = "unsafe-image-content"
    elif isinstance(error, ValueError):
        category = "unsupported-image-content"
    else:
        category = "unreadable-image-content"
    return ImageInspectionIssue(path, category)


def _inspect_group(
    root: Path, identity: ByteIdentity, entries: tuple[HashedEntry, ...]
) -> tuple[PixelEntry | None, tuple[ImageInspectionIssue, ...]]:
    failures: list[ImageInspectionIssue] = []
    for entry in entries:
        try:
            with open_stable_file(
                root,
                entry.path,
                entry.state,
                "migration image inspection",
            ) as descriptor:
                pixel_sha256 = displayed_pixel_hash(descriptor)
        except (
            FileChangedError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            OSError,
            UnidentifiedImageError,
            ValueError,
        ) as error:
            failures.append(_issue(entry.path, error))
            continue
        return PixelEntry(entry.path, identity, pixel_sha256), ()
    return None, tuple(failures)


def _inspect_groups(
    inventory: TreeInventory,
    groups: dict[ByteIdentity, tuple[HashedEntry, ...]],
    progress_interval_seconds: int,
    *,
    show_progress: bool,
) -> tuple[dict[ByteIdentity, PixelEntry], tuple[ImageInspectionIssue, ...]]:
    inspected: dict[ByteIdentity, PixelEntry] = {}
    issues: list[ImageInspectionIssue] = []
    progress = ProgressMeter(
        len(groups),
        sum(identity[0] for identity in groups),
        progress_interval_seconds,
    )
    for identity, entries in sorted(groups.items()):
        value, failures = _inspect_group(inventory.root, identity, entries)
        inspected_bytes = 0
        if value is None:
            issues.extend(failures)
        else:
            inspected[identity] = value
            inspected_bytes = identity[0]
        message = progress.advance("inspected", byte_count=inspected_bytes)
        if show_progress and message:
            print(f"  {message}")
    return inspected, tuple(issues)


def compare_image_content(
    source: TreeInventory,
    destination: TreeInventory,
    extensions: frozenset[str],
    progress_interval_seconds: int,
    *,
    show_progress: bool,
) -> ImageContentCoverage:
    """Compare exact displayed pixels for source identities missing by bytes."""

    source_identities = {entry.identity for entry in source.files}
    destination_identities = {entry.identity for entry in destination.files}
    missing_byte_identities = source_identities - destination_identities
    source_groups = {
        identity: entries
        for identity, entries in _groups(source.files, extensions).items()
        if identity in missing_byte_identities
    }
    destination_groups = _groups(destination.files, extensions)

    if not source_groups:
        return ImageContentCoverage(
            verdict="not-needed",
            reasons=(),
            algorithm=DISPLAYED_PIXEL_ALGORITHM,
            runtime=f"Pillow {pillow_version}",
            eligible_source_unique_streams=0,
            eligible_source_files=0,
            represented_unique_streams=0,
            represented_source_files=(),
            missing_unique_streams=0,
            missing_source_files=(),
            uninspectable_source_unique_streams=0,
            source_issues=(),
            destination_candidate_unique_streams=len(destination_groups),
            uninspectable_destination_unique_streams=0,
            destination_issues=(),
        )

    source_pixels, source_issues = _inspect_groups(
        source,
        source_groups,
        progress_interval_seconds,
        show_progress=show_progress,
    )
    destination_pixels, destination_issues = _inspect_groups(
        destination,
        destination_groups,
        progress_interval_seconds,
        show_progress=show_progress,
    )
    destination_digests = {entry.pixel_sha256 for entry in destination_pixels.values()}
    represented = {
        identity
        for identity, entry in source_pixels.items()
        if entry.pixel_sha256 in destination_digests
    }
    missing = set(source_pixels) - represented
    uninspectable = set(source_groups) - set(source_pixels)

    reasons: list[str] = []
    verdict: ImageCoverageVerdict
    if source_issues:
        reasons.append("source-image-evidence-incomplete")
        verdict = "unproven"
    elif missing and destination_issues:
        reasons.append("destination-image-evidence-incomplete")
        verdict = "unproven"
    elif missing:
        reasons.append("image-content-missing")
        verdict = "incomplete"
    else:
        verdict = "complete"

    def source_paths(identities: set[ByteIdentity]) -> tuple[Path, ...]:
        return tuple(
            entry.path
            for identity in sorted(identities)
            for entry in source_groups[identity]
        )

    return ImageContentCoverage(
        verdict=verdict,
        reasons=tuple(reasons),
        algorithm=DISPLAYED_PIXEL_ALGORITHM,
        runtime=f"Pillow {pillow_version}",
        eligible_source_unique_streams=len(source_groups),
        eligible_source_files=sum(len(entries) for entries in source_groups.values()),
        represented_unique_streams=len(represented),
        represented_source_files=source_paths(represented),
        missing_unique_streams=len(missing),
        missing_source_files=source_paths(missing),
        uninspectable_source_unique_streams=len(uninspectable),
        source_issues=source_issues,
        destination_candidate_unique_streams=len(destination_groups),
        uninspectable_destination_unique_streams=(
            len(destination_groups) - len(destination_pixels)
        ),
        destination_issues=destination_issues,
    )
