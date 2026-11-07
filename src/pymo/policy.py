"""Plan, review and explicitly accept one target-local unattended policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pymo import __version__
from pymo.config import ConfigError
from pymo.file_safety import FileChangedError
from pymo.logging_config import emit as print
from pymo.migrate import _initial_options
from pymo.migration.coordinator_state import (
    MigrationCoordinatorError,
    _options_from_json,
)
from pymo.migration.outcome import MigrationOutcomeError
from pymo.migration.policy_files import publish_private, read_private
from pymo.migration.policy_plan import POLICY_CANDIDATE_SCHEMA_VERSION, build_candidate
from pymo.migration.preauthorization import (
    MigrationPreauthorizationError,
    _object_without_duplicate_keys,
)
from pymo.migration.roots import DirectoryIdentityError
from pymo.migration.virtual import PolicyPlanningError, canonical_bytes
from pymo.video_content import VideoInspectionError


def _candidate(payload: bytes) -> dict[str, Any]:
    value = json.loads(payload, object_pairs_hook=_object_without_duplicate_keys)
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "kind", "policy", "transitions"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != POLICY_CANDIDATE_SCHEMA_VERSION
        or value["kind"] != "unaccepted-migration-plan"
        or not isinstance(value["policy"], dict)
        or not isinstance(value["transitions"], list)
    ):
        raise PolicyPlanningError("candidate format is unsupported")
    policy = value["policy"]
    if (
        set(policy)
        != {
            "schema_version",
            "tool_version",
            "baseline",
            "working",
            "options",
            "authorizations",
            "plan_binding",
        }
        or policy["schema_version"] != 5
        or policy["tool_version"] != __version__
        or not all(
            isinstance(policy[k], str) and Path(policy[k]).is_absolute()
            for k in ("baseline", "working")
        )
        or not isinstance(policy["authorizations"], list)
    ):
        raise PolicyPlanningError("candidate target declaration is invalid")
    _options_from_json(policy["options"])
    return value


def _review(candidate: dict[str, Any], sha256: str) -> None:
    print("Unaccepted migration plan; no execution authority or storage reclaimed.")
    print(f"Candidate SHA-256: {sha256}")
    for item in candidate["policy"]["authorizations"]:
        if not isinstance(item, dict) or set(item) != {
            "checkpoint",
            "decision",
            "expected",
        }:
            raise PolicyPlanningError("candidate checkpoint is malformed")
        # Render only strict selected aggregates, never arbitrary artifact text.
        from pymo.migration.preauthorization import _validate_authorization

        checkpoint, (decision, expected) = _validate_authorization(item)
        print(f"{checkpoint}: {decision}; {json.dumps(expected, sort_keys=True)}")
    print(
        "Duplicate files remain in place. Final evidence will be recomputed during execution."
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    plan = actions.add_parser(
        "plan", help="derive a complete zero-media-mutation candidate"
    )
    plan.add_argument("baseline", type=Path)
    plan.add_argument("working", type=Path)
    plan.add_argument("--output", type=Path)
    plan.add_argument(
        "--apply", action="store_true", help="write only the private candidate"
    )
    plan.add_argument("--config", type=Path)
    plan.add_argument("--ffmpeg", type=Path)
    plan.add_argument("--ffprobe", type=Path)
    plan.add_argument("--decode-timeout", type=int)
    plan.add_argument(
        "--quarantine-destination",
        type=Path,
        help="currently refused when future identities cannot be derived",
    )
    review = actions.add_parser(
        "review", help="show every candidate checkpoint and expectation"
    )
    review.add_argument("candidate", type=Path)
    accept = actions.add_parser(
        "accept", help="revalidate and publish the exact reviewed policy"
    )
    accept.add_argument("candidate", type=Path)
    accept.add_argument("--sha256", required=True)
    accept.add_argument("--output", required=True, type=Path)
    accept.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            if args.apply and args.output is None:
                parser.error("--apply requires --output")
            if args.decode_timeout is not None and args.decode_timeout <= 0:
                parser.error("--decode-timeout must be positive")
            roots = (
                args.baseline.expanduser().resolve(strict=True),
                args.working.expanduser().resolve(strict=True),
            )
            options = _initial_options(
                {
                    "no_cache": True,
                    "config": (
                        str(args.config.expanduser().resolve(strict=True))
                        if args.config
                        else None
                    ),
                    "ffmpeg": (
                        str(args.ffmpeg.expanduser().resolve(strict=True))
                        if args.ffmpeg
                        else None
                    ),
                    "ffprobe": (
                        str(args.ffprobe.expanduser().resolve(strict=True))
                        if args.ffprobe
                        else None
                    ),
                    "decode_timeout": args.decode_timeout,
                    "quarantine_destination": (
                        str(args.quarantine_destination)
                        if args.quarantine_destination
                        else None
                    ),
                }
            )
            candidate = build_candidate(*roots, options, show_progress=True)
            payload = canonical_bytes(candidate)
            _review(candidate, hashlib.sha256(payload).hexdigest())
            if args.apply:
                publish_private(args.output, payload, roots)
                print(
                    "Private candidate saved; review and acceptance are still required."
                )
            else:
                print("Preview only; use --output and --apply to save this candidate.")
            return 0
        payload = read_private(args.candidate)
        candidate = _candidate(payload)
        sha256 = hashlib.sha256(payload).hexdigest()
        if args.action == "review":
            _review(candidate, sha256)
            return 0
        if args.sha256 != sha256:
            raise PolicyPlanningError(
                "candidate digest differs from the reviewed bytes"
            )
        policy = candidate["policy"]
        roots = (Path(policy["baseline"]), Path(policy["working"]))
        fresh = build_candidate(
            *roots, _options_from_json(policy["options"]), show_progress=True
        )
        if (
            canonical_bytes(fresh) != canonical_bytes(candidate)
            or read_private(args.candidate) != payload
        ):
            raise PolicyPlanningError(
                "candidate or target changed; generate and review a new plan"
            )
        if args.apply:
            publish_private(args.output, canonical_bytes(policy), roots)
            print("Accepted private policy saved. Migration has not started.")
        else:
            print(
                "Acceptance preview passed; --apply is required to publish authority."
            )
        return 0
    except PolicyPlanningError as error:
        print(f"Policy authoring stopped safely: {error}.", file=sys.stderr)
        return 2
    except (
        MigrationPreauthorizationError,
        MigrationCoordinatorError,
        MigrationOutcomeError,
        DirectoryIdentityError,
        ConfigError,
        FileChangedError,
        VideoInspectionError,
        OSError,
        ValueError,
        RuntimeError,
    ):
        # No source paths, untrusted artifact text or native diagnostics in output.
        print(
            "Policy authoring stopped safely: incomplete, changed, unsupported or unsafe evidence. No execution was authorized by this command.",
            file=sys.stderr,
        )
        return 2
