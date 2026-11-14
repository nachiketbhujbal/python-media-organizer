"""CLI for retained duplicate-review movement or explicit copying."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pymo.action_log import ActionLogError, NoUndoableRun
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
from pymo.migration.private_io import PrivateIO
from pymo.quarantine_copy import (
    CopyPlan,
    NoRetainedCopy,
    apply_copy,
    inspect_copy_source,
    plan_copy,
    recover_copy,
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
        "method": "rename",
        "copy_reserve_bytes": 0,
        "metadata_entries": 0,
        "metadata_unknown": 0,
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
    private_io: PrivateIO | None = None,
) -> None:
    write_outcome(
        path,
        outcome_record(
            "quarantine-dups", "quarantine", result_kind, int(data["status"]), data
        ),
        collection,
        private_io=private_io,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retain one complete dups tree by same-filesystem move or explicit cross-filesystem copy."
    )
    parser.add_argument("collection", type=Path)
    parser.add_argument("destination", type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--undo", action="store_true")
    action.add_argument("--recover", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy across filesystems; retain all originals.",
    )
    parser.add_argument(
        "--copy-reserve-bytes",
        type=int,
        help="Explicit free-space reserve required after staged copying.",
    )
    add_outcome_argument(parser)
    args = parser.parse_args(argv)
    if args.copy != (args.copy_reserve_bytes is not None):
        parser.error("--copy requires an explicit --copy-reserve-bytes value")
    if args.copy_reserve_bytes is not None and args.copy_reserve_bytes < 0:
        parser.error("--copy-reserve-bytes must be nonnegative")
    if args.copy and args.undo:
        parser.error(
            "retained copying has no destructive undo; both copies remain retained"
        )
    return args


def _copy_data(plan: CopyPlan) -> dict[str, int | str]:
    data: dict[str, int | str] = {
        "method": "copy",
        "copy_reserve_bytes": plan.reserve_bytes,
        "metadata_entries": plan.evidence.metadata_entries,
        "metadata_unknown": plan.evidence.metadata_unknown,
        "status": 0,
        "files": plan.evidence.files,
        "directories": plan.evidence.directories,
        "bytes": plan.evidence.total_bytes,
        "manifest_sha256": plan.source.sha256,
        "destination_sha256": destination_binding_sha256(plan.target),
        "destination_parent_device": plan.target_parent_identity[0],
        "destination_parent_inode": plan.target_parent_identity[1],
    }
    data["decision_digest"] = decision_digest(
        "copy-quarantine",
        [
            {
                **data,
                "content_sha256": plan.evidence.sha256,
                "collection_device": plan.collection_identity[0],
                "collection_inode": plan.collection_identity[1],
            }
        ],
    )
    return data


def _copy_main(args: argparse.Namespace) -> int:
    if args.recover:
        plan = inspect_copy_source(
            args.collection, args.destination, args.copy_reserve_bytes
        )
    else:
        plan = plan_copy(args.collection, args.destination, args.copy_reserve_bytes)
    data = _copy_data(plan)
    if args.apply and not decision_digest_matches(
        args.migration_decision_digest, str(data["decision_digest"])
    ):
        raise ManagedQuarantineError("retained-copy plan changed after review")
    if args.apply:
        if args.recover:
            try:
                recover_copy(args.collection, args.destination, args.copy_reserve_bytes)
            except (NoUndoableRun, NoRetainedCopy):
                # The prior child may have failed before recording any intent.
                # Only absent or fully committed copy-free history permits a
                # fresh, fully revalidated apply; malformed/partial history does not.
                apply_copy(plan)
        else:
            apply_copy(plan)
    print(
        f"{'Verified retained copy of' if args.apply else 'Would copy'} "
        f"{plan.evidence.files} file(s), {plan.evidence.total_bytes} byte(s). "
        "Source duplicates remain in place; no storage was reclaimed."
    )
    print(
        "Copy evidence covers file byte streams only; filesystem metadata is not "
        f"claimed preserved ({plan.evidence.metadata_entries} entry/entries with extended attributes, "
        f"{plan.evidence.metadata_unknown} uninspectable)."
    )
    if not args.apply:
        print("Dry run only. Add --apply after reviewing this exact plan.")
    _write_outcome(
        args.migration_outcome,
        data,
        result_kind="observed" if args.apply else "preview",
        collection=plan.collection_root,
        private_io=args.migration_private_binding,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.recover and not args.apply:
        print("--recover requires --apply.", file=sys.stderr)
        return 2
    try:
        if args.copy:
            return _copy_main(args)
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
                    private_io=args.migration_private_binding,
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
            private_io=args.migration_private_binding,
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
