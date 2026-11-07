"""Fresh root, namespace and byte binding for authored policy schema 5."""

from __future__ import annotations

from typing import Any

from pymo.config import load_config
from pymo.migration.coordinator_state import MigrationState
from pymo.migration.preauthorization import (
    MigrationPreauthorizationError,
    _require_exact_fields,
    _validate_sha256,
)
from pymo.migration.virtual import inventory, namespace_digest
from pymo.migration.workflow import _stages


def validate_plan_binding(value: object) -> dict[str, Any]:
    result = _require_exact_fields(
        value,
        {"baseline_initial", "working_initial", "working_stages", "configuration"},
        "authored plan binding",
    )
    for key in ("baseline_initial", "working_initial", "configuration"):
        _validate_sha256(result[key], key)
    stages = result["working_stages"]
    if not isinstance(stages, list) or len(stages) != len(_stages()) + 1:
        raise MigrationPreauthorizationError(
            "authored policy has incomplete namespace stages"
        )
    for item in stages:
        _validate_sha256(item, "stage namespace")
    return result


def require_plan_binding(value: dict[str, Any], state: MigrationState) -> None:
    from pathlib import Path

    from pymo.migration.policy_plan import configuration_binding

    try:
        if (
            not state.options.no_cache
            or state.options.quarantine_destination is not None
        ):
            raise MigrationPreauthorizationError(
                "unsupported authored execution options"
            )
        config_path = Path(state.options.config) if state.options.config else None
        baseline_config = load_config(state.baseline, config_path)
        working_config = load_config(state.working, config_path)
        baseline = inventory(state.baseline, baseline_config)
        working = inventory(state.working, working_config)
        if (
            namespace_digest(baseline, initial=True) != value["baseline_initial"]
            or namespace_digest(working) != value["working_stages"][state.next_stage]
            or configuration_binding((state.baseline, state.working), state.options)
            != value["configuration"]
            or (
                state.next_stage
                <= next(
                    index
                    for index, stage in enumerate(_stages())
                    if stage.mode == "apply"
                )
                and namespace_digest(working, initial=True) != value["working_initial"]
            )
        ):
            raise MigrationPreauthorizationError(
                "authored policy target evidence changed"
            )
    except (OSError, ValueError, RuntimeError) as error:
        raise MigrationPreauthorizationError(
            "authored policy target evidence cannot be verified"
        ) from error
