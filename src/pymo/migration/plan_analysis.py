"""Fresh media analyses over a virtual namespace, using existing domain policy."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from pymo import validate
from pymo.classification import Classifier
from pymo.duplicates import images, videos
from pymo.duplicates.common import duplicate_layout
from pymo.file_safety import open_stable_file
from pymo.migration.coverage import compare_byte_inventories
from pymo.migration.images import compare_image_content
from pymo.migration.inventory import revalidate_tree
from pymo.migration.outcome import outcome_record, validation_data, verification_data
from pymo.migration.preauthorization import _validation_projection
from pymo.migration.report import build_report
from pymo.migration.simulation import without_duplicate_review_tree
from pymo.migration.verdict import build_preservation_evidence
from pymo.migration.videos import (
    compare_video_content,
    not_needed_video_content,
    video_content_required,
)
from pymo.migration.virtual import PolicyPlanningError, VirtualCollection
from pymo.migration.workflow import CoordinatorOptions
from pymo.video_content import (
    derive_fingerprint,
    ffmpeg_version,
    ffprobe_version,
    resolve_executable,
)


def native_path(value: str | None) -> Path | None:
    return Path(value) if value is not None else None


def validation(view: VirtualCollection, options: CoordinatorOptions) -> dict[str, Any]:
    classifier = Classifier(view.config.classification)
    candidates = []
    mismatched = []
    other = 0
    for entry in view.tree.files:
        kind, _ = view.classify(entry.path, classifier)
        extension_kind = validate._extension_kind(entry.path, view.config)
        if kind not in {"picture", "video"}:
            if extension_kind is not None:
                mismatched.append(entry.path)
            else:
                other += 1
            continue
        candidates.append(
            validate.MediaCandidate(
                view.tree.root,
                entry.path,
                entry.state,
                cast(validate.MediaKind, kind),
                extension_kind,
                kind,
                entry.read_path,
            )
        )
    discovery = validate.DiscoveryResult(
        tuple(candidates),
        view.tree.ignored,
        0,
        0,
        0,
        other,
        classifier.warning,
        (),
        (),
        (),
        tuple(mismatched),
    )
    has_video = any(c.kind == "video" and c.state.size for c in candidates)
    # Guided validation currently selects system native tools, independently of
    # the duplicate/verification native-tool overrides.
    ffprobe = resolve_executable(None, "ffprobe") if has_video else None
    ffmpeg = resolve_executable(None, "ffmpeg") if has_video else None
    results = validate.validate_candidates(
        tuple(candidates),
        validate.ValidationOptions(
            workers=1,
            full=True,
            ffprobe=ffprobe,
            ffmpeg=ffmpeg,
            timeout=view.config.video_duplicates.decode_timeout_seconds,
            progress_interval_seconds=view.config.performance.progress_interval_seconds,
            show_progress=False,
            hash_content=True,
            container_families=view.config.validation.container_families,
        ),
    )
    report = validate.build_report(
        view.tree.root,
        discovery,
        results,
        validate.ReportOptions(True, 1, False, False),
    )
    data = validation_data(report)
    # A complete plan never turns an uninspectable input into future authority.
    if (
        data["errors"]
        or data["unreadable"]
        or data["changed"]
        or any(
            f["code"] in {"unsupported_image_format", "changed_during_validation"}
            for f in data["findings"]
        )
    ):
        raise PolicyPlanningError("validation cannot establish complete media evidence")
    return _validation_projection(
        outcome_record("validate", "validation", "observed", 0, data)
    )


def verification(
    source: VirtualCollection,
    destination: VirtualCollection,
    options: CoordinatorOptions,
    *,
    simulated: bool = False,
) -> dict[str, Any]:
    comparison = destination.tree
    review = None
    if simulated:
        comparison, review = without_duplicate_review_tree(comparison)
    byte = compare_byte_inventories(source.tree, comparison)
    image_extensions = (
        source.config.image_duplicates.extensions
        | destination.config.image_duplicates.extensions
    )
    video_extensions = (
        source.config.classification.video_extensions
        | destination.config.classification.video_extensions
    )
    pixel = compare_image_content(
        source.tree, comparison, image_extensions, 15, show_progress=False
    )
    if video_content_required(source.tree, comparison, video_extensions):
        ffmpeg = resolve_executable(native_path(options.ffmpeg), "ffmpeg")
        ffprobe = resolve_executable(native_path(options.ffprobe), "ffprobe")
        playback = compare_video_content(
            source.tree,
            comparison,
            video_extensions,
            ffmpeg,
            ffprobe,
            ffmpeg_version(ffmpeg),
            ffprobe_version(ffprobe),
            options.decode_timeout
            or destination.config.video_duplicates.decode_timeout_seconds,
            15,
            show_progress=False,
        )
    else:
        playback = not_needed_video_content(comparison, video_extensions)
    preservation = build_preservation_evidence(
        source.tree,
        comparison,
        byte,
        pixel,
        playback,
        revalidate_tree(source.physical, source.config),
        revalidate_tree(destination.physical, destination.config),
        source.config.classification.image_extensions,
        image_extensions,
        simulated=simulated,
    )
    if preservation.verdict != "complete":
        raise PolicyPlanningError("planned preservation is not complete")
    report = build_report(
        source.tree,
        comparison,
        byte,
        pixel,
        playback,
        preservation,
        simulation=review,
        show_files=False,
        show_ignored=False,
    )
    return {"status": 0, **verification_data(report)}


def _duplicate_result(
    kind: str,
    paths: list[Path],
    view: VirtualCollection,
    groups: int,
    copies: int,
    byte_count: int,
    decision: str,
) -> dict[str, Any]:
    return {
        "status": 0,
        "media_kind": kind,
        "scanned_files": len(paths),
        "scanned_bytes": sum(view.entry(p).size for p in paths),
        "groups": groups,
        "extra_copies": copies,
        "duplicate_bytes": byte_count,
        "skipped": 0,
        "cache_issue": False,
        "decision_digest": decision,
    }


def _move_duplicates(
    view: VirtualCollection, pairs: list[tuple[Path, Path]], kind: str
) -> VirtualCollection:
    create = tuple(
        p
        for p in (
            view.layout.dups,
            (
                view.layout.duplicate_pics
                if kind == "pics"
                else view.layout.duplicate_vids
            ),
        )
        if pairs and not view.exists(p)
    )
    return view.move(pairs, create=create)


def _require_duplicate_layout(view: VirtualCollection, kind: str) -> None:
    layout = duplicate_layout(view.tree.root, "picture" if kind == "image" else "video")
    for path in (layout.source, layout.review_root, layout.destination):
        if view.exists(path) and path not in view.tree.directories:
            raise PolicyPlanningError("planned duplicate layout is unsafe")
    if layout.source not in view.tree.directories or any(
        p.parent == layout.source for p in view.tree.directories
    ):
        raise PolicyPlanningError(
            "planned duplicate source contains an unexpected directory"
        )


def image_duplicates(
    view: VirtualCollection,
) -> tuple[dict[str, Any], VirtualCollection]:
    _require_duplicate_layout(view, "image")
    paths = [
        p
        for p in view.paths()
        if p.parent == view.layout.pics
        and p.suffix.lower() in view.config.image_duplicates.extensions
    ]
    records = []
    for path in paths:
        entry = view.entry(path)
        record = images.inspect_image(
            view.tree.root, entry.read_path, state=entry.state
        )
        records.append(replace(record, path=path))
    groups = images.group_image_duplicates(records)
    plan = images.plan_image_moves(
        groups,
        view.layout.duplicate_pics,
        False,
        summary=True,
        exists=view.exists,
    )
    result = _duplicate_result(
        "image",
        paths,
        view,
        len(groups),
        len(plan),
        images._duplicate_bytes(groups),
        images._decision_digest(view.tree.root, plan),
    )
    return result, _move_duplicates(
        view, [(duplicate.path, target) for _, _, duplicate, target in plan], "pics"
    )


def video_duplicates(
    view: VirtualCollection, options: CoordinatorOptions
) -> tuple[dict[str, Any], VirtualCollection]:
    _require_duplicate_layout(view, "video")
    classifier = Classifier(view.config.classification)
    paths = [
        p
        for p in view.paths()
        if p.parent == view.layout.vids and view.classify(p, classifier)[0] == "video"
    ]
    if len(paths) < 2:
        return (
            _duplicate_result(
                "video",
                paths,
                view,
                0,
                0,
                0,
                videos._decision_digest(view.tree.root, []),
            ),
            view,
        )
    ffprobe = resolve_executable(native_path(options.ffprobe), "ffprobe")
    ffmpeg = resolve_executable(native_path(options.ffmpeg), "ffmpeg")
    physical_records = []
    logical = {}
    for path in paths:
        entry = view.entry(path)
        record = videos.inspect_video(
            view.tree.root, entry.read_path, ffprobe, state=entry.state
        )
        physical_records.append(record)
        logical[record.path] = path
    candidates = videos.candidate_video_records(physical_records)
    derived = {}
    for record in candidates:
        if record.byte_sha256 not in derived:
            with open_stable_file(
                view.tree.root, record.path, record.state, "planned video fingerprint"
            ) as fd:
                derived[record.byte_sha256] = derive_fingerprint(
                    fd,
                    record.probe,
                    ffmpeg,
                    options.decode_timeout
                    or view.config.video_duplicates.decode_timeout_seconds,
                    lambda: None,
                )
    physical_groups, skipped = videos.group_video_duplicates(candidates, derived)
    if skipped:
        raise PolicyPlanningError("video evidence changed during planning")
    groups = [
        [replace(record, path=logical[record.path]) for record in group]
        for group in physical_groups
    ]
    groups.sort(key=lambda group: str(min(r.path for r in group)).casefold())
    plan = videos.plan_video_moves(
        groups,
        view.layout.duplicate_vids,
        False,
        summary=True,
        exists=view.exists,
    )
    result = _duplicate_result(
        "video",
        paths,
        view,
        len(groups),
        len(plan),
        videos._duplicate_bytes(groups),
        videos._decision_digest(view.tree.root, plan),
    )
    return result, _move_duplicates(
        view, [(duplicate.path, target) for _, duplicate, target in plan], "vids"
    )
