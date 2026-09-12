"""Stable aggregate migration report and human synopsis projection."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pymo.logging_config import emit as print
from pymo.migration.coordinator_state import Attempt, MigrationState
from pymo.migration.outcome import MigrationOutcomeError, read_outcome
from pymo.migration.workflow import Stage, _stages
from pymo.progress import format_bytes, format_duration

# This identifies the public machine-readable migration-report contract. A
# schema change is required before any field, type, or meaning may change.
MIGRATION_REPORT_SCHEMA_VERSION = 1


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


def _workflow_status(state: MigrationState) -> str:
    if state.next_stage == 0 and not state.attempts:
        return "not-started"
    if state.next_stage == len(_stages()):
        return "complete"
    if state.attempts:
        latest = state.attempts[-1]
        if latest.action == "run" and latest.exit_status != 0:
            return "stopped"
    return "pending"


def _workflow_label(workflow: dict[str, Any]) -> str:
    status = workflow["status"]
    if status == "not-started":
        return "not started"
    if status == "complete":
        return (
            "complete and signed off"
            if workflow["human_signoff_recorded"]
            else "complete; human sign-off pending"
        )
    if status == "stopped":
        return (
            f"stopped at {workflow['stopped_stage']} "
            f"(exit {workflow['latest_exit_status']})"
        )
    return f"pending at {workflow['next_stage']}"


def _print_inventory(label: str, data: dict[str, Any]) -> None:
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


def _print_health(label: str, data: dict[str, Any]) -> None:
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
    return [outcome for name in names if (outcome := _latest(values, name)) is not None]


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
    findings = validation["findings"]
    if not findings:
        print("  Latest working validation findings: none.")
        return
    rendered = ", ".join(
        f"{item['code']}={item['count']} ({item['severity']})" for item in findings
    )
    print(f"  Latest working validation findings: {rendered}.")


def _cache_counts(data: dict[str, Any]) -> dict[str, Any]:
    cache = data["cache"]
    return {
        "enabled": cache["enabled"],
        "reused": cache["reused"],
        "computed": cache["computed"],
        "persisted": cache["persisted"],
    }


def _inventory_data(outcome: dict[str, Any] | None) -> dict[str, Any] | None:
    if outcome is None:
        return None
    data = outcome["data"]
    return {
        "result_kind": outcome["result_kind"],
        "status": outcome["status"],
        **{
            field: data[field]
            for field in (
                "files",
                "directories",
                "bytes",
                "pictures",
                "videos",
                "audio",
                "other",
                "unknown",
                "ignored",
                "symbolic_links",
                "unreadable",
                "changed",
            )
        },
    }


def _finding_data(item: dict[str, Any]) -> dict[str, Any]:
    code = item["code"]
    if code not in {
        "additional_streams",
        "changed_during_discovery",
        "changed_during_validation",
        "classification_fallback",
        "container_extension_mismatch",
        "empty_file",
        "extension_content_mismatch",
        "invalid_image",
        "invalid_video",
        "invalid_video_dimensions",
        "missing_or_invalid_duration",
        "missing_video_codec",
        "missing_video_stream",
        "multiple_audio_streams",
        "multiple_video_streams",
        "symbolic_link_skipped",
        "unreadable_entry",
        "unrecognized_media_extension",
        "unsupported_image_format",
    }:
        raise MigrationSynopsisError(
            "migration synopsis cannot expose an unsafe finding code"
        )
    return {
        "severity": item["severity"],
        "code": code,
        "count": item["count"],
    }


def _health_data(outcome: dict[str, Any] | None) -> dict[str, Any] | None:
    if outcome is None:
        return None
    data = outcome["data"]
    return {
        "result_kind": outcome["result_kind"],
        "status": outcome["status"],
        **{
            field: data[field]
            for field in (
                "media_files",
                "media_bytes",
                "pictures",
                "videos",
                "other_files",
                "symbolic_links",
                "unreadable",
                "changed",
                "healthy",
                "warning_only",
                "errors",
            )
        },
        "findings": [_finding_data(item) for item in data["findings"]],
        "cache": _cache_counts(data),
    }


def _transformation_data(outcome: dict[str, Any]) -> dict[str, Any]:
    data = outcome["data"]
    return {
        "result_kind": outcome["result_kind"],
        "status": outcome["status"],
        **{
            field: data[field]
            for field in (
                "operation",
                "files",
                "directories_created",
                "directories_removed",
            )
        },
    }


def _duplicate_data(outcome: dict[str, Any]) -> dict[str, Any]:
    data = outcome["data"]
    return {
        "result_kind": outcome["result_kind"],
        "status": outcome["status"],
        **{
            field: data[field]
            for field in (
                "media_kind",
                "scanned_files",
                "scanned_bytes",
                "groups",
                "extra_copies",
                "duplicate_bytes",
                "skipped",
            )
        },
        "cache": _cache_counts(data),
    }


def _preservation_data(outcome: dict[str, Any] | None) -> dict[str, Any] | None:
    if outcome is None:
        return None
    data = outcome["data"]
    return {
        "result_kind": outcome["result_kind"],
        "status": outcome["status"],
        **{
            field: data[field]
            for field in (
                "source_files",
                "source_bytes",
                "source_unique_streams",
                "accounted_unique_streams",
                "accounted_source_files",
                "unaccounted_unique_streams",
                "unaccounted_source_files",
                "unsupported_unique_streams",
                "unsupported_source_files",
                "destination_files",
                "destination_bytes",
                "review_files",
                "review_bytes",
                "verdict",
                "disposition",
            )
        },
        "reasons": list(data["reasons"]),
    }


def build_report(log_dir: Path, state: MigrationState) -> dict[str, Any]:
    """Project strict private outcomes into the stable aggregate report schema."""

    values = _outcomes(log_dir, state)
    run_attempts = [attempt for attempt in state.attempts if attempt.action == "run"]
    workflow_status = _workflow_status(state)
    latest_attempt = state.attempts[-1] if state.attempts else None
    next_stage = (
        None
        if state.next_stage == len(_stages())
        else _stages()[state.next_stage].identifier
    )
    stopped_stage = (
        latest_attempt.stage
        if workflow_status == "stopped" and latest_attempt is not None
        else None
    )
    latest_exit_status = (
        latest_attempt.exit_status
        if workflow_status == "stopped" and latest_attempt is not None
        else None
    )

    baseline_scan = _latest(values, "baseline-scan")
    working_scan = _latest(values, "working-scan")
    baseline_validation = _latest(values, "baseline-validation", successful=False)
    final_validation = _latest(
        values, "final-working-validation", successful=False
    ) or _latest(values, "working-validation", successful=False)

    transformations = _applied_transformations(values)
    duplicate_outcomes = _duplicate_results(values)
    duplicates = [_duplicate_data(outcome) for outcome in duplicate_outcomes]
    simulation = _latest(values, "without-dups-simulation")
    review_files = sum(outcome["extra_copies"] for outcome in duplicates)
    review_bytes = sum(outcome["duplicate_bytes"] for outcome in duplicates)
    if simulation is not None:
        review_files = simulation["data"]["review_files"]
        review_bytes = simulation["data"]["review_bytes"]
    quarantine_confirmed = any(
        attempt.action == "confirm-quarantine" for attempt in state.attempts
    )
    review_state = (
        "external-retention-confirmed-unverified"
        if quarantine_confirmed
        else "potentially-reclaimable" if duplicates else "not-assessed"
    )
    cache_results = [outcome["cache"] for outcome in duplicates]

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
    preservation = _preservation_data(latest_verification)

    return {
        "schema_version": MIGRATION_REPORT_SCHEMA_VERSION,
        "report_type": "pymo-migration-report",
        "tool_version": state.tool_version,
        "workflow": {
            "status": workflow_status,
            "completed_stages": state.next_stage,
            "total_stages": len(_stages()),
            "next_stage": next_stage,
            "stopped_stage": stopped_stage,
            "latest_exit_status": latest_exit_status,
            "validation_reviews_recorded": sum(
                attempt.action in {"acknowledge-review", "acknowledge-status"}
                for attempt in state.attempts
            ),
            "status_one_validations_acknowledged": sum(
                attempt.action == "acknowledge-status" for attempt in state.attempts
            ),
            "external_quarantine_confirmed": quarantine_confirmed,
            "human_signoff_recorded": any(
                attempt.action == "signoff" for attempt in state.attempts
            ),
        },
        "observed_child_work": {
            "attempts": len(run_attempts),
            "duration_milliseconds": sum(
                attempt.duration_milliseconds for attempt in run_attempts
            ),
        },
        "inventory": {
            "baseline": _inventory_data(baseline_scan),
            "initial_working": _inventory_data(working_scan),
        },
        "health": {
            "baseline": _health_data(baseline_validation),
            "latest_working": _health_data(final_validation),
        },
        "applied_transformations": [
            _transformation_data(item) for item in transformations
        ],
        "exact_duplicates": {
            "analyses": duplicates,
            "review_storage": {
                "files": review_files,
                "bytes": review_bytes,
                "state": review_state,
                "physical_storage_reclaimed": False,
            },
            "cache": {
                "reused": sum(item["reused"] for item in cache_results),
                "computed": sum(item["computed"] for item in cache_results),
                "persisted": sum(item["persisted"] for item in cache_results),
            },
        },
        "preservation": preservation,
        "scope": {
            "basis": "validated-private-stage-outcomes",
            "fresh_evidence": False,
            "collection_writes": False,
            "action_history_writes": False,
            "deletion_authority": False,
            "whole_device_recovery": False,
        },
    }


def print_synopsis(log_dir: Path, state: MigrationState) -> None:
    report = build_report(log_dir, state)
    workflow = report["workflow"]
    work = report["observed_child_work"]
    print("\nMigration synopsis")
    print(f"  Workflow: {_workflow_label(workflow)}.")
    print(
        f"  Observed child work: "
        f"{format_duration(work['duration_milliseconds'] / 1000)} across "
        f"{work['attempts']} attempt(s)."
    )

    baseline_scan = report["inventory"]["baseline"]
    working_scan = report["inventory"]["initial_working"]
    if baseline_scan is not None or working_scan is not None:
        print("  Inventory:")
        if baseline_scan is not None:
            _print_inventory("Baseline", baseline_scan)
        if working_scan is not None:
            _print_inventory("Initial working collection", working_scan)

    baseline_validation = report["health"]["baseline"]
    final_validation = report["health"]["latest_working"]
    if baseline_validation is not None or final_validation is not None:
        print("  Health:")
        if baseline_validation is not None:
            _print_health("Baseline", baseline_validation)
        if final_validation is not None:
            _print_health("Latest working collection", final_validation)

    transformations = report["applied_transformations"]
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

    duplicates = report["exact_duplicates"]["analyses"]
    if duplicates:
        rendered = ", ".join(
            f"{_count_phrase(outcome['extra_copies'], 'duplicate copy', 'duplicate copies')} "
            f"of {outcome['media_kind']} content "
            f"{'isolated' if outcome['result_kind'] == 'observed' else 'identified in preview'} "
            f"across {_count_phrase(outcome['groups'], 'group', 'groups')}"
            for outcome in duplicates
        )
        print(f"  Exact duplicates: {rendered}.")
        review = report["exact_duplicates"]["review_storage"]
        if review["state"] == "external-retention-confirmed-unverified":
            print(
                "  Duplicate review storage before external retention: "
                f"{review['files']} file(s), {format_bytes(review['bytes'])} isolated "
                "from the working collection."
            )
            print(
                "  External retention: confirmed by the operator; pymo did not "
                "inspect the retained destination or prove physical storage reclaimed."
            )
        else:
            print(
                f"  Duplicate review storage: {review['files']} file(s), "
                f"{format_bytes(review['bytes'])} potentially reclaimable from the working "
                "collection."
            )
            print("  External retention: pending; no storage reclamation is claimed.")

        cache = report["exact_duplicates"]["cache"]
        print(
            "  Duplicate-analysis cache: "
            f"{cache['reused']} reusable record(s), "
            f"{cache['computed']} computed, "
            f"{cache['persisted']} persisted."
        )

    _print_warnings(final_validation)

    latest_verification = report["preservation"]
    if latest_verification is not None:
        label = (
            "Simulated preservation"
            if latest_verification["result_kind"] == "simulated"
            else "Observed preservation"
        )
        print(
            f"  {label}: {latest_verification['verdict'].upper()}; "
            f"{latest_verification['accounted_unique_streams']}/"
            f"{latest_verification['source_unique_streams']} "
            f"unique source stream(s) accounted; disposition "
            f"{latest_verification['disposition']}."
        )
        if latest_verification["reasons"]:
            print(f"    Reasons: {', '.join(latest_verification['reasons'])}.")

    print(
        "  Scope: summary of recorded stage outcomes, not new preservation evidence "
        "or authority to delete retained content."
    )
