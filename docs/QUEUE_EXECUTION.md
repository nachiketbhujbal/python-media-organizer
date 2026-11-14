# Sequential queue execution

The v0.7.3 candidate adds `pymo queue run MANIFEST`. Without `--apply`, it
prints the same zero-write declaration preview as `queue plan`. Planning
schema 1 and manifest schema 1 remain unchanged. Execution has no JSON outcome
surface yet; queue recovery and aggregate synopsis are separate releases.

```bash
pymo queue plan "/private-plans/queue.json" --json
pymo queue run "/private-plans/queue.json"
pymo queue run "/private-plans/queue.json" --apply
```

## Authority and ordering

The complete manifest must pass declaration checks before any job state or
media write. Execution retains the original manifest, policy and receipt
bytes/identities, root ancestry and destination bindings; it does not reconstruct
authority from the public plan. Before each new job and between unattended
engine stages it rechecks original control/root bindings and still-pending
destinations. All jobs run in the declared order, one at a time.

The exact reviewed policy supplies each job's options and checkpoint decisions.
Queue `--apply` permits dispatch; it does not replace those decisions or waive
fresh media evidence. Authored policy namespaces are freshly checked before
creating job state and at the existing execution boundaries. Manual schema-4
policies retain their existing exact outcome and mutation-plan requirements.
A declaration check does not prove media preservation or free capacity. The
managed retained-copy child owns its capacity reserve check when it runs.

Each job uses the existing one-stage unattended migration engine and its
ordinary previews, applies, validation acknowledgements, duplicate disposition,
fresh final verification and policy-authorized sign-off. A nonzero unhandled
status stops the queue and is returned unchanged. A reviewed validation finding
may advance only when the existing policy exactly matches it. External
quarantine remains human-managed: the engine stops if `dups` is still present;
the queue never moves it on that disposition's behalf or proves external retention.

## State and interruption

Every manifest entry names an absent private state directory under an existing
owner-private parent. Execution allocates a private staging directory, publishes
it with one descriptor-relative atomic no-replace rename, and holds a dedicated
job lock. Its original ancestry and lock inode are carried into descriptor-
relative state/log/outcome I/O and child setup; replacing either cannot redirect
stage output to a new directory. Each child also binds the exclusively allocated
log inode, so a replacement regular file cannot receive appended diagnostics.
It creates separate ordinary migration state, policy binding, logs
and typed outcomes there. An occupied destination is never overwritten or
adopted, even if empty. Staging and partial job state are retained on failure.

A zero process status alone cannot start the next job. The executor reloads
strict state, checks original roots/options/version/policy binding, validates
the complete typed outcome history and final authorization, and requires the
terminal stage plus recorded sign-off. State remains bookkeeping, not new
preservation evidence or deletion authority.

Ctrl-C returns 130; unsafe setup/state/bindings return 2. No later job starts
after an unresolved result. A repeat `queue run --apply` refuses previously
created state instead of retrying anything. Preserve it for inspection. Existing
single-collection `migrate --resume` remains available with the exact version,
policy and saved paths; a partially applied child needs reviewed journal recovery
first. Do not edit policies/state or choose replacement paths to evade that
boundary. Queue resume/retry/skip semantics belong to v0.7.4.

## Output and scope

Queue headers and setup errors use aggregate ordinals. During execution the
existing migration engine emits its normal stage output and private stage-log
locators; children honor the bound policy's console/disclosure settings. Thus
execution is not the path-private planning JSON surface. Global queue options
cannot override a job policy or create an extra persistent log. The explicitly
declared job directories own persistent output.

Completion concerns only each approved workflow at its execution boundary. It
does not promise all collections stayed unchanged after their jobs finished,
copy an initial collection, publish to a package index, retire originals, delete
review storage or reclaim physical space. Keep baselines and retained evidence;
source retirement remains a separate human decision after fresh verification.
