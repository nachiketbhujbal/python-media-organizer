# Pre-authorized unattended migration policy

`pymo migrate --unattended PRIVATE_POLICY_JSON` is for a migration whose
operator already knows the exact aggregate results they are willing to accept.
It is intentionally stricter than a general “yes to all” option: every
validation review, apply, quarantine confirmation, and final sign-off must be
named separately with the exact preceding result it may cross.

For a new run:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection" --log-dir "/path/to/private-logs" --unattended "/path/to/private-policy.json"
```

For that exact existing run:

```bash
pymo migrate --resume "/path/to/private-logs" --unattended "/path/to/private-policy.json"
```

The first form validates the policy before creating restart state, initializes
the explicitly named private directory, and enters the normal one-stage engine.
The second recovers exact roots and options from that directory. Neither form
searches for state or policies.

## Privacy and file safety

The policy contains collection paths and is private. Its file must:

- be a regular file, not a symbolic link;
- have exactly one hard link;
- grant no permissions to group or other users, for example mode `0600`;
- be no larger than one MiB;
- live outside both collection roots; and
- remain byte-for-byte and identity-stable for the complete invocation.

The first unattended invocation creates
`pymo-unattended-policy-binding.json` as a separate private, create-once,
no-replace record in the migration log directory and stores the same policy
payload SHA-256 in restart state. The record binds the digest to the run's tool
version, canonical roots, complete options, and creation time. The record,
restart state, and supplied policy must agree on every later unattended resume.
An exact policy copy may be supplied from another safe private path, but
reformatting or changing even otherwise valid policy JSON requires a new
migration run; it cannot broaden authority for an existing run.

Keep the policy and migration log directory private. The binding record is
restart authority bookkeeping, not media evidence, the collection action
journal, quarantine proof, or deletion authority. Pymo creates it with private
permissions, never replaces it, and fails closed if it is missing, unsafe,
malformed, or disagrees with either of the other two authority surfaces.

## Schema 1

The top-level object has exactly these fields:

```json
{
  "schema_version": 1,
  "tool_version": "0.6.5",
  "baseline": "/canonical/path/to/baseline",
  "working": "/canonical/path/to/working-collection",
  "options": {
    "verbose": false,
    "quiet": false,
    "timestamps": true,
    "config": null,
    "show_ignored": false,
    "show_files": false,
    "ffmpeg": null,
    "ffprobe": null,
    "decode_timeout": null,
    "workers": null,
    "no_cache": false
  },
  "authorizations": []
}
```

`tool_version`, both canonical absolute roots, and every option must exactly
match the coordinator run. The authorization list may contain any subset of
the checkpoints below, but entries must be unique and in workflow order.
Reaching an omitted checkpoint stops with status 1.

| Checkpoint | Decision | Evidence matched exactly |
| --- | --- | --- |
| `baseline-validation` | `accept-validation` | Baseline full validation |
| `working-validation` | `accept-validation` | Initial working full validation |
| `extension-apply` | `apply` | Extension-correction preview |
| `organize-apply` | `apply` | Organization preview |
| `rename-apply` | `apply` | Rename preview |
| `image-duplicates-apply` | `apply` | Exact-image duplicate preview |
| `video-duplicates-apply` | `apply` | Exact-video duplicate preview |
| `external-quarantine` | `confirm-quarantine` | Complete without-`dups` simulation |
| `final-working-validation` | `accept-validation` | Final working full validation |
| `final-signoff` | `signoff` | Complete ordinary final verification |

Validation `expected` has these exact fields:

```json
{
  "status": 0,
  "media_files": 0,
  "media_bytes": 0,
  "pictures": 0,
  "videos": 0,
  "other_files": 0,
  "symbolic_links": 0,
  "unreadable": 0,
  "changed": 0,
  "healthy": 0,
  "warning_only": 0,
  "errors": 0,
  "findings": [],
  "cache_issue": false
}
```

Findings are unique objects containing `severity`, `code`, and positive
`count`, sorted by severity and then code. Status 1 may be accepted when it
exactly corresponds to known validation errors. `unreadable`, `changed`, and
`cache_issue` must always remain false or zero.

A transformation apply uses the matching successful preview:

```json
{
  "status": 0,
  "operation": "organization",
  "files": 0,
  "directories_created": 2,
  "directories_removed": 0,
  "decision_digest": "migration-decision-v1:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

`operation` is `extension-correction`, `organization`, or `rename` and must
match its checkpoint. An exact-duplicate apply uses:

```json
{
  "status": 0,
  "media_kind": "image",
  "scanned_files": 0,
  "scanned_bytes": 0,
  "groups": 0,
  "extra_copies": 0,
  "duplicate_bytes": 0,
  "skipped": 0,
  "cache_issue": false,
  "decision_digest": "migration-decision-v1:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

The versioned digest covers the ordered private source/target decisions and
descriptor-pinned SHA-256 content for every source that would move; it prevents
a different plan with identical aggregate counts, or different content at the
same paths, from inheriting authority. It reveals no path by itself but is
obtained from private coordinator outcome evidence. The coordinator passes the
reviewed digest to the apply child, which recomputes the current plan and stops
before mutation if it differs. Organization and rename also carry the same
file state and SHA-256 into the journaled move boundary. `media_kind` must match
the image or video checkpoint. External quarantine uses the successful
simulation totals:

```json
{
  "status": 0,
  "review_files": 0,
  "review_bytes": 0,
  "verdict": "complete",
  "disposition": "eligible-for-human-quarantine-review"
}
```

Final sign-off repeats every aggregate from the ordinary final verification:

```json
{
  "status": 0,
  "source_files": 0,
  "source_bytes": 0,
  "source_unique_streams": 0,
  "accounted_unique_streams": 0,
  "accounted_source_files": 0,
  "unaccounted_unique_streams": 0,
  "unaccounted_source_files": 0,
  "unsupported_unique_streams": 0,
  "unsupported_source_files": 0,
  "destination_files": 0,
  "destination_bytes": 0,
  "review_files": 0,
  "review_bytes": 0,
  "verdict": "complete",
  "disposition": "eligible-for-human-signoff",
  "reasons": []
}
```

## Stops and resume

- Status 0 means the authorized sequence completed and conditional sign-off was
  recorded, or an already signed-off run was inspected again.
- Status 1 means valid authority did not match the current checkpoint, a
  checkpoint was omitted, or the working `dups` path is still present.
- Status 2 means policy, binding, state, outcome, root, or setup safety failed.
- Any other child status, including 130 for interruption, is returned unchanged.

An evidence mismatch never writes an acknowledgement or dispatches its pending
apply. After a child failure, resolve the cause before resuming. At external
quarantine, pymo still does not move or delete anything: retain the complete
tree separately, confirm the working `dups` path is absent, then resume with the
same unchanged policy.

Policies are most suitable for repeated or previously reviewed collection
shapes whose exact aggregate evidence is already known. For an unfamiliar
collection, use `--run`, `--interactive`, the human synopsis, and `--json` to
review the evidence first; authoring broad guesses is expected to stop safely,
not to make the coordinator permissive.
