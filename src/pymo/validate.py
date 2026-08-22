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
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageSequence, UnidentifiedImageError

from pymo.action_log import is_action_log_path
from pymo.config import (
    ConfigError,
    PymoConfig,
    add_config_argument,
    add_show_ignored_argument,
    ignored_messages,
    load_config,
)
from pymo.duplicates.videos import VideoInspectionError, resolve_executable
from pymo.file_safety import FileChangedError, FileState
from pymo.logging_config import emit as print
from pymo.organize import Classifier
from pymo.progress import ProgressMeter, format_bytes

# This identifies the public machine-readable validation report contract.
VALIDATION_REPORT_SCHEMA_VERSION = 1


Severity = Literal["error", "warning", "info"]
MediaKind = Literal["picture", "video"]


@dataclass(frozen=True)
class MediaCandidate:
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


def _extension_kind(path: Path, config: PymoConfig) -> MediaKind | None:
    extension = path.suffix.casefold()
    if extension in config.classification.image_extensions:
        return "picture"
    if extension in config.classification.video_extensions:
        return "video"
    return None


def discover_candidates(root: Path, config: PymoConfig) -> DiscoveryResult:
    classifier = Classifier(config.classification)
    candidates: list[MediaCandidate] = []
    ignored: list[Path] = []
    symlink_count = 0
    unreadable_count = 0
    changed_count = 0
    other_count = 0
    symlink_paths: list[Path] = []
    unreadable_paths: list[Path] = []
    changed_paths: list[Path] = []

    def record_walk_error(error: OSError) -> None:
        nonlocal unreadable_count
        unreadable_count += 1
        unreadable_paths.append(Path(error.filename) if error.filename else root)

    for current, directory_names, file_names in os.walk(
        root, topdown=True, onerror=record_walk_error
    ):
        current_path = Path(current)
        retained: list[str] = []
        for name in sorted(directory_names, key=str.casefold):
            path = current_path / name
            if path.is_symlink():
                symlink_count += 1
                symlink_paths.append(path)
            elif config.ignores_directory(path, root):
                ignored.append(path)
            else:
                retained.append(name)
        directory_names[:] = retained

        for name in sorted(file_names, key=str.casefold):
            path = current_path / name
            if path.is_symlink():
                symlink_count += 1
                symlink_paths.append(path)
                continue
            if config.ignores_file(path, root):
                ignored.append(path)
                continue
            if is_action_log_path(root, path):
                continue
            try:
                state = FileState.capture(path)
            except FileChangedError:
                unreadable_count += 1
                unreadable_paths.append(path)
                continue
            detected_kind, _ = classifier.classify(path)
            try:
                state.require_unchanged(path, "media discovery")
            except FileChangedError:
                changed_count += 1
                changed_paths.append(path)
                continue
            extension_kind = _extension_kind(path, config)
            if detected_kind in {"picture", "video"}:
                kind: MediaKind = detected_kind  # type: ignore[assignment]
            elif extension_kind is not None:
                kind = extension_kind
            else:
                other_count += 1
                continue
            candidates.append(
                MediaCandidate(
                    path=path.absolute(),
                    state=state,
                    kind=kind,
                    extension_kind=extension_kind,
                    detected_kind=detected_kind,
                )
            )
    return DiscoveryResult(
        candidates=tuple(
            sorted(candidates, key=lambda item: str(item.path).casefold())
        ),
        ignored=tuple(sorted(ignored, key=lambda item: str(item).casefold())),
        symlink_count=symlink_count,
        unreadable_count=unreadable_count,
        changed_count=changed_count,
        other_count=other_count,
        classifier_warning=classifier.warning,
        symlink_paths=tuple(symlink_paths),
        unreadable_paths=tuple(unreadable_paths),
        changed_paths=tuple(changed_paths),
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
    elif candidate.detected_kind not in {candidate.extension_kind, "other"}:
        findings.append(
            _finding(
                candidate,
                "warning",
                "extension_content_mismatch",
                "filename extension and detected content type disagree",
            )
        )
    elif candidate.detected_kind == "other":
        findings.append(
            _finding(
                candidate,
                "warning",
                "extension_content_mismatch",
                "media extension has a meaningful non-media content signature",
            )
        )
    return findings


def validate_image(candidate: MediaCandidate, full: bool) -> ValidationResult:
    findings = _classification_findings(candidate)
    if candidate.state.size == 0:
        return ValidationResult(candidate, tuple(findings))
    supported_extensions = Image.registered_extensions()
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
        return ValidationResult(candidate, tuple(findings))

    animated_or_multipage = False
    try:
        candidate.state.require_unchanged(candidate.path, "image validation")
        with Image.open(candidate.path) as opened:
            animated_or_multipage = getattr(opened, "n_frames", 1) > 1
            expected_format = supported_extensions.get(candidate.path.suffix.casefold())
            if expected_format and opened.format and expected_format != opened.format:
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
            with Image.open(candidate.path) as opened:
                for frame in ImageSequence.Iterator(opened):
                    frame.load()
        candidate.state.require_unchanged(candidate.path, "image validation")
    except FileChangedError:
        findings = [_changed_finding(candidate)]
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
        else:
            findings.append(
                _finding(candidate, "error", "invalid_image", "image decode failed")
            )
    return ValidationResult(candidate, tuple(findings), animated_or_multipage)


def _probe_video(path: Path, ffprobe: str) -> dict[str, Any]:
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
                "stream=codec_type,codec_name,width,height,pix_fmt,sample_rate,channels:format=duration,format_name",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=60,
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


def _full_video_decode(path: Path, ffmpeg: str, timeout: int) -> None:
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
                str(path),
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
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise VideoInspectionError(f"FFmpeg validation failed: {error}") from error
    if result.returncode != 0:
        raise VideoInspectionError("FFmpeg could not completely decode the file")


def validate_video(
    candidate: MediaCandidate,
    ffprobe: str | None,
    ffmpeg: str | None,
    timeout: int,
) -> ValidationResult:
    findings = _classification_findings(candidate)
    if candidate.state.size == 0:
        return ValidationResult(candidate, tuple(findings))
    if ffprobe is None:
        raise VideoInspectionError("ffprobe is required for non-empty video")
    try:
        candidate.state.require_unchanged(candidate.path, "video validation")
        payload = _probe_video(candidate.path, ffprobe)
        streams = payload.get("streams")
        if not isinstance(streams, list) or not all(
            isinstance(stream, dict) for stream in streams
        ):
            raise VideoInspectionError("ffprobe returned an invalid stream list")
        videos = [stream for stream in streams if stream.get("codec_type") == "video"]
        audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
        others = [
            stream
            for stream in streams
            if stream.get("codec_type") not in {"video", "audio"}
        ]
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
            try:
                dimensions_valid = (
                    int(str(stream.get("width"))) > 0
                    and int(str(stream.get("height"))) > 0
                )
            except (TypeError, ValueError):
                dimensions_valid = False
            if not dimensions_valid:
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
        format_data = payload.get("format")
        duration = (
            format_data.get("duration") if isinstance(format_data, dict) else None
        )
        try:
            numeric_duration = float(str(duration))
            valid_duration = math.isfinite(numeric_duration) and numeric_duration > 0
        except (TypeError, ValueError):
            valid_duration = False
        if not valid_duration:
            findings.append(
                _finding(
                    candidate,
                    "warning",
                    "missing_or_invalid_duration",
                    "playback duration is missing or invalid",
                )
            )
        if ffmpeg is not None and videos:
            _full_video_decode(candidate.path, ffmpeg, timeout)
        candidate.state.require_unchanged(candidate.path, "video validation")
    except FileChangedError:
        findings = [_changed_finding(candidate)]
    except VideoInspectionError:
        try:
            candidate.state.require_unchanged(candidate.path, "video validation")
        except FileChangedError:
            findings = [_changed_finding(candidate)]
        else:
            findings.append(
                _finding(
                    candidate,
                    "error",
                    "invalid_video",
                    "video probe or full decode failed",
                )
            )
    return ValidationResult(candidate, tuple(findings))


def validate_candidates(
    candidates: tuple[MediaCandidate, ...],
    workers: int,
    full: bool,
    ffprobe: str | None,
    ffmpeg: str | None,
    timeout: int,
    progress_interval_seconds: int,
    show_progress: bool,
) -> tuple[ValidationResult, ...]:
    progress = ProgressMeter(
        len(candidates),
        sum(candidate.state.size for candidate in candidates),
        progress_interval_seconds,
    )

    def validate_one(candidate: MediaCandidate) -> ValidationResult:
        if candidate.kind == "picture":
            return validate_image(candidate, full)
        return validate_video(candidate, ffprobe, ffmpeg, timeout)

    results: list[ValidationResult] = []
    Image.init()
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for candidate, result in zip(
                candidates, executor.map(validate_one, candidates), strict=True
            ):
                results.append(result)
                message = progress.advance("validated", byte_count=candidate.state.size)
                if show_progress and message:
                    print(f"  {message}")
    return tuple(results)


def build_report(
    root: Path,
    discovery: DiscoveryResult,
    results: tuple[ValidationResult, ...],
    full: bool,
    workers: int,
    show_files: bool,
    show_ignored: bool,
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
        if show_files
        else []
    )
    if show_files:
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
        "profile": "full" if full else "standard",
        "workers": workers,
        "inventory": {
            "media_files": len(results),
            "media_bytes": sum(result.candidate.state.size for result in results),
            "pictures": sum(result.candidate.kind == "picture" for result in results),
            "videos": sum(result.candidate.kind == "video" for result in results),
            "other_files": discovery.other_count,
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
            if show_ignored
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
    print("\nValidation is report-only; no files were changed.")


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
    add_config_argument(parser)
    add_show_ignored_argument(parser)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2
    try:
        config = load_config(root, args.config)
    except ConfigError as error:
        print(f"Cannot use configuration: {error}", file=sys.stderr)
        return 2
    workers = (
        args.workers if args.workers is not None else config.performance.scan_workers
    )
    if not 1 <= workers <= 32:
        print("--workers must be between 1 and 32", file=sys.stderr)
        return 2

    discovery = discover_candidates(root, config)
    videos = [
        item
        for item in discovery.candidates
        if item.kind == "video" and item.state.size > 0
    ]
    ffprobe: str | None = None
    ffmpeg: str | None = None
    try:
        if videos:
            ffprobe = resolve_executable(None, "ffprobe")
            if args.full:
                ffmpeg = resolve_executable(None, "ffmpeg")
    except VideoInspectionError as error:
        print(str(error), file=sys.stderr)
        return 2

    if not args.json:
        print(f"Validating {len(discovery.candidates)} media file(s).")
        for message in ignored_messages(
            list(discovery.ignored), root, args.show_ignored
        ):
            print(message)
    validation_workers = 1 if args.full and videos else workers
    results = validate_candidates(
        discovery.candidates,
        validation_workers,
        args.full,
        ffprobe,
        ffmpeg,
        config.video_duplicates.decode_timeout_seconds,
        config.performance.progress_interval_seconds,
        not args.json,
    )
    report = build_report(
        root,
        discovery,
        results,
        args.full,
        validation_workers,
        args.show_files,
        args.show_ignored,
    )
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print_report(report, args.show_files)
    return 1 if report["health"]["files_with_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
