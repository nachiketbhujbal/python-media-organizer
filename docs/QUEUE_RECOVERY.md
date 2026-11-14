# Explicit queue recovery

The v0.7.4 candidate adds a separate recovery command. `queue run` continues to
refuse occupied job state, and `queue plan` remains a new-job declaration check.

```bash
pymo queue resume "/private-plans/queue.json"
pymo queue resume "/private-plans/queue.json" --apply
pymo queue resume "/private-plans/queue.json" --job 2 --apply
pymo queue resume "/private-plans/queue.json" --retry-job 2 --apply
```

Without `--apply`, recovery is zero-write. It may read authored media bindings
and retained-tree evidence and temporarily acquire existing advisory locks,
but creates no files, locks, logs, directories, cache, history or child process.
The preview uses aggregate ordinals and fixed status labels without paths.
Execution uses the existing migration engine's console and private log locators.
There is no queue JSON outcome report in this release.

## Selection and retries

The default selects every job in manifest order. Fully completed and signed-off
jobs pass strict state/outcome checks and run no children. An unfinished job
continues at its recorded boundary; an absent state destination starts a new job
through the ordinary exclusive-allocation path. `--job N` selects only that
one-based ordinal, while still validating the whole queue. Its success says
only that the selected job finished; it does not hide another job's status.

`--retry-job N` explicitly permits retrying a recorded failed read or preview
for that selected job. Repeat it for multiple failed jobs. All required retry
selections are checked before the first write. A retry flag on an unselected,
completed or otherwise non-retryable job fails setup. There is no automatic
failed-job skipping or arbitrary stage skipping. A status-one validation with
an exact matching existing authorization follows the ordinary reviewed
acknowledgement path; it is not a read retry.

No retry flag permits a failed mutation or ambiguous partial child. An
unhandled child status is returned unchanged and stops further selected work.
Ctrl-C returns 130; missing retry acknowledgement returns 1; malformed,
incomplete, occupied or changed controls return 2. A valid recovery preview
returns 0 without implying every displayed job may immediately execute.

## State and interruption

Every existing private job lock is held from before lifecycle inspection until
return, including locks for jobs not selected. Missing locks are not recreated.
Newly started jobs stay locked too. A busy or unsafe later job therefore blocks
all recovery work before an earlier job can mutate.

Existing state must match the complete exact policy, create-once policy binding,
roots, options, installed version and strict attempt/outcome history. Recovery
pins directory ancestry and lock identities and rechecks all private entries
at execution boundaries. Completed or unselected private records cannot change
while another job runs. An explicitly named valid ordinary migration run can
be inspected; recovery does not invent provenance from a manifest.

Child log allocation is synced before dispatch. If interruption happens before
the result is recorded, that unreferenced log blocks recovery even if no outcome
exists yet. Unknown files, retained scratch, incomplete initialization, missing
records, failed mutations and unresolved action-journal operations are refused.
Pymo neither erases those artifacts nor infers the child's result. Preserve them
for journal review. Do not remove markers or edit policies/state to bypass the
refusal. Standalone journal recovery and `migrate --resume` retain their own
explicit safeguards; queue recovery requires coherent evidence afterward.

An occupied managed quarantine destination additionally requires a successful
recorded disposition, the exact approved preview and fresh committed
journal/tree verification. Retained copies verify both original and copy. An
unrelated directory at the declared destination cannot be adopted.

## Limits

Version matching is exact. Keep the original installed version available for
an existing run; upgrading to v0.7.4 does not make a v0.7.3 run compatible.
No schema migration, policy rewrite, initial copying, cleanup or concurrency is
introduced. Historical completion is not a new preservation check. Use fresh
final verification and separate human review before any source retirement.
