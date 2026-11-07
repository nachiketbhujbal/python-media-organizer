"""Whole-queue binding validation and an aggregate, non-authoritative plan."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pymo import __version__
from pymo.managed_quarantine import destination_binding_sha256
from pymo.migration.policy_acceptance import receipt_path
from pymo.migration.preauthorization import (
    _CHECKPOINT_ORDER,
    MigrationPreauthorization,
    parse_preauthorization,
)
from pymo.migration.queue_manifest import (
    Endpoint,
    PrivateArtifact,
    QueueJob,
    QueuePlanningError,
    absolute_path,
    endpoints_overlap,
    observe_endpoint,
    parse_manifest,
    private_state_destination,
)
from pymo.migration.workflow import _stages

# Public planning projection, separate from future queue execution/outcome reports.
QUEUE_PLAN_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BoundJob:
    declaration: QueueJob
    policy: MigrationPreauthorization
    endpoints: tuple[Endpoint, ...]
    artifacts: tuple[PrivateArtifact, ...]
    controls: tuple[Endpoint, ...]


def _declared_endpoints(job: QueueJob) -> tuple[Endpoint, ...]:
    baseline = observe_endpoint(job.baseline)
    working = observe_endpoint(job.working)
    state = private_state_destination(job.state_directory)
    if (
        baseline.identity != job.baseline_identity
        or working.identity != job.working_identity
    ):
        raise QueuePlanningError("a collection identity differs from its declaration")
    endpoints: tuple[Endpoint, ...] = (baseline, working, state)
    if job.quarantine_destination is not None:
        endpoints += (observe_endpoint(job.quarantine_destination, missing=True),)
    return endpoints


def _bind_job(job: QueueJob, endpoints: tuple[Endpoint, ...]) -> BoundJob:
    working = endpoints[1]
    artifact = PrivateArtifact.read(job.policy)
    if len(artifact.payload) > 1024 * 1024:
        raise QueuePlanningError("policy exceeds its supported size")
    if hashlib.sha256(artifact.payload).hexdigest() != job.policy_sha256:
        raise QueuePlanningError("policy bytes differ from the declared digest")
    policy = parse_preauthorization(job.policy, artifact.payload, artifact.identity)
    if (
        policy.tool_version != __version__
        or policy.baseline != job.baseline
        or policy.working != job.working
        or tuple(policy.authorizations) != tuple(_CHECKPOINT_ORDER)
    ):
        raise QueuePlanningError("policy does not bind this complete workflow")
    artifacts = [artifact]
    if policy.acceptance is not None:
        artifacts.append(PrivateArtifact.read(receipt_path(job.policy)))
    controls: list[Endpoint] = []
    for key in ("config", "ffmpeg", "ffprobe"):
        value = policy.options[key]
        if value is not None:
            path = absolute_path(value)
            # No configuration or native executable is opened or executed here.
            controls.append(observe_endpoint(path.parent))
    desired = {
        "retained-in-place": "retain-dups",
        "external-quarantine": "confirm-quarantine",
        "managed-same-filesystem": "quarantine-dups",
        "retained-copy": "quarantine-dups",
    }[job.disposition]
    decision, expected = policy.authorizations["duplicate-disposition"]
    if (
        decision != desired
        or policy.options["quarantine_destination"]
        != (str(job.quarantine_destination) if job.quarantine_destination else None)
        or policy.options["quarantine_copy_reserve_bytes"] != job.copy_reserve_bytes
    ):
        raise QueuePlanningError("duplicate disposition conflicts with the policy")
    if job.quarantine_destination is not None:
        target = endpoints[3]
        planned = expected["quarantine_plan"]
        copy = job.disposition == "retained-copy"
        if (
            planned["method"] != ("copy" if copy else "rename")
            or planned["copy_reserve_bytes"] != (job.copy_reserve_bytes if copy else 0)
            or planned["destination_sha256"] != destination_binding_sha256(target.path)
            or (
                planned["destination_parent_device"],
                planned["destination_parent_inode"],
            )
            != target.identity
        ):
            raise QueuePlanningError(
                "quarantine target differs from the policy binding"
            )
        # This is declared topology, not a tree manifest/capacity verification.
        # A currently mounted review directory can differ from its collection.
        review = job.working / "dups"
        try:
            review.lstat()
        except FileNotFoundError:
            controls.append(observe_endpoint(review, missing=True))
            source_device = working.identity[0]
        else:
            review_endpoint = observe_endpoint(review)
            controls.append(review_endpoint)
            source_device = review_endpoint.identity[0]
        if (source_device == target.identity[0]) == copy:
            raise QueuePlanningError(
                "quarantine method conflicts with current filesystem topology"
            )
    return BoundJob(job, policy, endpoints, tuple(artifacts), tuple(controls))


def _require_separation(endpoints: list[Endpoint], parents: list[Endpoint]) -> None:
    for index, endpoint in enumerate(endpoints):
        if any(endpoints_overlap(endpoint, prior) for prior in endpoints[:index]):
            raise QueuePlanningError("queue roots or destinations overlap")
    # A shared private parent is fine. The artifact itself may never live under
    # any collection, and an existing artifact cannot occupy an absent target.
    for endpoint in endpoints:
        if not endpoint.missing and any(
            endpoint.identity in parent.ancestry for parent in parents
        ):
            raise QueuePlanningError(
                "control artifacts must be outside every collection"
            )


def _steps(policy: MigrationPreauthorization) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for stage in _stages():
        authorization = policy.authorizations.get(stage.identifier)
        steps.append(
            {
                "stage": stage.identifier,
                "mode": stage.mode,
                "target": stage.target,
                "decision": authorization[0] if authorization else None,
            }
        )
        if stage.identifier == "duplicate-disposition" and authorization is not None:
            if authorization[0] == "quarantine-dups":
                steps.extend(
                    [
                        {
                            "stage": "quarantine-preview",
                            "mode": "preview",
                            "target": "working",
                            "decision": None,
                        },
                        {
                            "stage": "quarantine-apply",
                            "mode": "apply",
                            "target": "working",
                            "decision": "apply",
                        },
                    ]
                )
    steps.append(
        {
            "stage": "final-signoff",
            "mode": "checkpoint",
            "target": "checkpoint",
            "decision": "signoff",
        }
    )
    return steps


def build_queue_plan(path: Path) -> dict[str, Any]:
    """Read control files and filesystem metadata only; never dispatch work."""
    manifest = PrivateArtifact.read(absolute_path(str(path.expanduser().absolute())))
    declarations = parse_manifest(manifest)
    endpoint_groups = tuple(_declared_endpoints(job) for job in declarations)
    endpoints = [endpoint for group in endpoint_groups for endpoint in group]
    parents = [
        manifest.parent,
        *(observe_endpoint(job.policy.parent) for job in declarations),
    ]
    # Refuse cross-job artifact placement before opening any policy/receipt.
    _require_separation(endpoints, parents)
    jobs = tuple(
        _bind_job(job, group)
        for job, group in zip(declarations, endpoint_groups, strict=True)
    )
    for job in jobs:
        for key in ("config", "ffmpeg", "ffprobe"):
            value = job.policy.options[key]
            if value is not None:
                parents.append(observe_endpoint(absolute_path(value).parent))
    _require_separation(endpoints, parents)
    result: dict[str, Any] = {
        "schema_version": QUEUE_PLAN_SCHEMA_VERSION,
        "kind": "queue-plan",
        "execution": "not-started",
        "ordering": "sequential",
        "media_evidence": "not-checked",
        "capacity": "not-checked",
        "destinations_reserved": False,
        "authority_created": False,
        "jobs": [
            {
                "ordinal": index,
                "disposition": job.declaration.disposition,
                "policy_kind": "authored" if job.policy.acceptance else "manual",
                "cache": "disabled" if job.policy.options["no_cache"] else "enabled",
                "human_external_quarantine_required": job.declaration.disposition
                == "external-quarantine",
                "steps": _steps(job.policy),
            }
            for index, job in enumerate(jobs, 1)
        ],
    }
    # No successful output until every declaration and dependency is rechecked.
    for job in jobs:
        for endpoint in (*job.endpoints, *job.controls):
            endpoint.require_current()
        private_state_destination(job.declaration.state_directory)
        for artifact in job.artifacts:
            artifact.require_current()
        if job.policy.acceptance is not None:
            job.policy.acceptance.require_current()
    manifest.require_current()
    return result
