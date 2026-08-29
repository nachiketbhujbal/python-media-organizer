#!/usr/bin/env python3
"""Correct provably false media extensions without changing file bytes."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pymo.action_log import (
    Action,
    ActionConflict,
    ActionLog,
    ActionLogError,
    NoUndoableRun,
    ToolId,
)
from pymo.cache.hashes import sha256_descriptor
from pymo.classification import Classifier
from pymo.config import (
    ConfigError,
    PymoConfig,
    add_config_argument,
    add_show_ignored_argument,
    ignored_messages,
    load_config,
)
from pymo.discovery import DiscoveryError
from pymo.duplicates.videos import VideoInspectionError, resolve_executable
from pymo.extension_truth import (
    ExtensionEvidenceError,
    inspect_image_format,
    inspect_video_container,
)
from pymo.file_safety import FileChangedError, FileState, open_stable_file
from pymo.logging_config import emit as print
from pymo.organize import available_target, discover_files, path_key
from pymo.progress import ProgressMeter


class CorrectionAnalysisError(RuntimeError):
    """A complete correction plan cannot be established safely."""


@dataclass(frozen=True)
class CorrectionRecord:
    source: Path
    target: Path
    kind: str
    state: FileState
    byte_sha256: str


@dataclass(frozen=True)
class CorrectionAnalysis:
    plan: tuple[CorrectionRecord, ...]
    already_truthful: int
    unsupported_or_ambiguous: int
    uninspectable: int
    skipped_links: tuple[Path, ...]
    ignored: tuple[Path, ...]
    classifier_warning: str | None


def _policy_for_image(
    descriptor: int, formats: Mapping[str, tuple[str, ...]]
) -> tuple[str, ...] | None:
    return formats.get(inspect_image_format(descriptor))


def _policy_for_video(
    descriptor: int,
    ffprobe: str,
    families: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...] | None:
    evidence = inspect_video_container(descriptor, ffprobe)
    return families.get(evidence.family)


def analyze_corrections(
    root: Path,
    config: PymoConfig,
    ffprobe_path: Path | None = None,
) -> CorrectionAnalysis:
    """Discover and inspect a complete collection without mutating it."""

    paths, skipped_links, ignored = discover_files(root, config)
    classifier = Classifier(config.classification)
    occupied = {path_key(path) for path in paths}
    plan: list[CorrectionRecord] = []
    already_truthful = 0
    unsupported_or_ambiguous = 0
    uninspectable = 0
    ffprobe: str | None = None
    progress = ProgressMeter(
        len(paths), None, config.performance.progress_interval_seconds
    )

    print(f"Inspecting extension truth for {len(paths)} file(s) in {root}")
    for path in paths:
        try:
            state = FileState.capture(path)
            with open_stable_file(
                root, path, state, "extension correction"
            ) as descriptor:
                kind, _ = classifier.classify(path, descriptor)
                accepted: tuple[str, ...] | None = None
                inspection_failed = False
                try:
                    if (
                        kind in {"picture", "video"}
                        and path.suffix.casefold()
                        in config.extension_correction.protected_custom_extensions
                    ):
                        pass
                    elif kind == "picture":
                        accepted = _policy_for_image(
                            descriptor, config.extension_correction.image_formats
                        )
                    elif kind == "video":
                        if ffprobe is None:
                            ffprobe = resolve_executable(ffprobe_path, "ffprobe")
                        accepted = _policy_for_video(
                            descriptor,
                            ffprobe,
                            config.extension_correction.video_families,
                        )
                except ExtensionEvidenceError:
                    uninspectable += 1
                    inspection_failed = True
                if kind in {"picture", "video"}:
                    if inspection_failed:
                        pass
                    elif accepted is None:
                        unsupported_or_ambiguous += 1
                    elif path.suffix.casefold() in accepted:
                        already_truthful += 1
                    else:
                        target = available_target(
                            path.with_suffix(accepted[0]), occupied
                        )
                        digest = sha256_descriptor(descriptor)
                        plan.append(
                            CorrectionRecord(
                                source=path,
                                target=target,
                                kind=kind,
                                state=state,
                                byte_sha256=digest,
                            )
                        )
        except FileChangedError as error:
            raise CorrectionAnalysisError(
                "a file changed while extension truth was inspected"
            ) from error
        progress_message = progress.advance("inspected")
        if progress_message:
            print(f"  {progress_message}")

    return CorrectionAnalysis(
        plan=tuple(plan),
        already_truthful=already_truthful,
        unsupported_or_ambiguous=unsupported_or_ambiguous,
        uninspectable=uninspectable,
        skipped_links=tuple(skipped_links),
        ignored=tuple(ignored),
        classifier_warning=classifier.warning,
    )


def describe_action(root: Path, action: Action, apply: bool) -> None:
    assert action.before and action.after
    verb = "correct extension" if apply else "would correct extension"
    print(f"\n{verb}: {root / action.before}\n  to: {root / action.after}")


def undo_corrections(root: Path, apply: bool) -> int:
    log = ActionLog(root)
    try:
        plan = log.plan_undo(ToolId.CORRECT_EXTENSIONS)
    except NoUndoableRun as error:
        print(str(error), file=sys.stderr)
        return 2
    except (ActionConflict, ActionLogError, OSError) as error:
        print(f"Cannot safely undo extension correction: {error}", file=sys.stderr)
        return 1

    print(f"Using action log: {log.path}")
    print(f"Extension-correction run: {plan.target.run_id}")
    for action in plan.actions:
        describe_action(root, action, apply)
    if not apply:
        print(f"\nWould reverse {len(plan.actions)} extension correction(s).")
        if plan.actions:
            print("Dry run only. Add --apply after reviewing this list.")
        return 0

    try:
        result = log.apply_undo(ToolId.CORRECT_EXTENSIONS)
    except (ActionConflict, ActionLogError, OSError) as error:
        print(f"Extension-correction undo failed safely: {error}", file=sys.stderr)
        return 1
    print(f"\nReversed {result.action_count} extension correction(s).")
    print("Verification passed: every recorded extension correction was reversed.")
    return 0


def _actions(root: Path, plan: tuple[CorrectionRecord, ...]) -> list[Action]:
    return [
        Action.for_evidenced_file(
            root,
            record.source,
            record.target,
            "RENAME",
            record.state,
            record.byte_sha256,
        )
        for record in plan
    ]


def apply_correction_plan(root: Path, plan: tuple[CorrectionRecord, ...]) -> Path:
    actions = _actions(root, plan)
    log = ActionLog(root)
    with log.transaction(ToolId.CORRECT_EXTENSIONS) as transaction:
        for action in actions:
            transaction.perform(action)
        transaction.commit()
    return log.path


def verify_correction_plan(
    root: Path,
    plan: tuple[CorrectionRecord, ...],
) -> tuple[CorrectionRecord, ...]:
    failures: list[CorrectionRecord] = []
    for record in plan:
        if os.path.lexists(record.source) or record.target.is_symlink():
            failures.append(record)
            continue
        try:
            current = FileState.capture(record.target)
            if (
                current.device != record.state.device
                or current.inode != record.state.inode
                or current.size != record.state.size
            ):
                failures.append(record)
                continue
            with open_stable_file(
                root, record.target, current, "extension-correction verification"
            ) as descriptor:
                if sha256_descriptor(descriptor) != record.byte_sha256:
                    failures.append(record)
        except FileChangedError:
            failures.append(record)
    return tuple(failures)


def report_evidence_counts(analysis: CorrectionAnalysis) -> None:
    print(f"Already truthful: {analysis.already_truthful} media file(s).")
    print(
        "Unsupported or ambiguous extension evidence: "
        f"{analysis.unsupported_or_ambiguous} media file(s)."
    )
    if analysis.uninspectable:
        print(
            "Media that could not be inspected conclusively: "
            f"{analysis.uninspectable} file(s)."
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Correct confidently identified false media extensions."
    )
    parser.add_argument(
        "folder", type=Path, help="collection directory whose extensions to check"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform corrections (without this option, the command is a dry run)",
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help=(
            "reverse the newest active extension-correction run; this is also "
            "a dry run unless --apply is supplied"
        ),
    )
    parser.add_argument("--ffprobe", type=Path, help="explicit ffprobe executable path")
    add_config_argument(parser)
    add_show_ignored_argument(parser)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2
    if args.undo:
        return undo_corrections(root, args.apply)

    try:
        config = load_config(root, args.config)
    except ConfigError as error:
        print(f"Cannot use configuration: {error}", file=sys.stderr)
        return 2
    try:
        analysis = analyze_corrections(root, config, args.ffprobe)
    except VideoInspectionError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (CorrectionAnalysisError, DiscoveryError, OSError) as error:
        print(f"Extension correction cannot safely continue: {error}", file=sys.stderr)
        return 1

    if analysis.classifier_warning:
        print(f"Warning: {analysis.classifier_warning}")
    for record in analysis.plan:
        print(
            f"\n{record.kind.upper()}\n"
            f"  {'correct extension' if args.apply else 'would correct extension'}: "
            f"{record.source}\n"
            f"  to: {record.target}"
        )
    if analysis.skipped_links:
        print(f"\nSkipped {len(analysis.skipped_links)} symbolic link(s):")
        for path in analysis.skipped_links:
            print(f"  {path}")
    for number, message in enumerate(
        ignored_messages(list(analysis.ignored), root, args.show_ignored)
    ):
        print(f"\n{message}" if number == 0 else message)

    if not args.apply:
        print(f"\nWould correct {len(analysis.plan)} media extension(s).")
        report_evidence_counts(analysis)
        if analysis.plan:
            print("Dry run only. Add --apply after reviewing this list.")
        return 0

    if not analysis.plan:
        print("\nCorrected 0 media extension(s).")
        report_evidence_counts(analysis)
        return 0

    try:
        log_path = apply_correction_plan(root, analysis.plan)
    except (ActionConflict, ActionLogError, OSError) as error:
        print(f"\nExtension correction stopped safely: {error}", file=sys.stderr)
        print(
            "Any completed corrections remain recorded and can be inspected "
            "with --undo.",
            file=sys.stderr,
        )
        return 1

    failures = verify_correction_plan(root, analysis.plan)
    print(f"\nCorrected {len(analysis.plan)} media extension(s).")
    report_evidence_counts(analysis)
    print(f"Action log: {log_path}")
    if failures:
        print("\nExtension-correction verification needs attention:")
        for record in failures:
            print(f"  {record.source} -> {record.target}")
        return 1
    print("Verification passed: every planned extension correction was completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
