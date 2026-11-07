# Queue declarations and planning

The v0.7.2 candidate adds `pymo queue plan MANIFEST [--json]`. It checks an
entire ordered declaration and prints the stages that each job would follow.
It starts no job and writes no media, logs, cache, lock, action history, private
state or output artifact. There is no `--apply` or execution selector.

Planning reads only explicitly named private control artifacts and filesystem
metadata. It does not scan or decode media, rederive authored namespace
evidence, check free capacity, reserve destinations or prove preservation.
Even a stale media plan can pass this declaration check. Fresh target, policy,
receipt, configuration and checkpoint checks remain mandatory during execution.
Queue execution, recovery and outcome aggregation are later roadmap units.

## Private manifest schema 1

The UTF-8 JSON file must be owner-private, regular, single-linked, nonempty and
at most one MiB. Its existing parent must be owner-private with trusted ancestry,
using the same safety contract as accepted policy artifacts. No symbolic links
are accepted in artifact or declared directory ancestry. The CLI locator may be
relative; every path inside the declaration must be normalized, absolute and
canonically spelled. Duplicate JSON keys, unknown fields, non-finite numbers,
unknown schemas, empty queues and malformed values fail closed.

The following is a structural example, not a usable policy or ready-made manifest.
Replace the version, identities and digest with observed values for the intended
local roots and an already reviewed policy. Device/inode pairs are JSON integers
from `Path.stat().st_dev` and `Path.stat().st_ino`; booleans are invalid. The digest
is lowercase SHA-256 over the exact policy file bytes. Keep the manifest outside
all collections; create it privately without replacing an existing artifact.

```json
{
  "schema_version": 1,
  "tool_version": "EXACT_INSTALLED_VERSION",
  "entries": [
    {
      "baseline": {"path": "/collections/baseline", "identity": [0, 0]},
      "working": {"path": "/collections/working", "identity": [0, 0]},
      "state_directory": "/private-plans/run-one",
      "policy": {"path": "/private-plans/accepted.json", "sha256": "EXACT_POLICY_SHA256"},
      "disposition": "retained-in-place",
      "quarantine": null
    }
  ]
}
```

Array order is execution order. Entries have no free-form name or identifier;
reports use one-based ordinals. Each entry binds existing baseline and working
directory identities, one **absent** private state directory leaf under an
existing owner-private parent, exact accepted policy bytes and duplicate
disposition. Existing state, even an empty directory, is refused: this format
declares new jobs, not resume or retry authority.

The policy supplies all effective coordinator options. It must match the
installed version and the exact baseline/working paths and contain all ten
ordered authorizations, including final sign-off. Both manual schema 4 and
accepted authored schema 5 are supported. Schema 5 requires its independently
verified acceptance receipt. A candidate, extracted draft, incomplete policy,
missing receipt or replaced receipt is invalid. Planning creates no acceptance.
Authoring remains retained-in-place/no-cache only; a declaration does not solve
the underivable future identities of managed-quarantine authoring.

## Duplicate disposition

| `disposition` | Policy decision | `quarantine` |
| --- | --- | --- |
| `retained-in-place` | `retain-dups` | `null` |
| `external-quarantine` | `confirm-quarantine` | `null` |
| `managed-same-filesystem` | `quarantine-dups` | Object with `destination` and null `copy_reserve_bytes` |
| `retained-copy` | `quarantine-dups` | Object with `destination` and explicit nonnegative integer `copy_reserve_bytes` |

Managed destinations must be absent leaves under existing directories, match
the policy's exact path digest and parent device/inode, and agree with its
method and reserve. Rename requires the same filesystem; retained copy requires
a different one. Topology uses a current real `dups` directory when present,
otherwise the working root's device for the future directory. These are
metadata checks, not full tree or capacity preflight. Explicit external
quarantine remains a human-managed checkpoint; no external location or retained
copy is proven by its confirmation policy.

Every baseline, working root, state destination and managed quarantine
destination must be distinct and non-nested across the complete queue. Shared
baselines are conservatively refused too. Existing endpoints are compared by
filesystem identity and ancestry. Absent leaves under the same physical parent
are also compared case-insensitively after Unicode normalization; ambiguous
spellings are refused even on a case-sensitive filesystem. Distinct state
leaves may share a private parent. Manifests, policies, receipts and referenced
configuration/native-tool parents must stay outside all collection roots.

All endpoints, parent identities, target absence, manifest/policy bytes and
schema-5 receipts are rechecked before any successful plan is emitted. An
occupied target, unsafe ancestry or failure in the last job rejects the whole
plan. There is no partial successful plan, path reservation or authority to
ignore subsequent changes.

## Output and compatibility

```bash
pymo queue plan "/private-plans/queue.json"
pymo queue plan "/private-plans/queue.json" --json
```

Normal output is timestamped and path-private, including under full visibility.
It lists every fixed workflow stage, its mode and authorized checkpoint
decision, separate managed quarantine preview/apply steps where selected, and
final sign-off as a future checkpoint. It never says those steps have run.
It reports policy origin (manual/authored), cache selection and required human
external quarantine. Detailed private options and expectations remain in the
bound policy; the output does not disclose them or grant their authority.

JSON planning schema 1 is deterministic and has exactly these top-level fields:
`schema_version`, `kind` (`queue-plan`), `execution` (`not-started`), `ordering`
(`sequential`), `media_evidence` and `capacity` (both `not-checked`),
`destinations_reserved` and `authority_created` (both false), and ordered `jobs`.
Each job has integer `ordinal`, `disposition`, `policy_kind` (`manual`/`authored`),
`cache` (`enabled`/`disabled`), boolean `human_external_quarantine_required`, and
`steps`. Each step has `stage`, `mode`, `target` and nullable `decision`, drawn
only from the fixed workflow and supported disposition choices. There are 25
steps normally, or 27 with managed quarantine. Roots, filenames, identities,
digests, timestamps and arbitrary manifest text are omitted.

This is a planning projection, separate from the future queue outcome synopsis.
Any incompatible public field, type, allowed value or meaning change requires
a new schema version. JSON has no logging prefix or runtime footer. Exit 0 means
only that the declaration checks passed; unsafe setup returns 2, emits no JSON,
and prints a generic path-private error. Ctrl-C retains exit 130. `--log-file`,
global configuration, path-disclosure and execution options are rejected before
persistent output can be created. Shell redirection is the operator's separate
choice and is not a pymo publication operation.
