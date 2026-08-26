"""Report-only media health validation for a collection."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import warnings
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageSequence, UnidentifiedImageError, __version__

from pymo.action_log import is_action_log_path
from pymo.cache.hashes import sha256_descriptor
from pymo.cache.paths import CachePathError, writable_cache_path
from pymo.cache.validation import (
    CachedValidationResult,
    ValidationCacheError,
    ValidationEvidenceValue,
    ValidationFindingValue,
    ValidationLookup,
    ValidationProfile,
    completed_timestamp,
    load_compatible_validation,
    preflight_validation_cache,
    publish_validation_batch,
    validation_runtime,
)
from pymo.classification import Classifier
from pymo.config import (
    ConfigError,
    PymoConfig,
    add_config_argument,
    add_show_ignored_argument,
    canonical_container_family,
    ignored_messages,
    load_config,
)
from pymo.duplicates.videos import (
    VideoInspectionError,
    ffmpeg_version,
    ffprobe_version,
    resolve_executable,
)
from pymo.file_safety import FileChangedError, FileState, open_stable_file
from pymo.logging_config import emit as print
from pymo.progress import ProgressMeter, format_bytes

# This identifies the public machine-readable validation report contract.
VALIDATION_REPORT_SCHEMA_VERSION = 2


Severity = Literal["error", "warning", "info"]
MediaKind = Literal["picture", "video"]
DiscoveryDisposition = Literal[
    "candidate",
    "ignored",
    "symlink",
    "unreadable",
    "changed",
    "other",
    "mismatched",
    "reserved",
]


@dataclass(frozen=True)
class MediaCandidate:
    root: Path
    path: Path
    state: FileState
    kind: MediaKind
    extension_kind: MediaKind | None
    detected_kind: str


@dataclass(frozen=True)
class Finding:
    path: Path
    kind: MediaKind
    severity: Severity
    code: str
    description: str


@dataclass(frozen=True)
class ValidationResult:
    candidate: MediaCandidate
    findings: tuple[Finding, ...]
    animated_or_multipage: bool = False
    byte_sha256: str | None = None
    completed_at: str = ""
    reused: bool = False


@dataclass(frozen=True)
class DiscoveryResult:
    candidates: tuple[MediaCandidate, ...]
    ignored: tuple[Path, ...]
    symlink_count: int
    unreadable_count: int
    changed_count: int
    other_count: int
    classifier_warning: str | None
    symlink_paths: tuple[Path, ...]
    unreadable_paths: tuple[Path, ...]
    changed_paths: tuple[Path, ...]
    mismatched_paths: tuple[Path, ...] = ()

    @property
    def mismatched_count(self) -> int:
        return len(self.mismatched_paths)


@dataclass(frozen=True)
class ValidationOptions:
    workers: int
    full: bool
    ffprobe: str | None
    ffmpeg: str | None
    timeout: int
    progress_interval_seconds: int
    show_progress: bool
    hash_content: bool
    container_families: Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class ReportOptions:
    full: bool
    workers: int
    show_files: bool
    show_ignored: bool
    cache_enabled: bool = False
    cache_location: str | None = None
    cache_records_written: int = 0
    cache_issue: str | None = None
    cache_mode: str = "fresh"
    cache_records_reused: int = 0
    fresh_validation_files: int | None = None


def _extension_kind(path: Path, config: PymoConfig) -> MediaKind | None:
    extension = path.suffix.casefold()
    if extension in config.classification.image_extensions:
        return "picture"
    if extension in config.classification.video_extensions:
        return "video"
    return None


def _retain_directories(
    current: Path,
    names: list[str],
    root: Path,
    config: PymoConfig,
) -> tuple[list[str], list[Path], list[Path]]:
    retained: list[str] = []
    ignored: list[Path] = []
    symlinks: list[Path] = []
    for name in sorted(names, key=str.casefold):
        path = current / name
        if path.is_symlink():
            symlinks.append(path)
        elif config.ignores_directory(path, root):
            ignored.append(path)
        else:
            retained.append(name)
    return retained, ignored, symlinks


def _discover_file(
    path: Path,
    root: Path,
    config: PymoConfig,
    classifier: Classifier,
) -> tuple[DiscoveryDisposition, MediaCandidate | None]:
    if path.is_symlink():
        return "symlink", None
    if config.ignores_file(path, root):
        return "ignored", None
    if is_action_log_path(root, path):
        return "reserved", None
    try:
        state = FileState.capture(path)
    except FileChangedError:
        return "unreadable", None
    try:
        with open_stable_file(root, path, state, "media discovery") as descriptor:
            detected_kind, _ = classifier.classify(path, descriptor)
    except FileChangedError:
        return "changed", None
    extension_kind = _extension_kind(path, config)
    if detected_kind in {"picture", "video"}:
        kind: MediaKind = detected_kind  # type: ignore[assignment]
    elif extension_kind is not None:
        # A meaningful non-media content signature outranks a media extension.
        # Validating such a file as media would probe or decode content that is
        # not media and report healthy content as damaged, so it is reported as
        # a naming mismatch instead of being promoted or silently dropped.
        return "mismatched", None
    else:
        return "other", None
    return (
        "candidate",
        MediaCandidate(
            root=root,
            path=path.absolute(),
            state=state,
            kind=kind,
            extension_kind=extension_kind,
            detected_kind=detected_kind,
        ),
    )


def discover_candidates(root: Path, config: PymoConfig) -> DiscoveryResult:
    classifier = Classifier(config.classification)
    candidates: list[MediaCandidate] = []
    ignored: list[Path] = []
    other_count = 0
    symlink_paths: list[Path] = []
    unreadable_paths: list[Path] = []
    changed_paths: list[Path] = []
    mismatched_paths: list[Path] = []

    def record_walk_error(error: OSError) -> None:
        unreadable_paths.append(Path(error.filename) if error.filename else root)

    for current, directory_names, file_names in os.walk(
        root, topdown=True, onerror=record_walk_error
    ):
        current_path = Path(current)
        retained, ignored_directories, symlink_directories = _retain_directories(
            current_path, directory_names, root, config
        )
        directory_names[:] = retained
        ignored.extend(ignored_directories)
        symlink_paths.extend(symlink_directories)

        for name in sorted(file_names, key=str.casefold):
            path = current_path / name
            disposition, candidate = _discover_file(path, root, config, classifier)
            if candidate is not None:
                candidates.append(candidate)
            elif disposition == "symlink":
                symlink_paths.append(path)
            elif disposition == "ignored":
                ignored.append(path)
            elif disposition == "unreadable":
                unreadable_paths.append(path)
            elif disposition == "changed":
                changed_paths.append(path)
            elif disposition == "mismatched":
                mismatched_paths.append(path)
            elif disposition == "other":
                other_count += 1
    return DiscoveryResult(
        candidates=tuple(
            sorted(candidates, key=lambda item: str(item.path).casefold())
        ),
        ignored=tuple(sorted(ignored, key=lambda item: str(item).casefold())),
        symlink_count=len(symlink_paths),
        unreadable_count=len(unreadable_paths),
        changed_count=len(changed_paths),
        other_count=other_count,
        classifier_warning=classifier.warning,
        symlink_paths=tuple(symlink_paths),
        unreadable_paths=tuple(unreadable_paths),
        changed_paths=tuple(changed_paths),
        mismatched_paths=tuple(
            sorted(mismatched_paths, key=lambda item: str(item).casefold())
        ),
    )


def _finding(
    candidate: MediaCandidate,
    severity: Severity,
    code: str,
    description: str,
) -> Finding:
    return Finding(candidate.path, candidate.kind, severity, code, description)


def _changed_finding(candidate: MediaCandidate) -> Finding:
    return _finding(
        candidate,
        "warning",
        "changed_during_validation",
        "file changed while it was being validated",
    )


def _validation_result(
    candidate: MediaCandidate,
    findings: list[Finding],
    *,
    animated_or_multipage: bool = False,
    byte_sha256: str | None = None,
) -> ValidationResult:
    return ValidationResult(
        candidate,
        tuple(findings),
        animated_or_multipage,
        byte_sha256,
        completed_timestamp(),
    )


def _classification_findings(candidate: MediaCandidate) -> list[Finding]:
    findings: list[Finding] = []
    if candidate.state.size == 0:
        findings.append(_finding(candidate, "error", "empty_file", "file is empty"))
    if candidate.extension_kind is None:
        findings.append(
            _finding(
                candidate,
                "warning",
                "unrecognized_media_extension",
                "content appears to be media but the extension is not recognized",
            )
        )
    elif candidate.detected_kind != candidate.extension_kind:
        # A candidate never carries a non-media detected kind: discovery reports
        # that as a `mismatched` entry instead, so this compares two media kinds.
        findings.append(
            _finding(
                candidate,
                "warning",
                "extension_content_mismatch",
                "filename extension and detected content type disagree",
            )
        )
    return findings


def validate_image(
    candidate: MediaCandidate, full: bool, *, hash_content: bool = False
) -> ValidationResult:
    findings = _classification_findings(candidate)
    supported_extensions = Image.registered_extensions()
    animated_or_multipage = False
    byte_sha256: str | None = None
    try:
        with open_stable_file(
            candidate.root, candidate.path, candidate.state, "image validation"
        ) as descriptor:
            if hash_content:
                byte_sha256 = sha256_descriptor(descriptor)
            if candidate.state.size == 0:
                return _validation_result(candidate, findings, byte_sha256=byte_sha256)
            if (
                candidate.extension_kind == "picture"
                and candidate.path.suffix.casefold() not in supported_extensions
                and candidate.detected_kind == "picture"
            ):
                findings.append(
                    _finding(
                        candidate,
                        "warning",
                        "unsupported_image_format",
                        "Pillow has no decoder for this recognized image format",
                    )
                )
                return _validation_result(candidate, findings, byte_sha256=byte_sha256)
            os.lseek(descriptor, 0, os.SEEK_SET)
            with os.fdopen(os.dup(descriptor), "rb") as handle:
                with Image.open(handle) as opened:
                    animated_or_multipage = getattr(opened, "n_frames", 1) > 1
                    expected_format = supported_extensions.get(
                        candidate.path.suffix.casefold()
                    )
                    if (
                        expected_format
                        and opened.format
                        and expected_format != opened.format
                    ):
                        findings.append(
                            _finding(
                                candidate,
                                "warning",
                                "extension_content_mismatch",
                                "image decoder format does not match the extension",
                            )
                        )
                    opened.verify()
            if full:
                os.lseek(descriptor, 0, os.SEEK_SET)
                with os.fdopen(os.dup(descriptor), "rb") as handle:
                    with Image.open(handle) as opened:
                        for frame in ImageSequence.Iterator(opened):
                            frame.load()
    except FileChangedError:
        findings = [_changed_finding(candidate)]
        byte_sha256 = None
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        ValueError,
    ):
        try:
            candidate.state.require_unchanged(candidate.path, "image validation")
        except FileChangedError:
            findings = [_changed_finding(candidate)]
            byte_sha256 = None
        else:
            findings.append(
                _finding(candidate, "error", "invalid_image", "image decode failed")
            )
    return _validation_result(
        candidate,
        findings,
        animated_or_multipage=animated_or_multipage,
        byte_sha256=byte_sha256,
    )


def _probe_video(descriptor: int, ffprobe: str) -> dict[str, Any]:
    os.lseek(descriptor, 0, os.SEEK_SET)
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_streams",
                "-show_format",
                "-show_entries",
                "stream=codec_type,codec_name,width,height,pix_fmt,sample_rate,channels:format=duration,format_name,probe_score",
                "-of",
                "json",
                f"/dev/fd/{descriptor}",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=60,
            pass_fds=(descriptor,),
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        raise VideoInspectionError(f"ffprobe failed: {error}") from error
    if result.returncode != 0:
        raise VideoInspectionError("ffprobe rejected the file")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise VideoInspectionError("ffprobe returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise VideoInspectionError("ffprobe returned a non-object JSON value")
    return payload


def _full_video_decode(descriptor: int, ffmpeg: str, timeout: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-nostdin",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                f"/dev/fd/{descriptor}",
                "-map",
                "0:v?",
                "-map",
                "0:a?",
                "-f",
                "null",
                "-",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            pass_fds=(descriptor,),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise VideoInspectionError(f"FFmpeg validation failed: {error}") from error
    if result.returncode != 0:
        raise VideoInspectionError("FFmpeg could not completely decode the file")


def _partition_streams(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    streams = payload.get("streams")
    if not isinstance(streams, list) or not all(
        isinstance(stream, dict) for stream in streams
    ):
        raise VideoInspectionError("ffprobe returned an invalid stream list")
    typed_streams = [stream for stream in streams if isinstance(stream, dict)]
    videos = [stream for stream in typed_streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in typed_streams if stream.get("codec_type") == "audio"]
    others = [
        stream
        for stream in typed_streams
        if stream.get("codec_type") not in {"video", "audio"}
    ]
    return videos, audios, others


def _has_positive_dimensions(stream: dict[str, Any]) -> bool:
    try:
        return int(str(stream.get("width"))) > 0 and int(str(stream.get("height"))) > 0
    except (TypeError, ValueError):
        return False


def _stream_findings(
    candidate: MediaCandidate,
    videos: list[dict[str, Any]],
    audios: list[dict[str, Any]],
    others: list[dict[str, Any]],
) -> list[Finding]:
    findings: list[Finding] = []
    if not videos:
        findings.append(
            _finding(candidate, "error", "missing_video_stream", "no video stream")
        )
    for stream in videos:
        if not stream.get("codec_name"):
            findings.append(
                _finding(
                    candidate,
                    "warning",
                    "missing_video_codec",
                    "video codec name is missing",
                )
            )
        if not _has_positive_dimensions(stream):
            findings.append(
                _finding(
                    candidate,
                    "error",
                    "invalid_video_dimensions",
                    "video dimensions are missing or invalid",
                )
            )
    if len(videos) > 1:
        findings.append(
            _finding(
                candidate,
                "warning",
                "multiple_video_streams",
                "file contains multiple video streams",
            )
        )
    if len(audios) > 1:
        findings.append(
            _finding(
                candidate,
                "warning",
                "multiple_audio_streams",
                "file contains multiple audio streams",
            )
        )
    if others:
        findings.append(
            _finding(
                candidate,
                "info",
                "additional_streams",
                "file contains subtitle, data, or attachment streams",
            )
        )
    return findings


def _duration_finding(
    candidate: MediaCandidate, payload: dict[str, Any]
) -> Finding | None:
    format_data = payload.get("format")
    duration = format_data.get("duration") if isinstance(format_data, dict) else None
    try:
        numeric_duration = float(str(duration))
        valid_duration = math.isfinite(numeric_duration) and numeric_duration > 0
    except (TypeError, ValueError):
        valid_duration = False
    if valid_duration:
        return None
    return _finding(
        candidate,
        "warning",
        "missing_or_invalid_duration",
        "playback duration is missing or invalid",
    )


def _container_extension_finding(
    candidate: MediaCandidate,
    payload: dict[str, Any],
    container_families: Mapping[str, frozenset[str]],
) -> Finding | None:
    if candidate.kind != "video":
        return None
    format_data = payload.get("format")
    if not isinstance(format_data, dict):
        return None
    probe_score = format_data.get("probe_score")
    format_name = format_data.get("format_name")
    # ffprobe's maximum score is the conservative accusation boundary. Raw or
    # ambiguous streams can select a demuxer at weaker scores, so treating any
    # successful selection as authoritative would create false mismatches.
    if type(probe_score) is not int or probe_score != 100:
        return None
    if not isinstance(format_name, str):
        return None
    observed_family = canonical_container_family(format_name)
    accepted_families = container_families.get(candidate.path.suffix.casefold())
    if (
        observed_family is None
        or accepted_families is None
        or observed_family in accepted_families
    ):
        return None
    return _finding(
        candidate,
        "warning",
        "container_extension_mismatch",
        "video container does not match the filename extension",
    )


def _inspect_video(
    candidate: MediaCandidate,
    descriptor: int,
    ffprobe: str,
    container_families: Mapping[str, frozenset[str]],
) -> tuple[list[Finding], bool]:
    payload = _probe_video(descriptor, ffprobe)
    videos, audios, others = _partition_streams(payload)
    findings = _stream_findings(candidate, videos, audios, others)
    duration_finding = _duration_finding(candidate, payload)
    if duration_finding is not None:
        findings.append(duration_finding)
    container_finding = _container_extension_finding(
        candidate, payload, container_families
    )
    if container_finding is not None:
        findings.append(container_finding)
    return findings, bool(videos)


def validate_video(
    candidate: MediaCandidate,
    ffprobe: str | None,
    ffmpeg: str | None,
    timeout: int,
    *,
    container_families: Mapping[str, frozenset[str]],
    hash_content: bool = False,
) -> ValidationResult:
    findings = _classification_findings(candidate)
    byte_sha256: str | None = None
    if candidate.state.size > 0 and ffprobe is None:
        raise VideoInspectionError("ffprobe is required for non-empty video")
    try:
        with open_stable_file(
            candidate.root, candidate.path, candidate.state, "video validation"
        ) as descriptor:
            if hash_content:
                byte_sha256 = sha256_descriptor(descriptor)
            if candidate.state.size == 0:
                return _validation_result(candidate, findings, byte_sha256=byte_sha256)
            if ffprobe is None:
                raise VideoInspectionError("ffprobe is required for non-empty video")
            probe_findings, has_video = _inspect_video(
                candidate,
                descriptor,
                ffprobe,
                container_families,
            )
            findings.extend(probe_findings)
            if ffmpeg is not None and has_video:
                _full_video_decode(descriptor, ffmpeg, timeout)
    except FileChangedError:
        findings = [_changed_finding(candidate)]
        byte_sha256 = None
    except (OSError, VideoInspectionError):
        try:
            candidate.state.require_unchanged(candidate.path, "video validation")
        except FileChangedError:
            findings = [_changed_finding(candidate)]
            byte_sha256 = None
        else:
            findings.append(
                _finding(
                    candidate,
                    "error",
                    "invalid_video",
                    "video probe or full decode failed",
                )
            )
    return _validation_result(candidate, findings, byte_sha256=byte_sha256)


def validate_candidates(
    candidates: tuple[MediaCandidate, ...],
    options: ValidationOptions,
) -> tuple[ValidationResult, ...]:
    progress = ProgressMeter(
        len(candidates),
        sum(candidate.state.size for candidate in candidates),
        options.progress_interval_seconds,
    )

    def validate_one(candidate: MediaCandidate) -> ValidationResult:
        if candidate.kind == "picture":
            return validate_image(
                candidate, options.full, hash_content=options.hash_content
            )
        return validate_video(
            candidate,
            options.ffprobe,
            options.ffmpeg,
            options.timeout,
            container_families=options.container_families,
            hash_content=options.hash_content,
        )

    results: list[ValidationResult] = []
    Image.init()
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with ThreadPoolExecutor(max_workers=options.workers) as executor:
            for candidate, result in zip(
                candidates, executor.map(validate_one, candidates), strict=True
            ):
                results.append(result)
                message = progress.advance("validated", byte_count=candidate.state.size)
                if options.show_progress and message:
                    print(f"  {message}")
    return tuple(results)


def _validation_evidence_values(
    results: tuple[ValidationResult, ...],
    profile: ValidationProfile,
    ffprobe_release: str | None,
    ffmpeg_release: str | None,
) -> tuple[ValidationEvidenceValue, ...]:
    values: list[ValidationEvidenceValue] = []
    for result in results:
        if result.byte_sha256 is None:
            continue
        candidate = result.candidate
        runtime = _validation_runtime_for_candidate(
            candidate, ffprobe_release, ffmpeg_release
        )
        values.append(
            ValidationEvidenceValue(
                path=candidate.path,
                state=candidate.state,
                byte_sha256=result.byte_sha256,
                kind=candidate.kind,
                profile=profile,
                runtime=runtime,
                completed_at=result.completed_at,
                findings=tuple(
                    ValidationFindingValue(
                        finding.severity, finding.code, finding.description
                    )
                    for finding in result.findings
                ),
                animated_or_multipage=result.animated_or_multipage,
            )
        )
    return tuple(values)


def _validation_runtime_for_candidate(
    candidate: MediaCandidate,
    ffprobe_release: str | None,
    ffmpeg_release: str | None,
) -> str:
    return validation_runtime(
        kind=candidate.kind,
        extension=candidate.path.suffix.casefold(),
        extension_kind=candidate.extension_kind,
        detected_kind=candidate.detected_kind,
        pillow=f"Pillow {__version__}" if candidate.kind == "picture" else None,
        ffprobe=ffprobe_release if candidate.kind == "video" else None,
        ffmpeg=ffmpeg_release if candidate.kind == "video" else None,
    )


def cached_validation_results(
    root: Path,
    database: Path,
    candidates: tuple[MediaCandidate, ...],
    profile: ValidationProfile,
    ffprobe_release: str | None,
    ffmpeg_release: str | None,
) -> dict[Path, ValidationResult]:
    lookups = tuple(
        ValidationLookup(
            path=candidate.path,
            state=candidate.state,
            kind=candidate.kind,
            profile=profile,
            runtime=_validation_runtime_for_candidate(
                candidate, ffprobe_release, ffmpeg_release
            ),
        )
        for candidate in candidates
    )
    cached = load_compatible_validation(root, database, lookups)
    candidates_by_path = {candidate.path: candidate for candidate in candidates}
    results: dict[Path, ValidationResult] = {}
    for path, value in cached.items():
        candidate = candidates_by_path[path]
        try:
            with open_stable_file(
                root, path, candidate.state, "cached validation reuse"
            ):
                pass
        except FileChangedError:
            continue
        results[path] = _cached_validation_result(candidate, value)
    return results


def _cached_validation_result(
    candidate: MediaCandidate, cached: CachedValidationResult
) -> ValidationResult:
    return ValidationResult(
        candidate=candidate,
        findings=tuple(
            Finding(
                path=candidate.path,
                kind=candidate.kind,
                severity=finding.severity,
                code=finding.code,
                description=finding.description,
            )
            for finding in cached.findings
        ),
        animated_or_multipage=cached.animated_or_multipage,
        byte_sha256=cached.byte_sha256,
        completed_at=cached.completed_at,
        reused=True,
    )


def publish_validation_results(
    root: Path,
    database: Path,
    results: tuple[ValidationResult, ...],
    profile: ValidationProfile,
    ffprobe_release: str | None,
    ffmpeg_release: str | None,
    batch_size: int,
) -> tuple[int, str | None]:
    """Publish bounded result batches and retain completed earlier batches."""

    values = _validation_evidence_values(
        results, profile, ffprobe_release, ffmpeg_release
    )
    written = 0
    for start in range(0, len(values), batch_size):
        batch = values[start : start + batch_size]
        try:
            publish_validation_batch(root, database, batch)
        except ValidationCacheError:
            return written, "validation evidence could not be published safely"
        written += len(batch)
    return written, None


def build_report(
    root: Path,
    discovery: DiscoveryResult,
    results: tuple[ValidationResult, ...],
    options: ReportOptions,
) -> dict[str, Any]:
    findings = [finding for result in results for finding in result.findings]
    by_code: dict[tuple[str, str, str], int] = Counter(
        (finding.severity, finding.code, finding.description) for finding in findings
    )
    if discovery.unreadable_count:
        by_code[
            ("error", "unreadable_entry", "entry could not be read safely")
        ] += discovery.unreadable_count
    if discovery.changed_count:
        by_code[
            (
                "warning",
                "changed_during_discovery",
                "file changed during media discovery and was omitted",
            )
        ] += discovery.changed_count
    if discovery.symlink_count:
        by_code[
            ("warning", "symbolic_link_skipped", "symbolic link was not followed")
        ] += discovery.symlink_count
    if discovery.mismatched_count:
        by_code[
            (
                "warning",
                "extension_content_mismatch",
                "media extension has a meaningful non-media content signature",
            )
        ] += discovery.mismatched_count
    if discovery.classifier_warning:
        by_code[
            (
                "warning",
                "classification_fallback",
                "system content classifier was unavailable",
            )
        ] += 1
    error_paths = {finding.path for finding in findings if finding.severity == "error"}
    warning_paths = {
        finding.path for finding in findings if finding.severity == "warning"
    }
    finding_files = (
        [
            {
                "path": finding.path.relative_to(root).as_posix(),
                "kind": finding.kind,
                "severity": finding.severity,
                "code": finding.code,
                "description": finding.description,
            }
            for finding in findings
        ]
        if options.show_files
        else []
    )
    if options.show_files:
        for paths, severity, code, description in (
            (
                discovery.unreadable_paths,
                "error",
                "unreadable_entry",
                "entry could not be read safely",
            ),
            (
                discovery.changed_paths,
                "warning",
                "changed_during_discovery",
                "file changed during media discovery and was omitted",
            ),
            (
                discovery.symlink_paths,
                "warning",
                "symbolic_link_skipped",
                "symbolic link was not followed",
            ),
            (
                discovery.mismatched_paths,
                "warning",
                "extension_content_mismatch",
                "media extension has a meaningful non-media content signature",
            ),
        ):
            finding_files.extend(
                {
                    "path": path.relative_to(root).as_posix(),
                    "kind": "entry",
                    "severity": severity,
                    "code": code,
                    "description": description,
                }
                for path in paths
            )
        finding_files.sort(key=lambda item: (item["path"], item["code"]))
    return {
        "schema_version": VALIDATION_REPORT_SCHEMA_VERSION,
        "profile": "full" if options.full else "standard",
        "workers": options.workers,
        "inventory": {
            "media_files": len(results),
            "media_bytes": sum(result.candidate.state.size for result in results),
            "pictures": sum(result.candidate.kind == "picture" for result in results),
            "videos": sum(result.candidate.kind == "video" for result in results),
            # A file whose media extension carries non-media content is a
            # non-media file; the accompanying warning is what distinguishes it
            # from one that never claimed to be media.
            "other_files": discovery.other_count + discovery.mismatched_count,
            "ignored_entry_points": len(discovery.ignored),
            "symbolic_links_skipped": discovery.symlink_count,
            "unreadable_entries": discovery.unreadable_count,
            "changed_during_discovery": discovery.changed_count,
        },
        "health": {
            "files_with_errors": len(error_paths) + discovery.unreadable_count,
            "files_with_warnings": (
                len(warning_paths - error_paths)
                + discovery.changed_count
                + discovery.symlink_count
                + discovery.mismatched_count
            ),
            "healthy_files": sum(
                not any(
                    finding.severity in {"error", "warning"}
                    for finding in result.findings
                )
                for result in results
            ),
            "animated_or_multipage_images": sum(
                result.animated_or_multipage for result in results
            ),
        },
        "cache": {
            "enabled": options.cache_enabled,
            "location": options.cache_location,
            "records_written": options.cache_records_written,
            "records_reused": options.cache_records_reused,
            "mode": options.cache_mode,
            "fresh_validation_files": (
                len(results)
                if options.fresh_validation_files is None
                else options.fresh_validation_files
            ),
            "fresh_validation_performed": (
                len(results)
                if options.fresh_validation_files is None
                else options.fresh_validation_files
            )
            > 0,
            "issue": options.cache_issue,
        },
        "findings": [
            {
                "severity": severity,
                "code": code,
                "count": count,
                "description": description,
            }
            for (severity, code, description), count in sorted(by_code.items())
        ],
        "finding_files": finding_files,
        "ignored_paths": (
            [path.relative_to(root).as_posix() for path in discovery.ignored]
            if options.show_ignored
            else []
        ),
    }


def print_report(report: dict[str, Any], show_files: bool) -> None:
    inventory = report["inventory"]
    health = report["health"]
    print("Collection validation")
    print(f"Profile: {report['profile']} ({report['workers']} worker(s))")
    print("\nMedia checked:")
    print(
        f"  {inventory['media_files']} file(s), "
        f"{format_bytes(inventory['media_bytes'])}"
    )
    print(f"  Pictures: {inventory['pictures']}")
    print(f"  Videos: {inventory['videos']}")
    print(f"  Symbolic links skipped: {inventory['symbolic_links_skipped']}")
    print(f"  Unreadable entries: {inventory['unreadable_entries']}")
    print(f"  Changed during discovery: {inventory['changed_during_discovery']}")
    print("\nHealth:")
    print(f"  Healthy files: {health['healthy_files']}")
    print(f"  Files with warnings only: {health['files_with_warnings']}")
    print(f"  Files with errors: {health['files_with_errors']}")
    print(
        "  Animated or multi-page images: " f"{health['animated_or_multipage_images']}"
    )
    print("\nFindings:")
    if not report["findings"]:
        print("  None")
    for finding in report["findings"]:
        print(
            f"  {finding['severity'].upper()} {finding['code']}: "
            f"{finding['count']} file(s) - {finding['description']}"
        )
    if show_files and report["finding_files"]:
        print("\nAffected files:")
        for finding in report["finding_files"]:
            print(f"  {finding['path']}: {finding['severity']} " f"{finding['code']}")
    print("\nValidation did not modify media or action history.")
    cache = report["cache"]
    if cache["enabled"]:
        print(
            "Disposable cache evidence: "
            f"{cache['records_written']} validated file record(s) written "
            f"({cache['location']})."
        )
        if cache["issue"]:
            print(f"  WARNING: {cache['issue']}.")
        print(f"  Compatible prior records reused: {cache['records_reused']}.")
        print(f"  Files freshly validated: {cache['fresh_validation_files']}.")
    else:
        print("Disposable cache evidence: disabled; no records read or written.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report media health without changing the collection."
    )
    parser.add_argument("folder", type=Path, help="media-collection root to validate")
    parser.add_argument(
        "--full",
        action="store_true",
        help="fully decode image frames and video/audio streams",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit one machine-readable JSON report instead of terminal text",
    )
    parser.add_argument(
        "--show-files",
        action="store_true",
        help="include collection-relative affected file paths",
    )
    parser.add_argument(
        "--workers",
        type=int,
        help="bounded validation workers (default: configured scan workers)",
    )
    cache_options = parser.add_mutually_exclusive_group()
    cache_options.add_argument(
        "--cache",
        type=Path,
        help=(
            "write fresh validation evidence to this cache file instead of the "
            "collection-local default; its parent must already exist"
        ),
    )
    cache_options.add_argument(
        "--no-cache",
        action="store_true",
        help="perform fresh validation without reading or writing cache state",
    )
    parser.add_argument(
        "--reuse-validation",
        action="store_true",
        help=(
            "reuse exact compatible validation results for unchanged files and "
            "freshly validate every miss"
        ),
    )
    add_config_argument(parser)
    add_show_ignored_argument(parser)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.reuse_validation and args.no_cache:
        print("--reuse-validation cannot be combined with --no-cache", file=sys.stderr)
        return 2
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2
    try:
        config = load_config(root, args.config)
        database = None if args.no_cache else writable_cache_path(root, args.cache)
    except (CachePathError, ConfigError) as error:
        print(f"Cannot use configuration: {error}", file=sys.stderr)
        return 2
    workers = (
        args.workers if args.workers is not None else config.performance.scan_workers
    )
    if not 1 <= workers <= 32:
        print("--workers must be between 1 and 32", file=sys.stderr)
        return 2

    discovery = discover_candidates(root, config)
    if database is not None and discovery.candidates:
        try:
            preflight_validation_cache(database)
        except ValidationCacheError:
            print("Validation cache cannot be used safely.", file=sys.stderr)
            return 1
    videos = [
        item
        for item in discovery.candidates
        if item.kind == "video" and item.state.size > 0
    ]
    ffprobe: str | None = None
    ffmpeg: str | None = None
    ffprobe_release: str | None = None
    ffmpeg_release: str | None = None
    try:
        if videos:
            ffprobe = resolve_executable(None, "ffprobe")
            if args.full:
                ffmpeg = resolve_executable(None, "ffmpeg")
            if database is not None:
                ffprobe_release = ffprobe_version(ffprobe)
                if ffmpeg is not None:
                    ffmpeg_release = ffmpeg_version(ffmpeg)
    except VideoInspectionError as error:
        print(str(error), file=sys.stderr)
        return 2

    profile: ValidationProfile = "full" if args.full else "standard"
    reused_results: dict[Path, ValidationResult] = {}
    if args.reuse_validation and database is not None:
        try:
            reused_results = cached_validation_results(
                root,
                database,
                discovery.candidates,
                profile,
                ffprobe_release,
                ffmpeg_release,
            )
        except ValidationCacheError:
            print("Validation cache cannot be used safely.", file=sys.stderr)
            return 1
    fresh_candidates = tuple(
        candidate
        for candidate in discovery.candidates
        if candidate.path not in reused_results
    )

    if not args.json:
        print(f"Evaluating {len(discovery.candidates)} media file(s).")
        if database is None:
            print("Validation cache disabled: no records read or written.")
        else:
            location = "explicit" if args.cache is not None else "collection-local"
            if args.reuse_validation:
                print(
                    "Compatible validation evidence will be read; fresh misses "
                    f"will be cached ({location})."
                )
            else:
                print(f"Fresh validation evidence will be cached ({location}).")
        if args.reuse_validation:
            print(
                f"Compatible validation reuse: {len(reused_results)} file(s); "
                f"fresh validation required: {len(fresh_candidates)} file(s)."
            )
        for message in ignored_messages(
            list(discovery.ignored), root, args.show_ignored
        ):
            print(message)
    validation_workers = 1 if args.full and videos else workers
    fresh_results = validate_candidates(
        fresh_candidates,
        ValidationOptions(
            workers=validation_workers,
            full=args.full,
            ffprobe=ffprobe,
            ffmpeg=ffmpeg,
            timeout=config.video_duplicates.decode_timeout_seconds,
            progress_interval_seconds=config.performance.progress_interval_seconds,
            show_progress=not args.json,
            hash_content=database is not None,
            container_families=config.validation.container_families,
        ),
    )
    fresh_by_path = {result.candidate.path: result for result in fresh_results}
    results = tuple(
        reused_results.get(candidate.path) or fresh_by_path[candidate.path]
        for candidate in discovery.candidates
    )
    cache_records_written = 0
    cache_issue: str | None = None
    if database is not None:
        cache_records_written, cache_issue = publish_validation_results(
            root,
            database,
            fresh_results,
            profile,
            ffprobe_release,
            ffmpeg_release,
            config.performance.cache_publication_batch_size,
        )
    report = build_report(
        root,
        discovery,
        results,
        ReportOptions(
            full=args.full,
            workers=validation_workers,
            show_files=args.show_files,
            show_ignored=args.show_ignored,
            cache_enabled=database is not None,
            cache_location=(
                None
                if database is None
                else "explicit" if args.cache is not None else "collection-local"
            ),
            cache_records_written=cache_records_written,
            cache_issue=cache_issue,
            cache_mode=("reuse-compatible" if args.reuse_validation else "fresh"),
            cache_records_reused=len(reused_results),
            fresh_validation_files=len(fresh_results),
        ),
    )
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print_report(report, args.show_files)
    return 1 if report["health"]["files_with_errors"] or cache_issue else 0


if __name__ == "__main__":
    raise SystemExit(main())
