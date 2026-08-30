"""Ordered stages and child-command construction for guided migration."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class CoordinatorOptions:
    verbose: bool
    quiet: bool
    timestamps: bool
    config: str | None
    show_ignored: bool
    ffmpeg: str | None
    ffprobe: str | None
    decode_timeout: int | None
    workers: int | None
    no_cache: bool

    def as_json(self) -> dict[str, bool | int | str | None]:
        return {
            "verbose": self.verbose,
            "quiet": self.quiet,
            "timestamps": self.timestamps,
            "config": self.config,
            "show_ignored": self.show_ignored,
            "ffmpeg": self.ffmpeg,
            "ffprobe": self.ffprobe,
            "decode_timeout": self.decode_timeout,
            "workers": self.workers,
            "no_cache": self.no_cache,
        }


@dataclass(frozen=True)
class Stage:
    identifier: str
    description: str
    command: str | None
    target: Literal["baseline", "working", "pair", "checkpoint"]
    mode: Literal["read", "preview", "apply", "checkpoint"]


def _stages() -> tuple[Stage, ...]:
    """Return the immutable runbook without module-level policy state."""

    return (
        Stage(
            "baseline-scan", "scan the unchanged baseline", "scan", "baseline", "read"
        ),
        Stage("working-scan", "scan the working collection", "scan", "working", "read"),
        Stage(
            "baseline-validation",
            "fully validate the unchanged baseline from fresh reads",
            "validate",
            "baseline",
            "read",
        ),
        Stage(
            "working-validation",
            "fully validate the working collection from fresh reads",
            "validate",
            "working",
            "read",
        ),
        Stage(
            "initial-verification",
            "prove the initial working copy against the baseline",
            "verify-migration",
            "pair",
            "read",
        ),
        Stage(
            "extension-preview",
            "preview truthful extension corrections",
            "correct-extensions",
            "working",
            "preview",
        ),
        Stage(
            "extension-apply",
            "apply reviewed truthful extension corrections",
            "correct-extensions",
            "working",
            "apply",
        ),
        Stage(
            "extension-verification",
            "freshly verify preservation after extension correction",
            "verify-migration",
            "pair",
            "read",
        ),
        Stage(
            "organize-preview",
            "preview collection organization",
            "organize",
            "working",
            "preview",
        ),
        Stage(
            "organize-apply",
            "apply reviewed collection organization",
            "organize",
            "working",
            "apply",
        ),
        Stage(
            "organize-verification",
            "freshly verify preservation after organization",
            "verify-migration",
            "pair",
            "read",
        ),
        Stage(
            "rename-preview",
            "preview deterministic media names",
            "rename",
            "working",
            "preview",
        ),
        Stage(
            "rename-apply",
            "apply reviewed deterministic media names",
            "rename",
            "working",
            "apply",
        ),
        Stage(
            "rename-verification",
            "freshly verify preservation after deterministic renaming",
            "verify-migration",
            "pair",
            "read",
        ),
        Stage(
            "image-duplicates-preview",
            "preview exact displayed-image duplicate isolation",
            "find-image-duplicates",
            "working",
            "preview",
        ),
        Stage(
            "image-duplicates-apply",
            "apply reviewed exact displayed-image duplicate isolation",
            "find-image-duplicates",
            "working",
            "apply",
        ),
        Stage(
            "image-duplicates-verification",
            "freshly verify preservation after image duplicate isolation",
            "verify-migration",
            "pair",
            "read",
        ),
        Stage(
            "video-duplicates-preview",
            "preview strict decoded-video duplicate isolation",
            "find-video-duplicates",
            "working",
            "preview",
        ),
        Stage(
            "video-duplicates-apply",
            "apply reviewed strict decoded-video duplicate isolation",
            "find-video-duplicates",
            "working",
            "apply",
        ),
        Stage(
            "video-duplicates-verification",
            "freshly verify preservation after video duplicate isolation",
            "verify-migration",
            "pair",
            "read",
        ),
        Stage(
            "without-dups-simulation",
            "simulate preservation without the duplicate review tree",
            "verify-migration",
            "pair",
            "read",
        ),
        Stage(
            "external-quarantine",
            "move the complete dups tree to retained external quarantine",
            None,
            "checkpoint",
            "checkpoint",
        ),
        Stage(
            "final-working-validation",
            "fully validate the final working collection from fresh reads",
            "validate",
            "working",
            "read",
        ),
        Stage(
            "final-verification",
            "perform ordinary fresh final migration verification",
            "verify-migration",
            "pair",
            "read",
        ),
    )


def _global_child_options(options: CoordinatorOptions, log_file: Path) -> list[str]:
    result: list[str] = []
    if options.verbose:
        result.append("--verbose")
    elif options.quiet:
        result.append("--quiet")
    result.append("--timestamps" if options.timestamps else "--no-timestamps")
    result.extend(("--log-file", str(log_file)))
    if options.config is not None:
        result.extend(("--config", options.config))
    if options.show_ignored:
        result.append("--show-ignored")
    return result


def _native_options(options: CoordinatorOptions, *, ffmpeg: bool) -> list[str]:
    result: list[str] = []
    if ffmpeg and options.ffmpeg is not None:
        result.extend(("--ffmpeg", options.ffmpeg))
    if options.ffprobe is not None:
        result.extend(("--ffprobe", options.ffprobe))
    if ffmpeg and options.decode_timeout is not None:
        result.extend(("--decode-timeout", str(options.decode_timeout)))
    return result


def child_command(
    baseline: Path,
    working: Path,
    options: CoordinatorOptions,
    stage: Stage,
    log_file: Path,
) -> list[str]:
    if stage.command is None:
        raise ValueError("checkpoint does not have a child command")
    command = [sys.executable, "-m", "pymo"]
    command.extend(_global_child_options(options, log_file))
    command.append(stage.command)
    if stage.target == "baseline":
        command.append(str(baseline))
    elif stage.target == "working":
        command.append(str(working))
    else:
        command.extend((str(baseline), str(working)))

    if stage.command == "scan" and options.workers is not None:
        command.extend(("--workers", str(options.workers)))
    elif stage.command == "validate":
        command.append("--full")
        if stage.target == "baseline" or options.no_cache:
            command.append("--no-cache")
        if options.workers is not None:
            command.extend(("--workers", str(options.workers)))
    elif stage.command == "correct-extensions":
        command.extend(_native_options(options, ffmpeg=False))
    elif stage.command == "find-image-duplicates" and options.no_cache:
        command.append("--no-cache")
    elif stage.command == "find-video-duplicates":
        if options.no_cache:
            command.append("--no-cache")
        command.extend(_native_options(options, ffmpeg=True))
    elif stage.command == "verify-migration":
        command.extend(_native_options(options, ffmpeg=True))
        if stage.identifier == "without-dups-simulation":
            command.append("--simulate-without-dups")
    if stage.mode == "apply":
        command.append("--apply")
    return command
