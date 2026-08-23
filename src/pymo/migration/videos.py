"""Strict decoded-playback coverage for byte-missing source videos."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pymo.file_safety import FileChangedError, open_stable_file
from pymo.logging_config import emit as print
from pymo.migration.coverage import ByteIdentity
from pymo.migration.inventory import HashedEntry, TreeInventory
from pymo.progress import ProgressMeter
from pymo.video import ProbeInfo
from pymo.video_content import (
    EXACT_PLAYBACK_ALGORITHM,
    DerivedFingerprint,
    VideoInspectionError,
    derive_fingerprint,
    probe_video,
)

VideoCoverageVerdict = Literal["complete", "incomplete", "unproven", "not-needed"]


@dataclass(frozen=True)
class VideoInspectionIssue:
    path: Path
    category: str


@dataclass(frozen=True)
class ProbedVideo:
    entry: HashedEntry
    probe: ProbeInfo


@dataclass(frozen=True)
class PlaybackEntry:
    path: Path
    byte_identity: ByteIdentity
    fingerprint: DerivedFingerprint


@dataclass(frozen=True)
class VideoContentCoverage:
    verdict: VideoCoverageVerdict
    reasons: tuple[str, ...]
    algorithm: str
    ffmpeg_runtime: str | None
    ffprobe_runtime: str | None
    eligible_source_unique_streams: int
    eligible_source_files: int
    represented_unique_streams: int
    represented_source_files: tuple[Path, ...]
    missing_unique_streams: int
    missing_source_files: tuple[Path, ...]
    uninspectable_source_unique_streams: int
    source_issues: tuple[VideoInspectionIssue, ...]
    destination_candidate_unique_streams: int
    uninspectable_destination_unique_streams: int
    destination_issues: tuple[VideoInspectionIssue, ...]


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


def _source_groups(
    source: TreeInventory,
    destination: TreeInventory,
    extensions: frozenset[str],
) -> dict[ByteIdentity, tuple[HashedEntry, ...]]:
    destination_identities = {entry.identity for entry in destination.files}
    return {
        identity: entries
        for identity, entries in _groups(source.files, extensions).items()
        if identity not in destination_identities
    }


def video_content_required(
    source: TreeInventory,
    destination: TreeInventory,
    extensions: frozenset[str],
) -> bool:
    return bool(_source_groups(source, destination, extensions))


def not_needed_video_content(
    destination: TreeInventory, extensions: frozenset[str]
) -> VideoContentCoverage:
    return VideoContentCoverage(
        verdict="not-needed",
        reasons=(),
        algorithm=EXACT_PLAYBACK_ALGORITHM,
        ffmpeg_runtime=None,
        ffprobe_runtime=None,
        eligible_source_unique_streams=0,
        eligible_source_files=0,
        represented_unique_streams=0,
        represented_source_files=(),
        missing_unique_streams=0,
        missing_source_files=(),
        uninspectable_source_unique_streams=0,
        source_issues=(),
        destination_candidate_unique_streams=len(
            _groups(destination.files, extensions)
        ),
        uninspectable_destination_unique_streams=0,
        destination_issues=(),
    )


def _issue(path: Path, error: BaseException, stage: str) -> VideoInspectionIssue:
    category = (
        f"changed-during-video-{stage}"
        if isinstance(error, FileChangedError)
        else f"uninspectable-video-{stage}"
    )
    return VideoInspectionIssue(path, category)


def _probe_group(
    root: Path,
    entries: tuple[HashedEntry, ...],
    ffprobe: str,
) -> tuple[ProbedVideo | None, tuple[VideoInspectionIssue, ...]]:
    failures: list[VideoInspectionIssue] = []
    for entry in entries:
        try:
            with open_stable_file(
                root, entry.path, entry.state, "migration video structure inspection"
            ) as descriptor:
                probe = probe_video(descriptor, ffprobe)
        except (FileChangedError, OSError, VideoInspectionError) as error:
            failures.append(_issue(entry.path, error, "probe"))
            continue
        return ProbedVideo(entry, probe), ()
    return None, tuple(failures)


def _probe_groups(
    inventory: TreeInventory,
    groups: dict[ByteIdentity, tuple[HashedEntry, ...]],
    ffprobe: str,
    progress_interval_seconds: int,
    *,
    show_progress: bool,
) -> tuple[dict[ByteIdentity, ProbedVideo], tuple[VideoInspectionIssue, ...]]:
    values: dict[ByteIdentity, ProbedVideo] = {}
    issues: list[VideoInspectionIssue] = []
    progress = ProgressMeter(
        len(groups),
        sum(identity[0] for identity in groups),
        progress_interval_seconds,
    )
    for identity, entries in sorted(groups.items()):
        value, failures = _probe_group(inventory.root, entries, ffprobe)
        inspected_bytes = 0
        if value is None:
            issues.extend(failures)
        else:
            values[identity] = value
            inspected_bytes = identity[0]
        message = progress.advance("probed", byte_count=inspected_bytes)
        if show_progress and message:
            print(f"  {message}")
    return values, tuple(issues)


def _fingerprint_groups(
    inventory: TreeInventory,
    values: dict[ByteIdentity, ProbedVideo],
    ffmpeg: str,
    decode_timeout: int,
    progress_interval_seconds: int,
    *,
    show_progress: bool,
) -> tuple[dict[ByteIdentity, PlaybackEntry], tuple[VideoInspectionIssue, ...]]:
    fingerprints: dict[ByteIdentity, PlaybackEntry] = {}
    issues: list[VideoInspectionIssue] = []
    ordered = sorted(values.items())
    progress = ProgressMeter(
        len(ordered),
        sum(identity[0] for identity, _ in ordered),
        progress_interval_seconds,
    )
    for number, (identity, value) in enumerate(ordered, start=1):
        if show_progress:
            print(f"  starting playback fingerprint {number}/{len(ordered)}")

        def heartbeat(active_number: int = number) -> None:
            message = progress.heartbeat("playback fingerprint progress", active_number)
            if show_progress and message:
                print(f"  {message}")

        fingerprinted_bytes = 0
        try:
            with open_stable_file(
                inventory.root,
                value.entry.path,
                value.entry.state,
                "migration video playback inspection",
            ) as descriptor:
                fingerprint = derive_fingerprint(
                    descriptor,
                    value.probe,
                    ffmpeg,
                    decode_timeout,
                    heartbeat,
                )
        except (FileChangedError, OSError, VideoInspectionError) as error:
            issues.append(_issue(value.entry.path, error, "playback"))
        else:
            fingerprints[identity] = PlaybackEntry(
                value.entry.path, identity, fingerprint
            )
            fingerprinted_bytes = identity[0]
        message = progress.advance(
            "playback fingerprint progress", byte_count=fingerprinted_bytes
        )
        if show_progress and message:
            print(f"  {message}")
    return fingerprints, tuple(issues)


def compare_video_content(
    source: TreeInventory,
    destination: TreeInventory,
    extensions: frozenset[str],
    ffmpeg: str,
    ffprobe: str,
    ffmpeg_runtime: str,
    ffprobe_runtime: str,
    decode_timeout: int,
    progress_interval_seconds: int,
    *,
    show_progress: bool,
) -> VideoContentCoverage:
    """Compare strict decoded playback for source identities missing by bytes."""

    source_groups = _source_groups(source, destination, extensions)
    if not source_groups:
        return not_needed_video_content(destination, extensions)
    destination_groups = _groups(destination.files, extensions)
    source_probes, source_probe_issues = _probe_groups(
        source,
        source_groups,
        ffprobe,
        progress_interval_seconds,
        show_progress=show_progress,
    )
    destination_probes, destination_probe_issues = _probe_groups(
        destination,
        destination_groups,
        ffprobe,
        progress_interval_seconds,
        show_progress=show_progress,
    )
    source_fingerprints, source_decode_issues = _fingerprint_groups(
        source,
        source_probes,
        ffmpeg,
        decode_timeout,
        progress_interval_seconds,
        show_progress=show_progress,
    )
    relevant_keys = {value.probe.candidate_key for value in source_probes.values()}
    relevant_destination = {
        identity: value
        for identity, value in destination_probes.items()
        if value.probe.candidate_key in relevant_keys
    }
    destination_fingerprints, destination_decode_issues = _fingerprint_groups(
        destination,
        relevant_destination,
        ffmpeg,
        decode_timeout,
        progress_interval_seconds,
        show_progress=show_progress,
    )
    source_issues = (*source_probe_issues, *source_decode_issues)
    destination_issues = (*destination_probe_issues, *destination_decode_issues)
    destination_digests = {
        value.fingerprint.digest for value in destination_fingerprints.values()
    }
    represented = {
        identity
        for identity, value in source_fingerprints.items()
        if value.fingerprint.digest in destination_digests
    }
    missing = set(source_fingerprints) - represented
    uninspectable = set(source_groups) - set(source_fingerprints)

    reasons: list[str] = []
    verdict: VideoCoverageVerdict
    if source_issues:
        reasons.append("source-video-evidence-incomplete")
        verdict = "unproven"
    elif missing and destination_issues:
        reasons.append("destination-video-evidence-incomplete")
        verdict = "unproven"
    elif missing:
        reasons.append("video-content-missing")
        verdict = "incomplete"
    else:
        verdict = "complete"

    def source_paths(identities: set[ByteIdentity]) -> tuple[Path, ...]:
        return tuple(
            entry.path
            for identity in sorted(identities)
            for entry in source_groups[identity]
        )

    unavailable_destination = (set(destination_groups) - set(destination_probes)) | (
        set(relevant_destination) - set(destination_fingerprints)
    )
    return VideoContentCoverage(
        verdict=verdict,
        reasons=tuple(reasons),
        algorithm=EXACT_PLAYBACK_ALGORITHM,
        ffmpeg_runtime=ffmpeg_runtime,
        ffprobe_runtime=ffprobe_runtime,
        eligible_source_unique_streams=len(source_groups),
        eligible_source_files=sum(len(entries) for entries in source_groups.values()),
        represented_unique_streams=len(represented),
        represented_source_files=source_paths(represented),
        missing_unique_streams=len(missing),
        missing_source_files=source_paths(missing),
        uninspectable_source_unique_streams=len(uninspectable),
        source_issues=source_issues,
        destination_candidate_unique_streams=len(destination_groups),
        uninspectable_destination_unique_streams=len(unavailable_destination),
        destination_issues=destination_issues,
    )
