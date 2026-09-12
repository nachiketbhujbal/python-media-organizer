"""Guide one baseline and working collection through the migration runbook."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Sequence
from dataclasses import replace
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
from pymo.migration.outcome import MigrationOutcomeError, ResultKind, read_outcome
from pymo.migration.preauthorization import (
    MigrationPreauthorization,
    MigrationPreauthorizationError,
    MigrationPreauthorizationMismatch,
    apply_preview_stage,
    load_preauthorization,
)
from pymo.migration.roots import (
    DirectoryIdentityError,
    directory_identity,
    existing_directories_are_disjoint,
    paths_are_disjoint,
)
from pymo.migration.synopsis import (
    MigrationSynopsisError,
    build_report,
    print_synopsis,
    validate_synopsis_history,
)
from pymo.migration.workflow import (
    CoordinatorOptions,
    Stage,
    _stages,
    child_command,
)


def _disjoint(first: Path, second: Path) -> bool:
    try:
        return paths_are_disjoint(first, second)
    except DirectoryIdentityError as error:
        raise MigrationCoordinatorError(str(error)) from error


def _expand_argument_path(path: Path) -> Path:
    try:
        return path.expanduser()
    except (OSError, RuntimeError) as error:
        raise MigrationCoordinatorError(
            "a command-line path cannot be resolved safely"
        ) from error


def _resolve_argument_path(path: Path) -> Path:
    try:
        return _expand_argument_path(path).resolve()
    except (OSError, RuntimeError) as error:
        raise MigrationCoordinatorError(
            "a command-line path cannot be resolved safely"
        ) from error


def _validate_roots(baseline: Path, working: Path) -> None:
    if not baseline.is_dir():
        raise MigrationCoordinatorError("baseline is not a readable directory")
    if not working.is_dir():
        raise MigrationCoordinatorError(
            "working collection is not a readable directory"
        )
    try:
        disjoint = existing_directories_are_disjoint(baseline, working)
    except DirectoryIdentityError as error:
        raise MigrationCoordinatorError(str(error)) from error
    if not disjoint:
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
        "show_files",
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
                str(_resolve_argument_path(value)) if isinstance(value, Path) else value
            )
    return overrides


def _initial_options(overrides: dict[str, object]) -> CoordinatorOptions:
    values: dict[str, object] = {
        "verbose": False,
        "quiet": False,
        "timestamps": True,
        "config": None,
        "show_ignored": False,
        "show_files": False,
        "ffmpeg": None,
        "ffprobe": None,
        "decode_timeout": None,
        "workers": None,
        "no_cache": False,
    }
    values.update(overrides)
    return CoordinatorOptions(**values)  # type: ignore[arg-type]


def _require_matching_options(
    overrides: dict[str, object], state: MigrationState
) -> None:
    current = state.options.as_json()
    for name, value in overrides.items():
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


def _stage_result_kind(stage: Stage) -> ResultKind:
    if stage.identifier == "without-dups-simulation":
        return "simulated"
    if stage.mode == "preview":
        return "preview"
    return "observed"


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
        if any(attempt.action == "signoff" for attempt in state.attempts):
            print(
                "Human sign-off is recorded in private restart state; retain source, baseline, and quarantine."
            )
        else:
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
        print("Run routine stages with --run, or only this stage with --run-next.")


def _run_next(
    log_dir: Path, state_path: Path, state: MigrationState, apply: bool
) -> int:
    validate_synopsis_history(log_dir, state)
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
    outcome_file = log_file.with_suffix(".outcome.json")
    expected_decision_digest: str | None = None
    if stage.mode == "apply":
        preview = _recorded_outcome(
            log_dir, state, apply_preview_stage(stage.identifier)
        )
        value = preview["data"]["decision_digest"]  # type: ignore[index]
        if not isinstance(value, str):  # pragma: no cover - outcome validation owns it.
            raise MigrationCoordinatorError(
                "reviewed preview has an invalid private decision digest"
            )
        expected_decision_digest = value
    command = child_command(
        state.baseline,
        state.working,
        state.options,
        stage,
        log_file,
        outcome_file,
        expected_decision_digest,
    )
    print(f"Running one migration stage: {stage.identifier}.")
    print(f"Private stage log: {log_file}")
    started_at = time.monotonic()
    try:
        completed = subprocess.run(command, check=False)
        status = completed.returncode
        if status < 0:
            status = 128 + abs(status)
    except OSError:
        status = 127
    duration_milliseconds = max(0, round((time.monotonic() - started_at) * 1000))
    outcome_name: str | None = None
    if os.path.lexists(outcome_file):
        try:
            read_outcome(
                outcome_file,
                expected_command=stage.command or "",
                expected_status=status,
                expected_result_kind=_stage_result_kind(stage),
            )
        except MigrationOutcomeError as error:
            raise MigrationCoordinatorError(
                "private stage outcome is invalid"
            ) from error
        outcome_name = outcome_file.name
    elif status == 0 or (stage.command == "validate" and status == 1):
        raise MigrationCoordinatorError(
            "successful child stage did not record its private typed outcome"
        )
    attempt = Attempt(
        stage.identifier,
        "run",
        status,
        _now(),
        log_file.name,
        apply,
        duration_milliseconds,
        outcome_name,
    )
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
            and outcome_name is not None
        ):
            print(
                "Review the findings; --accept-status is the explicit acknowledgement boundary."
            )
    return status


def _run_until_checkpoint(
    log_dir: Path, state_path: Path, state: MigrationState
) -> int:
    binding = state
    identities = _collection_identities(state)
    while state.next_stage < len(_stages()):
        _require_collection_identities(state, identities)
        stage = _stages()[state.next_stage]
        if stage.mode in {"apply", "checkpoint"}:
            print("Safe operator loop paused at an operator checkpoint.")
            _print_status(state)
            print_synopsis(log_dir, state)
            return 0
        previous_state = state
        status = _run_next(log_dir, state_path, state, apply=False)
        if status != 0:
            print_synopsis(log_dir, _load_state(state_path))
            return status
        state = _load_state(state_path)
        _require_successful_transition(previous_state, state, stage)
        _require_operator_binding(state, binding)
        _require_collection_identities(state, identities)
        if stage.review_after_success:
            print("Safe operator loop paused for validation review.")
            _print_status(state)
            print_synopsis(log_dir, state)
            return 0
    _require_collection_identities(state, identities)
    print("Safe operator loop reached the final sign-off boundary.")
    _print_status(state)
    print_synopsis(log_dir, state)
    return 0


def _require_operator_binding(state: MigrationState, expected: MigrationState) -> None:
    if (
        state.tool_version != expected.tool_version
        or state.baseline != expected.baseline
        or state.working != expected.working
        or state.options != expected.options
        or state.created_at != expected.created_at
        or state.unattended_policy_sha256 != expected.unattended_policy_sha256
    ):
        raise MigrationCoordinatorError(
            "migration restart binding changed during the safe operator loop"
        )


def _require_successful_transition(
    previous: MigrationState, current: MigrationState, stage: Stage
) -> None:
    _require_run_transition(previous, current, stage, status=0, apply=False)


def _require_run_transition(
    previous: MigrationState,
    current: MigrationState,
    stage: Stage,
    *,
    status: int,
    apply: bool,
) -> None:
    if (
        current.next_stage != previous.next_stage + int(status == 0)
        or len(current.attempts) != len(previous.attempts) + 1
        or current.attempts[:-1] != previous.attempts
    ):
        raise MigrationCoordinatorError(
            "migration restart lifecycle changed unexpectedly during the safe operator loop"
        )
    attempt = current.attempts[-1]
    if (
        attempt.stage != stage.identifier
        or attempt.action != "run"
        or attempt.exit_status != status
        or attempt.log_file is None
        or attempt.apply != apply
        or (status == 0 and attempt.outcome_file is None)
    ):
        raise MigrationCoordinatorError(
            "migration restart lifecycle changed unexpectedly during the safe operator loop"
        )


def _require_bookkeeping_transition(
    previous: MigrationState,
    current: MigrationState,
    stage: Stage,
    *,
    action: str,
    status: int,
    advance: bool,
) -> None:
    if (
        current.next_stage != previous.next_stage + int(advance)
        or len(current.attempts) != len(previous.attempts) + 1
        or current.attempts[:-1] != previous.attempts
    ):
        raise MigrationCoordinatorError(
            "migration restart lifecycle changed unexpectedly during the interactive operator loop"
        )
    attempt = current.attempts[-1]
    if (
        attempt.stage != stage.identifier
        or attempt.action != action
        or attempt.exit_status != status
        or attempt.log_file is not None
        or attempt.apply
    ):
        raise MigrationCoordinatorError(
            "migration restart lifecycle changed unexpectedly during the interactive operator loop"
        )


def _collection_identities(
    state: MigrationState,
) -> tuple[tuple[int, int], tuple[int, int]]:
    try:
        baseline = directory_identity(state.baseline)
        working = directory_identity(state.working)
    except DirectoryIdentityError as error:
        raise MigrationCoordinatorError(str(error)) from error
    if baseline is None or working is None:
        raise MigrationCoordinatorError(
            "collection identity changed during the safe operator loop"
        )
    return baseline, working


def _require_collection_identities(
    state: MigrationState,
    expected: tuple[tuple[int, int], tuple[int, int]],
) -> None:
    if _collection_identities(state) != expected:
        raise MigrationCoordinatorError(
            "collection identity changed during the safe operator loop"
        )


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


def _prompt_yes_no(question: str) -> bool:
    print(f"{question} [y/N]", file=sys.stderr)
    response = sys.stdin.readline()
    if response == "":
        raise MigrationCoordinatorError("interactive input ended before a decision")
    answer = response.strip().lower()
    if answer in {"y", "yes"}:
        return True
    if answer in {"", "n", "no"}:
        return False
    raise MigrationCoordinatorError(
        "interactive input must be yes, y, no, n, or an empty response"
    )


def _successful_validation_review(state: MigrationState) -> Stage | None:
    if not state.attempts:
        return None
    attempt = state.attempts[-1]
    if attempt.action != "run" or attempt.exit_status != 0:
        return None
    stage = next((item for item in _stages() if item.identifier == attempt.stage), None)
    if stage is None or not stage.review_after_success:
        return None
    return stage


def _pending_status_one_validation(state: MigrationState) -> Stage | None:
    if state.next_stage == len(_stages()) or not state.attempts:
        return None
    stage = _stages()[state.next_stage]
    attempt = state.attempts[-1]
    if (
        not stage.review_after_success
        or attempt.stage != stage.identifier
        or attempt.action != "run"
        or attempt.exit_status != 1
    ):
        return None
    return stage


def _acknowledge_review(state_path: Path, state: MigrationState, stage: Stage) -> None:
    attempt = Attempt(stage.identifier, "acknowledge-review", 0, _now(), None, False)
    _write_state(state_path, _updated_state(state, attempt, advance=False))


def _record_signoff(state_path: Path, state: MigrationState) -> None:
    stage = _stages()[-1]
    attempt = Attempt(stage.identifier, "signoff", 0, _now(), None, False)
    _write_state(state_path, _updated_state(state, attempt, advance=False))


def _recorded_outcome(
    log_dir: Path, state: MigrationState, stage_identifier: str
) -> dict[str, object]:
    stage = next(
        (item for item in _stages() if item.identifier == stage_identifier), None
    )
    if stage is None or stage.command is None:
        raise MigrationCoordinatorError(
            "migration checkpoint refers to an unknown evidence stage"
        )
    attempt = next(
        (
            item
            for item in reversed(state.attempts)
            if item.stage == stage_identifier and item.action == "run"
        ),
        None,
    )
    if attempt is None or attempt.outcome_file is None:
        raise MigrationCoordinatorError(
            "migration checkpoint does not have a private typed outcome"
        )
    try:
        return read_outcome(
            log_dir / attempt.outcome_file,
            expected_command=stage.command,
            expected_status=attempt.exit_status,
            expected_result_kind=_stage_result_kind(stage),
        )
    except MigrationOutcomeError as error:
        raise MigrationCoordinatorError(
            "migration checkpoint private typed outcome is invalid"
        ) from error


def _reload_unattended(
    state_path: Path,
    expected_state: MigrationState,
    binding: MigrationState,
    identities: tuple[tuple[int, int], tuple[int, int]],
    policy: MigrationPreauthorization,
) -> MigrationState:
    policy.require_current()
    state = _load_state(state_path)
    if state != expected_state:
        raise MigrationCoordinatorError(
            "migration restart lifecycle changed during unattended execution"
        )
    _require_operator_binding(state, binding)
    _require_collection_identities(state, identities)
    policy.require_binding(state)
    return state


def _bind_unattended_policy(
    state_path: Path,
    state: MigrationState,
    policy: MigrationPreauthorization,
) -> MigrationState:
    if state.unattended_policy_sha256 is None:
        state = replace(
            state,
            unattended_policy_sha256=policy.payload_sha256,
            updated_at=_now(),
        )
        _write_state(state_path, state)
        state = _load_state(state_path)
    if state.unattended_policy_sha256 != policy.payload_sha256:
        raise MigrationCoordinatorError(
            "pre-authorization policy differs from the policy bound to this migration"
        )
    return state


def _run_unattended(
    log_dir: Path,
    state_path: Path,
    state: MigrationState,
    policy: MigrationPreauthorization,
) -> int:
    binding = state
    identities = _collection_identities(state)
    try:
        while True:
            validate_synopsis_history(log_dir, state)
            _require_operator_binding(state, binding)
            _require_collection_identities(state, identities)
            policy.require_current()
            policy.require_binding(state)

            successful_review = _successful_validation_review(state)
            if successful_review is not None:
                outcome = _recorded_outcome(
                    log_dir, state, successful_review.identifier
                )
                policy.require_checkpoint(successful_review.identifier, outcome)
                state = _reload_unattended(
                    state_path, state, binding, identities, policy
                )
                previous_state = state
                _acknowledge_review(state_path, state, successful_review)
                state = _load_state(state_path)
                _require_bookkeeping_transition(
                    previous_state,
                    state,
                    successful_review,
                    action="acknowledge-review",
                    status=0,
                    advance=False,
                )
                continue

            status_one_review = _pending_status_one_validation(state)
            if status_one_review is not None:
                outcome = _recorded_outcome(
                    log_dir, state, status_one_review.identifier
                )
                policy.require_checkpoint(status_one_review.identifier, outcome)
                state = _reload_unattended(
                    state_path, state, binding, identities, policy
                )
                previous_state = state
                status = _accept_status(state_path, state)
                if status != 0:  # pragma: no cover - guarded by state inspection.
                    return status
                state = _load_state(state_path)
                _require_bookkeeping_transition(
                    previous_state,
                    state,
                    status_one_review,
                    action="acknowledge-status",
                    status=1,
                    advance=True,
                )
                continue

            if state.next_stage == len(_stages()):
                if state.attempts and state.attempts[-1].action == "signoff":
                    print("Unattended migration is already complete and signed off.")
                    _print_status(state)
                    print_synopsis(log_dir, state)
                    return 0
                final_stage = _stages()[-1]
                outcome = _recorded_outcome(log_dir, state, final_stage.identifier)
                policy.require_checkpoint("final-signoff", outcome)
                state = _reload_unattended(
                    state_path, state, binding, identities, policy
                )
                previous_state = state
                _record_signoff(state_path, state)
                state = _load_state(state_path)
                _require_bookkeeping_transition(
                    previous_state,
                    state,
                    final_stage,
                    action="signoff",
                    status=0,
                    advance=False,
                )
                _require_operator_binding(state, binding)
                _require_collection_identities(state, identities)
                print(
                    "Pre-authorized final sign-off recorded in private migration state."
                )
                _print_status(state)
                print_synopsis(log_dir, state)
                return 0

            stage = _stages()[state.next_stage]
            if stage.mode == "apply":
                preview = apply_preview_stage(stage.identifier)
                outcome = _recorded_outcome(log_dir, state, preview)
                policy.require_checkpoint(stage.identifier, outcome)
                state = _reload_unattended(
                    state_path, state, binding, identities, policy
                )
                previous_state = state
                status = _run_next(log_dir, state_path, state, apply=True)
                state = _load_state(state_path)
                _require_run_transition(
                    previous_state, state, stage, status=status, apply=True
                )
                _require_operator_binding(state, binding)
                _require_collection_identities(state, identities)
                policy.require_current()
                policy.require_binding(state)
                if status != 0:
                    print_synopsis(log_dir, state)
                    return status
                continue

            if stage.mode == "checkpoint":
                outcome = _recorded_outcome(log_dir, state, "without-dups-simulation")
                policy.require_checkpoint("external-quarantine", outcome)
                state = _reload_unattended(
                    state_path, state, binding, identities, policy
                )
                previous_state = state
                status = _confirm_quarantine(state_path, state)
                if status != 0:
                    _require_collection_identities(state, identities)
                    print_synopsis(log_dir, state)
                    return status
                state = _load_state(state_path)
                _require_bookkeeping_transition(
                    previous_state,
                    state,
                    stage,
                    action="confirm-quarantine",
                    status=0,
                    advance=True,
                )
                continue

            previous_state = state
            status = _run_next(log_dir, state_path, state, apply=False)
            state = _load_state(state_path)
            _require_run_transition(
                previous_state, state, stage, status=status, apply=False
            )
            _require_operator_binding(state, binding)
            _require_collection_identities(state, identities)
            policy.require_current()
            policy.require_binding(state)
            if status != 0 and not (stage.review_after_success and status == 1):
                print_synopsis(log_dir, state)
                return status
    except MigrationPreauthorizationMismatch as error:
        print(f"Unattended migration stopped: {error}.", file=sys.stderr)
        print_synopsis(log_dir, state)
        return 1


def _reload_after_prompt(
    state_path: Path,
    expected_state: MigrationState,
    binding: MigrationState,
    identities: tuple[tuple[int, int], tuple[int, int]],
) -> MigrationState:
    state = _load_state(state_path)
    if state != expected_state:
        raise MigrationCoordinatorError(
            "migration restart lifecycle changed while awaiting interactive input"
        )
    _require_operator_binding(state, binding)
    _require_collection_identities(state, identities)
    return state


def _run_interactive(log_dir: Path, state_path: Path, state: MigrationState) -> int:
    binding = state
    identities = _collection_identities(state)
    while True:
        _require_operator_binding(state, binding)
        _require_collection_identities(state, identities)

        successful_review = _successful_validation_review(state)
        if successful_review is not None:
            if not _prompt_yes_no(
                f"Accept the reviewed successful findings for {successful_review.identifier}?"
            ):
                print("Interactive migration paused before validation acknowledgement.")
                print_synopsis(log_dir, state)
                return 0
            state = _reload_after_prompt(state_path, state, binding, identities)
            previous_state = state
            _acknowledge_review(state_path, state, successful_review)
            state = _load_state(state_path)
            _require_bookkeeping_transition(
                previous_state,
                state,
                successful_review,
                action="acknowledge-review",
                status=0,
                advance=False,
            )
            continue

        status_one_review = _pending_status_one_validation(state)
        if status_one_review is not None:
            if not _prompt_yes_no(
                f"Accept the reviewed status-1 findings for {status_one_review.identifier}?"
            ):
                print("Interactive migration paused before validation acknowledgement.")
                print_synopsis(log_dir, state)
                return 1
            state = _reload_after_prompt(state_path, state, binding, identities)
            previous_state = state
            status = _accept_status(state_path, state)
            if status != 0:
                return status
            state = _load_state(state_path)
            _require_bookkeeping_transition(
                previous_state,
                state,
                status_one_review,
                action="acknowledge-status",
                status=1,
                advance=True,
            )
            continue

        if state.next_stage == len(_stages()):
            if state.attempts and state.attempts[-1].action == "signoff":
                print("Interactive migration is already complete and signed off.")
                _print_status(state)
                print_synopsis(log_dir, state)
                return 0
            if not _prompt_yes_no(
                "Record human sign-off for the completed migration verification?"
            ):
                print("Interactive migration paused at final human sign-off.")
                print_synopsis(log_dir, state)
                return 0
            state = _reload_after_prompt(state_path, state, binding, identities)
            previous_state = state
            final_stage = _stages()[-1]
            _record_signoff(state_path, state)
            state = _load_state(state_path)
            _require_bookkeeping_transition(
                previous_state,
                state,
                final_stage,
                action="signoff",
                status=0,
                advance=False,
            )
            _require_operator_binding(state, binding)
            _require_collection_identities(state, identities)
            print("Human sign-off recorded in private migration state.")
            _print_status(state)
            print_synopsis(log_dir, state)
            return 0

        stage = _stages()[state.next_stage]
        if stage.mode == "apply":
            if not _prompt_yes_no(
                f"Apply the reviewed mutation for {stage.identifier}?"
            ):
                print("Interactive migration paused before mutation.")
                print_synopsis(log_dir, state)
                return 0
            state = _reload_after_prompt(state_path, state, binding, identities)
            previous_state = state
            status = _run_next(log_dir, state_path, state, apply=True)
            state = _load_state(state_path)
            _require_run_transition(
                previous_state, state, stage, status=status, apply=True
            )
            _require_operator_binding(state, binding)
            _require_collection_identities(state, identities)
            if status != 0:
                print_synopsis(log_dir, state)
                return status
            continue

        if stage.mode == "checkpoint":
            if not _prompt_yes_no(
                "Confirm the complete dups tree is retained externally and absent from the working collection?"
            ):
                print("Interactive migration paused at external quarantine review.")
                print_synopsis(log_dir, state)
                return 0
            state = _reload_after_prompt(state_path, state, binding, identities)
            previous_state = state
            status = _confirm_quarantine(state_path, state)
            if status != 0:
                _require_collection_identities(state, identities)
                print_synopsis(log_dir, state)
                return status
            state = _load_state(state_path)
            _require_bookkeeping_transition(
                previous_state,
                state,
                stage,
                action="confirm-quarantine",
                status=0,
                advance=True,
            )
            continue

        previous_state = state
        status = _run_next(log_dir, state_path, state, apply=False)
        state = _load_state(state_path)
        _require_run_transition(
            previous_state, state, stage, status=status, apply=False
        )
        _require_operator_binding(state, binding)
        _require_collection_identities(state, identities)
        if status != 0 and not (stage.review_after_success and status == 1):
            print_synopsis(log_dir, state)
            return status


def _dispatch_existing_state(
    args: argparse.Namespace,
    log_dir: Path,
    state_path: Path,
    state: MigrationState,
) -> int:
    validate_synopsis_history(log_dir, state)
    if args.json:
        identities = _collection_identities(state)
        report = build_report(log_dir, state)
        current = _load_state(state_path)
        if current != state:
            raise MigrationCoordinatorError(
                "migration restart lifecycle changed during report generation"
            )
        _require_collection_identities(current, identities)
        if build_report(log_dir, current) != report:
            raise MigrationCoordinatorError(
                "private stage outcome history changed during report generation"
            )
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    if args.run_next:
        status = _run_next(log_dir, state_path, state, args.apply)
        updated = _load_state(state_path)
        print_synopsis(log_dir, updated)
        return status
    if args.run:
        return _run_until_checkpoint(log_dir, state_path, state)
    if args.interactive:
        return _run_interactive(log_dir, state_path, state)
    if args.unattended is not None:
        policy = load_preauthorization(
            args.unattended, roots=(state.baseline, state.working)
        )
        state = _bind_unattended_policy(state_path, state, policy)
        policy.require_binding(state)
        return _run_unattended(log_dir, state_path, state, policy)
    if args.accept_status:
        status = _accept_status(state_path, state)
        print_synopsis(log_dir, _load_state(state_path))
        return status
    if args.confirm_quarantine:
        status = _confirm_quarantine(state_path, state)
        print_synopsis(log_dir, _load_state(state_path))
        return status
    _print_status(state)
    _print_plan(state.next_stage)
    print_synopsis(log_dir, state)
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guide one baseline and working collection through the production runbook."
    )
    parser.add_argument(
        "baseline", nargs="?", type=Path, help="unchanged baseline collection"
    )
    parser.add_argument(
        "working", nargs="?", type=Path, help="working collection to transform"
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        help="explicit private directory for restart state and per-stage logs",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        metavar="PRIVATE_STATE_DIRECTORY",
        help="resume using roots and options from an existing private state directory",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--start", action="store_true", help="initialize restartable workflow state"
    )
    actions.add_argument(
        "--run-next", action="store_true", help="run exactly the pending child stage"
    )
    actions.add_argument(
        "--run",
        action="store_true",
        help="run routine stages until the next operator checkpoint",
    )
    actions.add_argument(
        "--interactive",
        action="store_true",
        help="run in one foreground process and ask at each operator checkpoint",
    )
    actions.add_argument(
        "--unattended",
        type=Path,
        metavar="PRIVATE_POLICY_JSON",
        help="run only checkpoints explicitly authorized by a private policy",
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
    parser.add_argument("--show-files", action="store_true", default=None)
    parser.add_argument("--ffmpeg", type=Path)
    parser.add_argument("--ffprobe", type=Path)
    parser.add_argument("--decode-timeout", type=int)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--no-cache", action="store_true", default=None)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the stable path-private migration report and exit",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    selected_action = any(
        (
            args.start,
            args.run_next,
            args.run,
            args.interactive,
            args.unattended is not None,
            args.accept_status,
            args.confirm_quarantine,
        )
    )
    if args.json and selected_action:
        print(
            "Migration coordinator cannot safely continue: --json cannot be combined with a workflow action.",
            file=sys.stderr,
        )
        return 2
    if args.json and (args.show_files or args.show_ignored):
        print(
            "Migration coordinator cannot safely continue: --json is always path-private and cannot show files or ignored paths.",
            file=sys.stderr,
        )
        return 2
    if args.apply and not args.run_next:
        print("--apply requires --run-next.", file=sys.stderr)
        return 2
    if args.decode_timeout is not None and args.decode_timeout <= 0:
        print("--decode-timeout must be positive.", file=sys.stderr)
        return 2
    if args.workers is not None and not 1 <= args.workers <= 32:
        print("--workers must be between 1 and 32.", file=sys.stderr)
        return 2
    if args.interactive and not sys.stdin.isatty():
        print(
            "Migration coordinator cannot safely continue: --interactive requires terminal input.",
            file=sys.stderr,
        )
        return 2

    if args.resume is not None:
        if args.baseline is not None or args.working is not None:
            print(
                "Migration coordinator cannot safely continue: --resume cannot be combined with positional collections.",
                file=sys.stderr,
            )
            return 2
        if args.log_dir is not None:
            print(
                "Migration coordinator cannot safely continue: --resume cannot be combined with --log-dir.",
                file=sys.stderr,
            )
            return 2
        if args.start:
            print(
                "Migration coordinator cannot safely continue: --resume cannot initialize migration state.",
                file=sys.stderr,
            )
            return 2
    elif args.baseline is None or args.working is None:
        print(
            "Migration coordinator cannot safely continue: baseline and working collections are required unless --resume is used.",
            file=sys.stderr,
        )
        return 2

    try:
        option_overrides = _option_overrides(args)
        if args.resume is not None:
            requested_log_dir = _expand_argument_path(args.resume)
            if requested_log_dir.is_symlink():
                raise MigrationCoordinatorError(
                    "private resume directory must not be a symbolic link"
                )
            log_dir = _resolve_argument_path(requested_log_dir)
            _prepare_log_dir(log_dir, create=False)
            state_path = _state_path(log_dir)
            if not os.path.lexists(state_path):
                raise MigrationCoordinatorError(
                    "no migration restart state exists in the private resume directory"
                )
            with _state_lock(log_dir, create=not args.json):
                if not os.path.lexists(state_path):
                    raise MigrationCoordinatorError(
                        "no migration restart state exists in the private resume directory"
                    )
                state = _load_state(state_path)
                if state.tool_version != __version__:
                    raise MigrationCoordinatorError(
                        "restart state was created by a different pymo version"
                    )
                baseline = _resolve_argument_path(state.baseline)
                working = _resolve_argument_path(state.working)
                if baseline != state.baseline or working != state.working:
                    raise MigrationCoordinatorError(
                        "recorded collection roots no longer resolve to their saved paths"
                    )
                _validate_roots(baseline, working)
                if not _disjoint(log_dir, baseline) or not _disjoint(log_dir, working):
                    raise MigrationCoordinatorError(
                        "private resume directory must be distinct and non-nested with both collections"
                    )
                _require_matching_options(option_overrides, state)
                return _dispatch_existing_state(args, log_dir, state_path, state)

        assert args.baseline is not None
        assert args.working is not None
        baseline = _resolve_argument_path(args.baseline)
        working = _resolve_argument_path(args.working)
        _validate_roots(baseline, working)
        if args.log_dir is None:
            if (
                args.start
                or args.run_next
                or args.run
                or args.interactive
                or args.unattended is not None
                or args.accept_status
                or args.confirm_quarantine
                or args.json
            ):
                raise MigrationCoordinatorError(
                    "an explicit --log-dir is required for restartable workflow actions"
                )
            _print_plan()
            print(
                "Zero-write plan only. Add --log-dir and --start to initialize private restart state."
            )
            return 0

        requested_log_dir = _expand_argument_path(args.log_dir)
        if requested_log_dir.is_symlink():
            raise MigrationCoordinatorError(
                "private log directory must not be a symbolic link"
            )
        log_dir = _resolve_argument_path(requested_log_dir)
        if not _disjoint(log_dir, baseline) or not _disjoint(log_dir, working):
            raise MigrationCoordinatorError(
                "private log directory must be distinct and non-nested with both collections"
            )
        policy: MigrationPreauthorization | None = None
        if args.unattended is not None:
            policy = load_preauthorization(args.unattended, roots=(baseline, working))
        state_path = _state_path(log_dir)
        initial_unattended_state: MigrationState | None = None
        if policy is not None and not os.path.lexists(state_path):
            created = _now()
            initial_unattended_state = MigrationState(
                __version__,
                baseline,
                working,
                _initial_options(option_overrides),
                0,
                (),
                created,
                created,
                policy.payload_sha256,
            )
            policy.require_binding(initial_unattended_state)
            policy.require_current()
        _prepare_log_dir(log_dir, create=args.start or policy is not None)
        with _state_lock(log_dir, create=not args.json):
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
                    _initial_options(option_overrides),
                    0,
                    (),
                    created,
                    created,
                )
                _write_state(state_path, state)
                print(f"Initialized private migration state: {state_path}")
                _print_status(state)
                print_synopsis(log_dir, state)
                return 0
            if initial_unattended_state is not None and not os.path.lexists(state_path):
                state = initial_unattended_state
                assert policy is not None
                policy.require_binding(state)
                policy.require_current()
                _write_state(state_path, state)
                print(f"Initialized private migration state: {state_path}")
                return _run_unattended(log_dir, state_path, state, policy)
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
            _require_matching_options(option_overrides, state)
            return _dispatch_existing_state(args, log_dir, state_path, state)
    except (
        MigrationCoordinatorError,
        MigrationPreauthorizationError,
        MigrationSynopsisError,
    ) as error:
        print(
            f"Migration coordinator cannot safely continue: {error}.", file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
