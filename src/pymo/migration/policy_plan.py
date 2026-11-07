"""Compose the fixed migration workflow without applying any transition."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pymo import __version__, correct_extensions, organize, rename
from pymo.cache.hashes import sha256_descriptor
from pymo.classification import Classifier
from pymo.collection import CollectionLayout
from pymo.config import load_config
from pymo.file_safety import FileState, open_stable_file
from pymo.logging_config import emit
from pymo.migration import plan_analysis
from pymo.migration.preauthorization import MIGRATION_PREAUTHORIZATION_SCHEMA_VERSION
from pymo.migration.roots import existing_directories_are_disjoint
from pymo.migration.virtual import (
    PolicyPlanningError,
    VirtualCollection,
    digest,
    namespace_digest,
)
from pymo.migration.workflow import CoordinatorOptions, _stages

# Public private-artifact contract; a candidate is never an executable policy.
POLICY_CANDIDATE_SCHEMA_VERSION = 1


def configuration_binding(roots: tuple[Path, Path], options: CoordinatorOptions) -> str:
    values: list[list[str] | None] = []
    for root in roots:
        path = Path(options.config) if options.config else CollectionLayout(root).config
        if not path.exists() and not path.is_symlink():
            values.append(None)
            continue
        state = FileState.capture(path)
        with open_stable_file(path.parent, path, state, "policy configuration") as fd:
            values.append([str(path), sha256_descriptor(fd)])
    return digest(values)


def _transformation(
    operation: str, count: int, decision: str, created: int = 0, removed: int = 0
) -> dict[str, Any]:
    return {
        "status": 0,
        "operation": operation,
        "files": count,
        "directories_created": created,
        "directories_removed": removed,
        "decision_digest": decision,
    }


def _organization(view: VirtualCollection) -> tuple[dict[str, Any], VirtualCollection]:
    root = view.tree.root
    pics, vids = view.layout.pics, view.layout.vids
    for path in (pics, vids):
        if view.exists(path) and path not in view.tree.directories:
            raise PolicyPlanningError("organization destination is occupied")
    plan, _, _, _ = organize.build_plan(
        root,
        pics,
        vids,
        Classifier(view.config.classification),
        view.config,
        view=view,
        show_progress=False,
    )
    create = tuple(p for p in (pics, vids) if not view.exists(p))
    # Extension correction changes no directory namespace. Reuse the real
    # traversal order so the shared decision digest is exact on this filesystem.
    directories = organize.removable_directories(root, pics, vids, view.config)
    evidence = {
        record.source: (
            view.entry(record.source).state,
            view.entry(record.source).sha256,
        )
        for record in plan
    }
    result = _transformation(
        "organization",
        len(plan),
        organize._decision_digest(root, plan, create, directories, evidence),
        len(create),
        len(directories),
    )
    updated = view.move(
        [(r.source, r.target) for r in plan], create=create, remove=tuple(directories)
    )
    return result, updated


def _renaming(view: VirtualCollection) -> tuple[dict[str, Any], VirtualCollection]:
    plan, _, _, _ = rename.build_rename_plan(
        view.tree.root,
        Classifier(view.config.classification),
        view.config,
        view=view,
        show_progress=False,
    )
    evidence = {
        record.source: (
            view.entry(record.source).state,
            view.entry(record.source).sha256,
        )
        for record in plan
    }
    result = _transformation(
        "rename", len(plan), rename._decision_digest(view.tree.root, plan, evidence)
    )
    return result, view.move([(r.source, r.target) for r in plan])


def build_candidate(
    baseline: Path,
    working: Path,
    options: CoordinatorOptions,
    *,
    show_progress: bool = False,
) -> dict[str, Any]:
    if not existing_directories_are_disjoint(baseline, working):
        raise PolicyPlanningError("collections must be distinct and non-nested")
    if (
        options.quarantine_destination is not None
        or options.quarantine_copy_reserve_bytes is not None
    ):
        raise PolicyPlanningError(
            "future managed-quarantine identities cannot be authored safely; use reviewed stage-by-stage operation"
        )
    if not options.no_cache:
        raise PolicyPlanningError(
            "policy authoring requires the explicit no-cache execution profile"
        )
    config_path = Path(options.config) if options.config else None
    baseline_config = load_config(baseline, config_path)
    working_config = load_config(working, config_path)
    config_binding = configuration_binding((baseline, working), options)
    if show_progress:
        emit("Reading current collection bytes for the complete plan.")
    source = VirtualCollection.capture(baseline, baseline_config)
    current = VirtualCollection.capture(working, working_config)
    initial = current
    if any(
        entry.state.device != current.tree.root_identity[0]
        for entry in current.tree.files
    ):
        raise PolicyPlanningError("working collection spans filesystems")
    # Old active journal dependencies cannot be predicted from future names.
    if CollectionLayout(working).action_log in current.tree.tool_state:
        raise PolicyPlanningError(
            "existing working action history requires a separately reviewed workflow"
        )
    initial_binding = namespace_digest(current.tree, initial=True)
    baseline_binding = namespace_digest(source.tree, initial=True)
    expected: dict[str, dict[str, Any]] = {}
    transitions: list[dict[str, Any]] = []
    checkpoints = []
    stage_bindings = []
    simulation: dict[str, Any] | None = None
    pending: VirtualCollection | None = None
    for stage in _stages():
        if show_progress:
            emit(f"Planning stage: {stage.identifier}.")
        stage_bindings.append(namespace_digest(current.tree))
        if stage.identifier in {"baseline-scan", "working-scan"}:
            # Complete stable byte discovery already performed; scan has no decision.
            continue
        if stage.command == "validate":
            result = plan_analysis.validation(
                source if stage.target == "baseline" else current, options
            )
            checkpoints.append(
                {
                    "checkpoint": stage.identifier,
                    "decision": "accept-validation",
                    "expected": result,
                }
            )
        elif stage.command == "verify-migration":
            simulated = stage.identifier == "without-dups-simulation"
            result = plan_analysis.verification(
                source, current, options, simulated=simulated
            )
            if simulated:
                simulation = result
            if stage.identifier == "final-verification":
                checkpoints.append(
                    {
                        "checkpoint": "final-signoff",
                        "decision": "signoff",
                        "expected": result,
                    }
                )
        elif stage.mode == "preview":
            before = current
            if stage.command == "correct-extensions":
                analysis = correct_extensions.analyze_corrections(
                    working,
                    working_config,
                    plan_analysis.native_path(options.ffprobe),
                    show_progress=False,
                )
                if analysis.skipped_links or analysis.uninspectable:
                    raise PolicyPlanningError("extension evidence is incomplete")
                result = _transformation(
                    "extension-correction",
                    len(analysis.plan),
                    correct_extensions._decision_digest(working, analysis.plan),
                )
                pending = current.move([(r.source, r.target) for r in analysis.plan])
            elif stage.command == "organize":
                result, pending = _organization(current)
            elif stage.command == "rename":
                result, pending = _renaming(current)
            elif stage.command == "find-image-duplicates":
                result, pending = plan_analysis.image_duplicates(current)
            else:
                result, pending = plan_analysis.video_duplicates(current, options)
            expected[stage.identifier] = result
            after_by_origin = {e.read_path: e for e in pending.tree.files}
            transitions.append(
                {
                    "stage": stage.identifier,
                    "moves": [
                        {
                            "source": e.path.relative_to(working).as_posix(),
                            "target": after_by_origin[e.read_path]
                            .path.relative_to(working)
                            .as_posix(),
                            "sha256": e.sha256,
                            "bytes": e.size,
                        }
                        for e in before.tree.files
                        if after_by_origin[e.read_path].path != e.path
                    ],
                    "create_directories": sorted(
                        str(p.relative_to(working))
                        for p in set(pending.tree.directories)
                        - set(before.tree.directories)
                    ),
                    "remove_directories": sorted(
                        str(p.relative_to(working))
                        for p in set(before.tree.directories)
                        - set(pending.tree.directories)
                    ),
                }
            )
        elif stage.mode == "apply":
            preview = stage.identifier.replace("-apply", "-preview")
            checkpoints.append(
                {
                    "checkpoint": stage.identifier,
                    "decision": "apply",
                    "expected": expected[preview],
                }
            )
            if pending is None:
                raise PolicyPlanningError("missing virtual transition")
            current = pending
            pending = None
        elif stage.identifier == "duplicate-disposition":
            if simulation is None:
                raise PolicyPlanningError("missing simulated preservation")
            result = {
                field: simulation[field]
                for field in (
                    "status",
                    "review_files",
                    "review_bytes",
                    "verdict",
                    "disposition",
                )
            }
            checkpoints.append(
                {
                    "checkpoint": stage.identifier,
                    "decision": "retain-dups",
                    "expected": result,
                }
            )
        else:
            raise PolicyPlanningError("unsupported workflow stage")
    stage_bindings.append(namespace_digest(current.tree))
    source.require_current()
    initial.require_current()
    if (
        namespace_digest(source.physical, initial=True) != baseline_binding
        or namespace_digest(initial.physical, initial=True) != initial_binding
    ):
        raise PolicyPlanningError("initial namespace changed during planning")
    if configuration_binding((baseline, working), options) != config_binding:
        raise PolicyPlanningError("configuration changed during planning")
    binding = {
        "baseline_initial": baseline_binding,
        "working_initial": initial_binding,
        "working_stages": stage_bindings,
        "configuration": config_binding,
    }
    policy = {
        "schema_version": MIGRATION_PREAUTHORIZATION_SCHEMA_VERSION,
        "tool_version": __version__,
        "baseline": str(baseline),
        "working": str(working),
        "options": options.as_json(),
        "authorizations": checkpoints,
        "plan_binding": binding,
    }
    return {
        "schema_version": POLICY_CANDIDATE_SCHEMA_VERSION,
        "kind": "unaccepted-migration-plan",
        "policy": policy,
        "transitions": transitions,
    }
