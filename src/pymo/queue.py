"""Plan or explicitly execute a sequential queue of approved migrations."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pymo.logging_config import emit as print
from pymo.migration.queue_plan import build_queue_plan
from pymo.migration.queue_run import run_queue


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    plan = actions.add_parser(
        "plan", help="validate declarations; write and execute nothing"
    )
    plan.add_argument("manifest", type=Path)
    plan.add_argument(
        "--json", action="store_true", help="emit path-private planning schema 1"
    )
    run = actions.add_parser("run", help="preview, or execute new jobs with --apply")
    run.add_argument("manifest", type=Path)
    run.add_argument(
        "--apply", action="store_true", help="execute approved jobs in order"
    )
    args = parser.parse_args(argv)
    if args.action == "run" and args.apply:
        return run_queue(args.manifest)

    try:
        result = build_queue_plan(args.manifest)
    except (OSError, ValueError, RuntimeError, RecursionError):
        print(
            "Queue planning stopped safely: malformed, conflicting, changed or unsafe declarations. No job started.",
            file=sys.stderr,
        )
        return 2
    if getattr(args, "json", False):
        sys.stdout.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    else:
        print(
            f"Queue plan validated: {len(result['jobs'])} jobs in declared sequential order; no job started."
        )
        for job in result["jobs"]:
            print(
                f"Job {job['ordinal']}: {job['disposition']}; {job['policy_kind']} policy; cache {job['cache']}."
            )
            for step in job["steps"]:
                decision = f"; decision {step['decision']}" if step["decision"] else ""
                print(f"  {step['stage']}: {step['mode']}{decision}")
            if job["human_external_quarantine_required"]:
                print(
                    "  Human-managed external quarantine remains a required checkpoint."
                )
        print(
            "Planning checked declarations only. Media evidence and capacity were not checked; destinations are not reserved."
        )
        print(
            "Future execution must revalidate bindings and fresh evidence. No authority, sign-off or storage reclamation was created."
        )
    return 0
