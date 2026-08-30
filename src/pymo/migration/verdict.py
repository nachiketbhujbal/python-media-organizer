"""Final layered preservation verdict for a completed migration analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pymo.migration.coverage import ByteCoverage, ByteIdentity
from pymo.migration.images import ImageContentCoverage
from pymo.migration.inventory import StabilityEvidence, TreeInventory
from pymo.migration.videos import VideoContentCoverage

PreservationVerdict = Literal["complete", "incomplete", "unproven"]


@dataclass(frozen=True)
class PreservationEvidence:
    simulated: bool
    verdict: PreservationVerdict
    reasons: tuple[str, ...]
    source_unique_streams: int
    source_files: int
    accounted_unique_streams: int
    accounted_source_files: int
    byte_represented_unique_streams: int
    image_represented_unique_streams: int
    video_represented_unique_streams: int
    unaccounted_unique_streams: int
    unaccounted_source_files: tuple[Path, ...]
    unsupported_unique_streams: int
    unsupported_source_files: tuple[Path, ...]
    source_stability: StabilityEvidence
    destination_stability: StabilityEvidence
    source_excluded_entry_points: int
    destination_excluded_entry_points: int
    disposition: str


def _identities_for_paths(
    source: TreeInventory, paths: tuple[Path, ...]
) -> set[ByteIdentity]:
    by_path = {entry.path: entry.identity for entry in source.files}
    return {by_path[path] for path in paths if path in by_path}


def _paths_for_identities(
    source: TreeInventory, identities: set[ByteIdentity]
) -> tuple[Path, ...]:
    return tuple(entry.path for entry in source.files if entry.identity in identities)


def build_preservation_evidence(
    source: TreeInventory,
    destination: TreeInventory,
    byte_coverage: ByteCoverage,
    image_content: ImageContentCoverage,
    video_content: VideoContentCoverage,
    source_stability: StabilityEvidence,
    destination_stability: StabilityEvidence,
    classification_image_extensions: frozenset[str],
    exact_image_extensions: frozenset[str],
    *,
    simulated: bool = False,
) -> PreservationEvidence:
    """Combine fresh byte and exact-media evidence without hiding its layers."""

    source_identities = {entry.identity for entry in source.files}
    destination_identities = {entry.identity for entry in destination.files}
    byte_represented = source_identities & destination_identities
    image_represented = (
        _identities_for_paths(source, image_content.represented_source_files)
        - byte_represented
    )
    video_represented = (
        _identities_for_paths(source, video_content.represented_source_files)
        - byte_represented
        - image_represented
    )
    accounted = byte_represented | image_represented | video_represented
    unaccounted = source_identities - accounted

    image_problem_identities = _identities_for_paths(
        source, tuple(issue.path for issue in image_content.source_issues)
    )
    video_problem_identities = _identities_for_paths(
        source, tuple(issue.path for issue in video_content.source_issues)
    )
    unsupported_extensions: set[ByteIdentity] = set()
    for entry in source.files:
        suffix = entry.path.suffix.lower()
        if (
            suffix in classification_image_extensions
            and suffix not in exact_image_extensions
        ):
            unsupported_extensions.add(entry.identity)
    unsupported = unaccounted & (
        image_problem_identities | video_problem_identities | unsupported_extensions
    )

    reasons: list[str] = []
    evidence_incomplete = not all(
        (
            source.evidence_complete,
            destination.evidence_complete,
            source_stability.complete,
            destination_stability.complete,
        )
    )
    if evidence_incomplete:
        reasons.append("filesystem-evidence-incomplete")
        verdict: PreservationVerdict = "unproven"
    elif unsupported:
        reasons.append("unsupported-source-media")
        verdict = "unproven"
    elif unaccounted and (
        image_content.verdict == "unproven"
        or video_content.verdict == "unproven"
        or byte_coverage.verdict == "unproven"
    ):
        reasons.append("media-equivalence-evidence-incomplete")
        verdict = "unproven"
    elif unaccounted:
        reasons.append("source-content-unaccounted")
        verdict = "incomplete"
    else:
        verdict = "complete"

    unaccounted_paths = _paths_for_identities(source, unaccounted)
    unsupported_paths = _paths_for_identities(source, unsupported)
    return PreservationEvidence(
        simulated=simulated,
        verdict=verdict,
        reasons=tuple(reasons),
        source_unique_streams=len(source_identities),
        source_files=len(source.files),
        accounted_unique_streams=len(accounted),
        accounted_source_files=sum(
            entry.identity in accounted for entry in source.files
        ),
        byte_represented_unique_streams=len(byte_represented),
        image_represented_unique_streams=len(image_represented),
        video_represented_unique_streams=len(video_represented),
        unaccounted_unique_streams=len(unaccounted),
        unaccounted_source_files=unaccounted_paths,
        unsupported_unique_streams=len(unsupported),
        unsupported_source_files=unsupported_paths,
        source_stability=source_stability,
        destination_stability=destination_stability,
        source_excluded_entry_points=(
            source_stability.ignored_entry_points + source_stability.tool_state_entries
        ),
        destination_excluded_entry_points=(
            destination_stability.ignored_entry_points
            + destination_stability.tool_state_entries
        ),
        disposition=(
            "eligible-for-human-quarantine-review"
            if verdict == "complete" and simulated
            else (
                "eligible-for-human-signoff"
                if verdict == "complete"
                else "retain-source-and-resolve-findings"
            )
        ),
    )
