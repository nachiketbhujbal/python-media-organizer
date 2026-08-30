"""Guide one baseline and working collection through the migration runbook."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

from pymo import __version__
from pymo.logging_config import emit as print
from pymo.migration.coordinator_state import (
    Attempt,
    MigrationCoordinatorError,
    MigrationState,
    _load_state,
    _now,
    _prepare_log_dir,
    _state_lock,
    _state_path,
    _updated_state,
    _write_state,
)
from pymo.migration.workflow import (
    CoordinatorOptions,
    Stage,
    _stages,
    child_command,
)


def _disjoint(first: Path, second: Path) -> bool:
    return (
        first != second and first not in second.parents and second not in first.parents
    )


def _validate_roots(baseline: Path, working: Path) -> None:
    if not baseline.is_dir():
        raise MigrationCoordinatorError("baseline is not a readable directory")
    if not working.is_dir():
        raise MigrationCoordinatorError(
            "working collection is not a readable directory"
        )
    if not _disjoint(baseline, working):
        raise MigrationCoordinatorError(
            "baseline and working collection must be distinct, non-nested directories"
        )


def _option_overrides(args: argparse.Namespace) -> dict[str, object]:
    names = (
        "verbose",
        "quiet",
        "timestamps",
        "config",
        "show_ignored",
        "ffmpeg",
        "ffprobe",
        "decode_timeout",
        "workers",
        "no_cache",
    )
    overrides: dict[str, object] = {}
    for name in names:
        value = getattr(args, name)
        if value is not None:
            overrides[name] = (
                str(value.expanduser().resolve()) if isinstance(value, Path) else value
            )
    return overrides


def _initial_options(args: argparse.Namespace) -> CoordinatorOptions:
    values: dict[str, object] = {
        "verbose": False,
        "quiet": False,
        "timestamps": True,
        "config": None,
        "show_ignored": False,
        "ffmpeg": None,
        "ffprobe": None,
        "decode_timeout": None,
        "workers": None,
        "no_cache": False,
    }
    values.update(_option_overrides(args))
    return CoordinatorOptions(**values)  # type: ignore[arg-type]


def _require_matching_options(args: argparse.Namespace, state: MigrationState) -> None:
    current = state.options.as_json()
    for name, value in _option_overrides(args).items():
        if current[name] != value:
            raise MigrationCoordinatorError(
                f"{name.replace('_', '-')} differs from the recorded coordinator option"
            )


def _new_log_file(log_dir: Path, state: MigrationState, stage: Stage) -> Path:
    number = len(state.attempts) + 1
    path = log_dir / f"{number:03d}-{stage.identifier}-{uuid.uuid4().hex[:8]}.log"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise MigrationCoordinatorError(
            "private stage log could not be created"
        ) from error
    os.close(descriptor)
    return path


def _print_plan(next_stage: int = 0) -> None:
    stages = _stages()
    print("Guided single-collection migration plan:")
    for index, stage in enumerate(stages):
        marker = (
            "next"
            if index == next_stage
            else "done" if index < next_stage else "pending"
        )
        requirement = " (requires --apply)" if stage.mode == "apply" else ""
        print(
            f"  {index + 1:02d}. [{marker}] {stage.identifier}: {stage.description}{requirement}"
        )


def _print_status(state: MigrationState) -> None:
    if state.next_stage == len(_stages()):
        print("Migration sequence complete: final observed verification succeeded.")
        print(
            "The result is eligible for human sign-off only; retain source, baseline, and quarantine."
        )
        if any(attempt.action == "acknowledge-status" for attempt in state.attempts):
            print(
                "Reviewed validation findings were explicitly acknowledged and remain recorded."
            )
        return
    stage = _stages()[state.next_stage]
    print(f"Migration progress: {state.next_stage}/{len(_stages())} stage(s) complete.")
    print(f"Next checkpoint: {stage.identifier} — {stage.description}.")
    if stage.mode == "apply":
        print("Run this reviewed mutation with --run-next --apply.")
    elif stage.mode == "checkpoint":
        print(
            "Move or retain the complete dups tree externally, then use --confirm-quarantine."
        )
    else:
        print("Run only this stage with --run-next.")


def _run_next(
    log_dir: Path, state_path: Path, state: MigrationState, apply: bool
) -> int:
    if state.next_stage == len(_stages()):
        print("Migration sequence is already complete.")
        return 0
    stage = _stages()[state.next_stage]
    if stage.mode == "checkpoint":
        print(
            "External quarantine is a human checkpoint; use --confirm-quarantine.",
            file=sys.stderr,
        )
        return 2
    if stage.mode == "apply" and not apply:
        print(
            "This stage mutates the working collection; add --apply after reviewing its preview.",
            file=sys.stderr,
        )
        return 2
    if stage.mode != "apply" and apply:
        print("--apply is valid only at a pending apply checkpoint.", file=sys.stderr)
        return 2

    log_file = _new_log_file(log_dir, state, stage)
    command = child_command(
        state.baseline, state.working, state.options, stage, log_file
    )
    print(f"Running one migration stage: {stage.identifier}.")
    print(f"Private stage log: {log_file}")
    try:
        completed = subprocess.run(command, check=False)
        status = completed.returncode
        if status < 0:
            status = 128 + abs(status)
    except OSError:
        status = 127
    attempt = Attempt(stage.identifier, "run", status, _now(), log_file.name, apply)
    _write_state(state_path, _updated_state(state, attempt, advance=status == 0))
    if status == 0:
        print(f"Stage complete: {stage.identifier}.")
    else:
        print(
            f"Stage stopped with exit status {status}: {stage.identifier}.",
            file=sys.stderr,
        )
        if (
            stage.identifier
            in {
                "baseline-validation",
                "working-validation",
                "final-working-validation",
            }
            and status == 1
        ):
            print(
                "Review the findings; --accept-status is the explicit acknowledgement boundary."
            )
    return status


def _accept_status(state_path: Path, state: MigrationState) -> int:
    if state.next_stage == len(_stages()) or not state.attempts:
        print("There is no pending validation status to acknowledge.", file=sys.stderr)
        return 2
    stage = _stages()[state.next_stage]
    previous = state.attempts[-1]
    if (
        stage.identifier
        not in {"baseline-validation", "working-validation", "final-working-validation"}
        or previous.stage != stage.identifier
        or previous.action != "run"
        or previous.exit_status != 1
    ):
        print(
            "Only the latest status-1 validation findings can be acknowledged.",
            file=sys.stderr,
        )
        return 2
    attempt = Attempt(stage.identifier, "acknowledge-status", 1, _now(), None, False)
    _write_state(state_path, _updated_state(state, attempt, advance=True))
    print(
        f"Acknowledged reviewed validation findings for {stage.identifier}; the original status 1 remains recorded."
    )
    return 0


def _confirm_quarantine(state_path: Path, state: MigrationState) -> int:
    if state.next_stage == len(_stages()):
        print("There is no pending external-quarantine checkpoint.", file=sys.stderr)
        return 2
    stage = _stages()[state.next_stage]
    if stage.identifier != "external-quarantine":
        print(
            "External quarantine cannot be confirmed before its checkpoint.",
            file=sys.stderr,
        )
        return 2
    if os.path.lexists(state.working / "dups"):
        print(
            "The working collection still contains its dups path; pymo will not move or delete it.",
            file=sys.stderr,
        )
        return 1
    attempt = Attempt(stage.identifier, "confirm-quarantine", 0, _now(), None, False)
    _write_state(state_path, _updated_state(state, attempt, advance=True))
    print(
        "External quarantine checkpoint confirmed; the working collection has no dups path."
    )
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guide one baseline and working collection through the production runbook."
    )
    parser.add_argument("baseline", type=Path, help="unchanged baseline collection")
    parser.add_argument("working", type=Path, help="working collection to transform")
    parser.add_argument(
        "--log-dir",
        type=Path,
        help="explicit private directory for restart state and per-stage logs",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--start", action="store_true", help="initialize restartable workflow state"
    )
    actions.add_argument(
        "--run-next", action="store_true", help="run exactly the pending child stage"
    )
    actions.add_argument(
        "--accept-status",
        action="store_true",
        help="acknowledge the latest reviewed validation status 1",
    )
    actions.add_argument(
        "--confirm-quarantine",
        action="store_true",
        help="confirm the human-managed dups quarantine checkpoint",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="authorize only the pending reviewed apply stage with --run-next",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--verbose", action="store_true", default=None)
    output.add_argument("--quiet", action="store_true", default=None)
    timestamps = parser.add_mutually_exclusive_group()
    timestamps.add_argument("--timestamps", dest="timestamps", action="store_true")
    timestamps.add_argument("--no-timestamps", dest="timestamps", action="store_false")
    parser.set_defaults(timestamps=None)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--show-ignored", action="store_true", default=None)
    parser.add_argument("--ffmpeg", type=Path)
    parser.add_argument("--ffprobe", type=Path)
    parser.add_argument("--decode-timeout", type=int)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--no-cache", action="store_true", default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.apply and not args.run_next:
        print("--apply requires --run-next.", file=sys.stderr)
        return 2
    if args.decode_timeout is not None and args.decode_timeout <= 0:
        print("--decode-timeout must be positive.", file=sys.stderr)
        return 2
    if args.workers is not None and not 1 <= args.workers <= 32:
        print("--workers must be between 1 and 32.", file=sys.stderr)
        return 2

    baseline = args.baseline.expanduser().resolve()
    working = args.working.expanduser().resolve()
    try:
        _validate_roots(baseline, working)
        if args.log_dir is None:
            if (
                args.start
                or args.run_next
                or args.accept_status
                or args.confirm_quarantine
            ):
                raise MigrationCoordinatorError(
                    "an explicit --log-dir is required for restartable workflow actions"
                )
            _print_plan()
            print(
                "Zero-write plan only. Add --log-dir and --start to initialize private restart state."
            )
            return 0

        requested_log_dir = args.log_dir.expanduser()
        if requested_log_dir.is_symlink():
            raise MigrationCoordinatorError(
                "private log directory must not be a symbolic link"
            )
        log_dir = requested_log_dir.resolve()
        if not _disjoint(log_dir, baseline) or not _disjoint(log_dir, working):
            raise MigrationCoordinatorError(
                "private log directory must be distinct and non-nested with both collections"
            )
        _prepare_log_dir(log_dir, create=args.start)
        state_path = _state_path(log_dir)
        with _state_lock(log_dir):
            if args.start:
                if os.path.lexists(state_path):
                    raise MigrationCoordinatorError(
                        "migration restart state already exists in this private log directory"
                    )
                created = _now()
                state = MigrationState(
                    __version__,
                    baseline,
                    working,
                    _initial_options(args),
                    0,
                    (),
                    created,
                    created,
                )
                _write_state(state_path, state)
                print(f"Initialized private migration state: {state_path}")
                _print_status(state)
                return 0
            if not os.path.lexists(state_path):
                raise MigrationCoordinatorError(
                    "no migration restart state exists; use --start first"
                )
            state = _load_state(state_path)
            if state.baseline != baseline or state.working != working:
                raise MigrationCoordinatorError(
                    "declared collections do not match the private restart state"
                )
            if state.tool_version != __version__:
                raise MigrationCoordinatorError(
                    "restart state was created by a different pymo version"
                )
            _require_matching_options(args, state)
            if args.run_next:
                return _run_next(log_dir, state_path, state, args.apply)
            if args.accept_status:
                return _accept_status(state_path, state)
            if args.confirm_quarantine:
                return _confirm_quarantine(state_path, state)
            _print_status(state)
            _print_plan(state.next_stage)
            return 0
    except MigrationCoordinatorError as error:
        print(
            f"Migration coordinator cannot safely continue: {error}.", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
