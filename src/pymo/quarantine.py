"""CLI for reversible same-filesystem duplicate-review quarantine."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pymo.action_log import ActionLogError
from pymo.logging_config import emit as print
from pymo.managed_quarantine import (
    ManagedQuarantineError,
    QuarantinePlan,
    QuarantineUndoPlan,
    apply_managed_quarantine,
    apply_managed_quarantine_undo,
    destination_binding_sha256,
    plan_managed_quarantine,
    plan_managed_quarantine_undo,
    reconcile_managed_quarantine,
)
from pymo.migration.outcome import (
    MigrationOutcomeError,
    ResultKind,
    add_outcome_argument,
    decision_digest,
    decision_digest_matches,
    outcome_record,
    write_outcome,
)


def _plan_data(
    plan: QuarantinePlan | QuarantineUndoPlan,
    *,
    status: int = 0,
    operation: str | None = None,
) -> dict[str, int | str]:
    manifest = plan.manifest
    destination_sha256 = destination_binding_sha256(plan.target)
    digest = decision_digest(
        operation
        or (
            "managed-quarantine"
            if isinstance(plan, QuarantinePlan)
            else "managed-restore"
        ),
        [
            {
                "files": manifest.file_count,
                "directories": manifest.directory_count,
                "bytes": manifest.total_bytes,
                "manifest_sha256": manifest.sha256,
                "destination_sha256": destination_sha256,
                "destination_parent_device": plan.target_parent_device,
                "destination_parent_inode": plan.target_parent_inode,
            }
        ],
    )
    return {
        "status": status,
        "files": manifest.file_count,
        "directories": manifest.directory_count,
        "bytes": manifest.total_bytes,
        "manifest_sha256": manifest.sha256,
        "destination_sha256": destination_sha256,
        "destination_parent_device": plan.target_parent_device,
        "destination_parent_inode": plan.target_parent_inode,
        "decision_digest": digest,
    }


def _write_outcome(
    path: Path | None,
    data: dict[str, int | str],
    *,
    result_kind: ResultKind,
    collection: Path,
) -> None:
    write_outcome(
        path,
        outcome_record(
            "quarantine-dups", "quarantine", result_kind, int(data["status"]), data
        ),
        collection,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Atomically retain one complete dups tree elsewhere on the same filesystem."
    )
    parser.add_argument("collection", type=Path)
    parser.add_argument("destination", type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--undo", action="store_true")
    action.add_argument("--recover", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--apply", action="store_true")
    add_outcome_argument(parser)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.recover and not args.apply:
        print("--recover requires --apply.", file=sys.stderr)
        return 2
    try:
        if args.recover:
            try:
                result = reconcile_managed_quarantine(args.collection, args.destination)
            except ManagedQuarantineError:
                # A failed child may have stopped before opening a journal run.
                # Re-enter the ordinary apply boundary; it will still parse any
                # existing journal strictly and revalidate the complete tree.
                recovery_plan = plan_managed_quarantine(
                    args.collection, args.destination
                )
                data = _plan_data(recovery_plan)
                if not decision_digest_matches(
                    args.migration_decision_digest, str(data["decision_digest"])
                ):
                    print(
                        "Managed quarantine plan changed after review; nothing was moved.",
                        file=sys.stderr,
                    )
                    return 1
                result = apply_managed_quarantine(recovery_plan)
            if not result.disposition_complete:
                recovery_plan = plan_managed_quarantine(
                    args.collection, args.destination
                )
                data = _plan_data(recovery_plan)
                if not decision_digest_matches(
                    args.migration_decision_digest, str(data["decision_digest"])
                ):
                    print(
                        "Managed quarantine plan changed after review; nothing was moved.",
                        file=sys.stderr,
                    )
                    return 1
                result = apply_managed_quarantine(recovery_plan)
            print(
                "Reconciled one interrupted managed-quarantine journal lifecycle; "
                f"verified {result.file_count} file(s), {result.total_bytes} byte(s)."
            )
            if result.direction == "quarantine" and args.migration_outcome is not None:
                observed = plan_managed_quarantine_undo(
                    args.collection, args.destination
                )
                data = _plan_data(observed, operation="managed-quarantine")
                if not decision_digest_matches(
                    args.migration_decision_digest, str(data["decision_digest"])
                ):
                    print(
                        "Managed quarantine plan changed after review; nothing was claimed complete.",
                        file=sys.stderr,
                    )
                    return 1
                _write_outcome(
                    args.migration_outcome,
                    data,
                    result_kind="observed",
                    collection=observed.collection_root,
                )
            return 0
        plan = (
            plan_managed_quarantine_undo(args.collection, args.destination)
            if args.undo
            else plan_managed_quarantine(args.collection, args.destination)
        )
        data = _plan_data(plan)
        expected = args.migration_decision_digest
        if args.apply and not decision_digest_matches(
            expected, str(data["decision_digest"])
        ):
            print(
                "Managed quarantine plan changed after review; nothing was moved.",
                file=sys.stderr,
            )
            return 1
        result_kind: ResultKind
        if args.apply:
            result = (
                apply_managed_quarantine_undo(plan)
                if isinstance(plan, QuarantineUndoPlan)
                else apply_managed_quarantine(plan)
            )
            if result.manifest_sha256 != data["manifest_sha256"]:
                raise ManagedQuarantineError(
                    "managed quarantine result did not match its reviewed manifest"
                )
            print(
                f"Verified atomic {'restoration' if args.undo else 'retention'} of "
                f"{result.file_count} file(s), {result.total_bytes} byte(s)."
            )
            result_kind = "observed"
        else:
            print(
                f"Would atomically {'restore' if args.undo else 'retain'} "
                f"{plan.manifest.file_count} file(s), {plan.manifest.total_bytes} byte(s) "
                "on the same filesystem."
            )
            print("Dry run only. Add --apply after reviewing this exact plan.")
            result_kind = "preview"
        _write_outcome(
            args.migration_outcome,
            data,
            result_kind=result_kind,
            collection=plan.collection_root,
        )
        return 0
    except (ActionLogError, ManagedQuarantineError, MigrationOutcomeError, OSError):
        print(
            "Managed quarantine could not safely continue; nothing is claimed complete.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
