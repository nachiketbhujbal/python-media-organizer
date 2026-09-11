"""Concise path-private human synopsis for one guided migration."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pymo.logging_config import emit as print
from pymo.migration.coordinator_state import Attempt, MigrationState
from pymo.migration.outcome import MigrationOutcomeError, read_outcome
from pymo.migration.workflow import Stage, _stages
from pymo.progress import format_bytes, format_duration


class MigrationSynopsisError(RuntimeError):
    """The private outcome history cannot support a trustworthy synopsis."""


def _stage_map() -> dict[str, Stage]:
    return {stage.identifier: stage for stage in _stages()}


def _outcomes(
    log_dir: Path, state: MigrationState
) -> list[tuple[Attempt, dict[str, Any]]]:
    stages = _stage_map()
    values: list[tuple[Attempt, dict[str, Any]]] = []
    for attempt in state.attempts:
        if attempt.action != "run" or attempt.outcome_file is None:
            continue
        stage = stages.get(attempt.stage)
        if stage is None or stage.command is None:
            raise MigrationSynopsisError(
                "migration synopsis references an unknown stage"
            )
        try:
            outcome = read_outcome(
                log_dir / attempt.outcome_file,
                expected_command=stage.command,
                expected_status=attempt.exit_status,
                expected_result_kind=(
                    "simulated"
                    if stage.identifier == "without-dups-simulation"
                    else "preview" if stage.mode == "preview" else "observed"
                ),
            )
        except MigrationOutcomeError as error:
            raise MigrationSynopsisError(
                "migration synopsis cannot trust a private stage outcome"
            ) from error
        values.append((attempt, outcome))
    return values


def validate_synopsis_history(log_dir: Path, state: MigrationState) -> None:
    """Require every recorded private outcome to remain trustworthy."""

    _outcomes(log_dir, state)


def _latest(
    values: Iterable[tuple[Attempt, dict[str, Any]]],
    *stage_names: str,
    successful: bool = True,
) -> dict[str, Any] | None:
    names = set(stage_names)
    matches = [
        outcome
        for attempt, outcome in values
        if attempt.stage in names and (not successful or attempt.exit_status == 0)
    ]
    return matches[-1] if matches else None


def _workflow_label(state: MigrationState) -> str:
    if state.next_stage == 0 and not state.attempts:
        return "not started"
    if state.next_stage == len(_stages()):
        return (
            "complete and signed off"
            if any(attempt.action == "signoff" for attempt in state.attempts)
            else "complete; human sign-off pending"
        )
    if state.attempts:
        latest = state.attempts[-1]
        if latest.action == "run" and latest.exit_status != 0:
            return f"stopped at {latest.stage} (exit {latest.exit_status})"
    return f"pending at {_stages()[state.next_stage].identifier}"


def _print_inventory(label: str, outcome: dict[str, Any]) -> None:
    data = outcome["data"]
    print(
        f"  {label}: {data['files']} file(s), {format_bytes(data['bytes'])}; "
        f"{data['pictures']} picture(s), {data['videos']} video(s), "
        f"{data['audio']} audio file(s), "
        f"{data['other'] + data['unknown']} other or unknown file(s)."
    )
    if data["unreadable"] or data["changed"] or data["symbolic_links"]:
        print(
            "    Inspection limits: "
            f"{data['unreadable']} unreadable, {data['changed']} changed, "
            f"{data['symbolic_links']} symbolic link(s)."
        )


def _print_health(label: str, outcome: dict[str, Any]) -> None:
    data = outcome["data"]
    print(
        f"  {label}: {data['healthy']} healthy, "
        f"{data['warning_only']} warning-only, {data['errors']} with errors; "
        f"{data['media_files']} media and {data['other_files']} non-media file(s)."
    )
    if data["symbolic_links"] or data["unreadable"] or data["changed"]:
        print(
            "    Inspection limits: "
            f"{data['symbolic_links']} symbolic link(s), "
            f"{data['unreadable']} unreadable, {data['changed']} changed."
        )


def _count_phrase(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _applied_transformations(
    values: list[tuple[Attempt, dict[str, Any]]],
) -> list[dict[str, Any]]:
    names = (
        "extension-apply",
        "organize-apply",
        "rename-apply",
    )
    return [
        outcome["data"]
        for name in names
        if (outcome := _latest(values, name)) is not None
    ]


def _duplicate_results(
    values: list[tuple[Attempt, dict[str, Any]]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for applied, preview in (
        ("image-duplicates-apply", "image-duplicates-preview"),
        ("video-duplicates-apply", "video-duplicates-preview"),
    ):
        outcome = _latest(values, applied) or _latest(values, preview)
        if outcome is not None:
            results.append(outcome)
    return results


def _print_warnings(validation: dict[str, Any] | None) -> None:
    if validation is None:
        return
    findings = validation["data"]["findings"]
    if not findings:
        print("  Latest working validation findings: none.")
        return
    rendered = ", ".join(
        f"{item['code']}={item['count']} ({item['severity']})" for item in findings
    )
    print(f"  Latest working validation findings: {rendered}.")


def print_synopsis(log_dir: Path, state: MigrationState) -> None:
    values = _outcomes(log_dir, state)
    total_seconds = (
        sum(
            attempt.duration_milliseconds
            for attempt in state.attempts
            if attempt.action == "run"
        )
        / 1000
    )
    print("\nMigration synopsis")
    print(f"  Workflow: {_workflow_label(state)}.")
    print(
        f"  Observed child work: {format_duration(total_seconds)} across "
        f"{sum(attempt.action == 'run' for attempt in state.attempts)} attempt(s)."
    )

    baseline_scan = _latest(values, "baseline-scan")
    working_scan = _latest(values, "working-scan")
    if baseline_scan is not None or working_scan is not None:
        print("  Inventory:")
        if baseline_scan is not None:
            _print_inventory("Baseline", baseline_scan)
        if working_scan is not None:
            _print_inventory("Initial working collection", working_scan)

    baseline_validation = _latest(values, "baseline-validation", successful=False)
    final_validation = _latest(
        values, "final-working-validation", successful=False
    ) or _latest(values, "working-validation", successful=False)
    if baseline_validation is not None or final_validation is not None:
        print("  Health:")
        if baseline_validation is not None:
            _print_health("Baseline", baseline_validation)
        if final_validation is not None:
            _print_health("Latest working collection", final_validation)

    transformations = _applied_transformations(values)
    if transformations:
        labels = {
            "extension-correction": ("extension correction", "extension corrections"),
            "organization": ("organization move", "organization moves"),
            "rename": ("canonical rename", "canonical renames"),
        }
        rendered = ", ".join(
            _count_phrase(item["files"], *labels[item["operation"]])
            for item in transformations
        )
        print(f"  Applied transformations: {rendered}.")

    duplicates = _duplicate_results(values)
    if duplicates:
        rendered = ", ".join(
            f"{_count_phrase(outcome['data']['extra_copies'], 'duplicate copy', 'duplicate copies')} "
            f"of {outcome['data']['media_kind']} content "
            f"{'isolated' if outcome['result_kind'] == 'observed' else 'identified in preview'} "
            f"across {_count_phrase(outcome['data']['groups'], 'group', 'groups')}"
            for outcome in duplicates
        )
        print(f"  Exact duplicates: {rendered}.")
        simulation = _latest(values, "without-dups-simulation")
        review_files = sum(outcome["data"]["extra_copies"] for outcome in duplicates)
        review_bytes = sum(outcome["data"]["duplicate_bytes"] for outcome in duplicates)
        if simulation is not None:
            review_files = simulation["data"]["review_files"]
            review_bytes = simulation["data"]["review_bytes"]
        quarantine_confirmed = any(
            attempt.action == "confirm-quarantine" for attempt in state.attempts
        )
        if quarantine_confirmed:
            print(
                "  Duplicate review storage before external retention: "
                f"{review_files} file(s), {format_bytes(review_bytes)} isolated "
                "from the working collection."
            )
            print(
                "  External retention: confirmed by the operator; pymo did not "
                "inspect the retained destination or prove physical storage reclaimed."
            )
        else:
            print(
                f"  Duplicate review storage: {review_files} file(s), "
                f"{format_bytes(review_bytes)} potentially reclaimable from the working "
                "collection."
            )
            print("  External retention: pending; no storage reclamation is claimed.")

        cache_results = [outcome["data"]["cache"] for outcome in duplicates]
        print(
            "  Duplicate-analysis cache: "
            f"{sum(item['reused'] for item in cache_results)} reusable record(s), "
            f"{sum(item['computed'] for item in cache_results)} computed, "
            f"{sum(item['persisted'] for item in cache_results)} persisted."
        )

    _print_warnings(final_validation)

    final_verification = _latest(values, "final-verification", successful=False)
    latest_verification = final_verification or _latest(
        values,
        "without-dups-simulation",
        "video-duplicates-verification",
        "image-duplicates-verification",
        "rename-verification",
        "organize-verification",
        "extension-verification",
        "initial-verification",
        successful=False,
    )
    if latest_verification is not None:
        data = latest_verification["data"]
        label = (
            "Simulated preservation"
            if latest_verification["result_kind"] == "simulated"
            else "Observed preservation"
        )
        print(
            f"  {label}: {data['verdict'].upper()}; "
            f"{data['accounted_unique_streams']}/{data['source_unique_streams']} "
            f"unique source stream(s) accounted; disposition "
            f"{data['disposition']}."
        )
        if data["reasons"]:
            print(f"    Reasons: {', '.join(data['reasons'])}.")

    print(
        "  Scope: summary of recorded stage outcomes, not new preservation evidence "
        "or authority to delete retained content."
    )
