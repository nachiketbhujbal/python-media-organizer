# Stable migration report

`pymo migrate --json` emits schema 1 of the public, path-private migration
report. It projects the coordinator's already-recorded strict stage outcomes;
it does not scan either collection, create new evidence, advance the workflow,
or authorize a mutation or deletion.

## Invocation

An existing private migration state directory is required. The explicit resume
form is the shortest invocation:

```bash
pymo migrate --resume "/path/to/private-logs" --json
```

The original locator remains supported:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection" --log-dir "/path/to/private-logs" --json
```

The command writes one compact JSON object and a trailing newline to standard
output. It emits no timestamps, progress messages, final runtime line, or
debug output, including when global console-output flags are present. A caller
may explicitly capture that output:

```bash
pymo migrate --resume "/path/to/private-logs" --json > migration-report.json
```

Report generation requires an existing state file and its existing private
coordinator lock. It validates the exact pymo version, collection roots,
root separation, complete restart lifecycle, and every referenced typed
outcome before output. It also rechecks the lifecycle, outcome projection, and
both collection-directory identities before emitting. A missing, unsafe,
changed, or conflicting input returns setup status 2 without producing a
report or creating coordinator state.

`--json` cannot be combined with `--start`, `--run-next`, `--run`,
`--interactive`, `--accept-status`, or `--confirm-quarantine`. It is a report
action only.

## Schema 1 compatibility

The top-level object has exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | Always `1` for this contract. |
| `report_type` | string | Always `pymo-migration-report`. |
| `tool_version` | string | Exact pymo version bound to the restart state. |
| `workflow` | object | Coordinator progress, reviews, quarantine confirmation, and sign-off bookkeeping. |
| `observed_child_work` | object | Count and summed measured duration of recorded child attempts. |
| `inventory` | object | Baseline and initial-working scan aggregates, or `null` before those stages. |
| `health` | object | Baseline and latest-working validation aggregates, or `null` before those stages. |
| `applied_transformations` | array | Successful observed extension, organization, and rename apply outcomes in workflow order. |
| `exact_duplicates` | object | Latest successful image/video duplicate outcomes, review-storage interpretation, and aggregate cache counts. |
| `preservation` | object or null | Latest verification outcome, preferring final observed verification when available. |
| `scope` | object | Fixed limits on what generating this report did and what its contents authorize. |

All count, byte, duration, and exit-status values are non-negative integers;
an unavailable exit status is `null`. Arrays retain workflow order. Objects
are serialized with lexicographically sorted keys and compact separators, so
unchanged valid state produces byte-identical output.

### Workflow

`workflow.status` is one of:

- `not-started`: state exists but no child has run;
- `pending`: the next stage or operator checkpoint has not completed;
- `stopped`: the latest child returned a nonzero status and was not advanced;
- `complete`: every stage has completed, whether or not human sign-off was
  later recorded.

`completed_stages` and `total_stages` are counts. `next_stage` is the pending
stage identifier or `null` at completion. `stopped_stage` and
`latest_exit_status` are populated only for `stopped`. Separate counters record
all successful-validation and status-one acknowledgements.
`external_quarantine_confirmed` records only the existing human checkpoint;
it does not prove the external destination. `human_signoff_recorded` records
only explicit operator sign-off and does not alter preservation evidence.

### Recorded result kinds

Inventory and health objects contain `result_kind` and `status` alongside their
aggregate facts. Applied transformations are successful `observed` results.
Each exact-duplicate analysis explicitly records `preview` or `observed` plus
its exit status. Preservation explicitly records `simulated` or `observed` and
its exit status, verdict, disposition, accounting totals, and aggregate reason
codes.

The duplicate `review_storage.state` is one of:

- `not-assessed`: no successful duplicate result exists;
- `potentially-reclaimable`: duplicate copies were previewed or isolated, but
  the external-retention checkpoint has not been confirmed;
- `external-retention-confirmed-unverified`: the operator confirmed the
  working `dups` path was absent, but pymo did not inspect an external
  destination or prove physical capacity was reclaimed.

`physical_storage_reclaimed` is therefore `false` in schema 1.

### Privacy and authority

Schema 1 never includes collection roots, filenames, ignored path names,
private directory paths, state or outcome filenames, attempt identifiers,
timestamps, or action-journal entries. It deliberately omits free-form private
cache issue text and includes only cache booleans and counts.

`scope.basis` is `validated-private-stage-outcomes`. The remaining scope fields
state that generation produced no fresh evidence, collection write, or action-
history write and grants no deletion authority or whole-device recovery claim.
The report does not replace the baseline, retained quarantine, child logs,
action journal, or ordinary fresh final verification.

The schema version is the compatibility boundary. A future release must use a
new schema version before changing any schema 1 field name, type, allowed value,
or meaning. Human synopsis wording is not part of this machine contract.
