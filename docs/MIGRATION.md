# Production migration runbook

This runbook defines the conservative, collection-by-collection sequence for
copying or rescuing media into a working collection and using `pymo` to prove,
transform, and sign off that collection. It is intentionally explicit. A
successful pymo report proves only its named, namespace-visible evidence
contract; it does not prove whole-device recovery.

## Availability

- Versions through 0.5.6 provide scan, validation, organization, deterministic
  renaming, exact image/video duplicate isolation, and layered migration
  verification.
- Version 0.5.9 adds reversible `correct-extensions` behavior.
- Version 0.5.10 adds zero-write
  `verify-migration --simulate-without-dups` for the human-reviewed quarantine
  preview before ordinary fresh post-move verification.
- Version 0.5.11 adds `pymo migrate` to coordinate this sequence for one
  declared baseline/working pair. It does not perform rescue copying,
  automatic quarantine, or deletion.
- Version 0.5.12 hardens both standalone verification and guided coordinator
  setup against aliased, disappearing, replaced, or unresolvable roots and
  command-line paths.
- Version 0.5.13 reconciles this runbook with the verified 0.5.12 release. It
  changes no workflow or command behavior.
- Version 0.6.0 adds `migrate --run`, which advances routine successful stages
  in one foreground invocation and stops at every existing decision boundary.
- Version 0.6.1 adds `migrate --interactive`, which uses a terminal to ask one
  conservative question at each existing decision boundary and records
  accepted review and sign-off decisions in private restart state.
- Version 0.6.2 adds a concise path-private synopsis of the stage outcomes
  already recorded by the coordinator. It creates no new preservation evidence
  and grants no deletion authority.
- Version 0.6.3 adds explicit resume from one named existing private state
  directory without searching for state or changing any checkpoint.
- Version 0.6.4 adds stable, deterministic, path-private migration-report
  schema 1 over those validated existing outcomes.
- Version 0.6.5 adds exact private pre-authorization for unattended operation;
  versions 0.6.6 and 0.6.7 add independent logging levels and visibility
  profiles.
- Version 0.6.8 adds explicit retained-in-place duplicate disposition,
  advances the coordinator report to schema 2, and keeps the established
  human-managed external-quarantine path available.

Perform only stages supported by the installed version and keep every
transition human-reviewed. Do not use a loose shell script as the production
authority.

## Operational experience and next direction

Controlled v0.5.13 trials established that this runbook can preserve and
reproduce the intended media outcomes across varied existing collections. They
also showed that the released coordinator is operationally expensive: a full
run requires roughly two dozen similar invocations, special standalone modes
for validation acknowledgement and quarantine confirmation, and manual movement
of the duplicate review tree. Long media analysis magnifies that supervision
cost even when the underlying work and cache reuse are correct.

Version 0.6.0 reduces that repetition without skipping a checkpoint. Its safe
operator loop pauses after every successful validation for review, stops before
every apply, after any nonzero child status, at the duplicate-disposition
checkpoint, and after final evidence becomes eligible for human sign-off. It
asks no questions and grants no mutation authority. Version 0.6.1's explicit
interactive mode asks separately at those same boundaries; an answer applies
only to its current question.
[ADR 0087](adrs/0087-operator-first-migration-roadmap.md) keeps reports, saved
context, logging and visibility policy, duplicate disposition, queues, and
benchmark-gated scheduling as separate later releases;
[ADR 0088](adrs/0088-safe-migration-operator-loop.md) records the first loop
boundary, and
[ADR 0089](adrs/0089-interactive-migration-checkpoints.md) records interactive
consent. [ADR 0091](adrs/0091-typed-human-migration-synopsis.md) records the
private typed-outcome and human-synopsis boundary. [ADR 0093](adrs/0093-explicit-private-migration-resume.md)
records the saved locator, and
[ADR 0095](adrs/0095-stable-migration-report-artifact.md) records the public
report projection. [ADR 0103](adrs/0103-retained-in-place-duplicate-disposition.md)
records the first duplicate-disposition choice.

## Collection roles

- **Source:** the original device or recovery source. Keep it read-only whenever
  practical. Pymo never establishes whole-device health.
- **Baseline:** an unchanged, readable collection copy used as preservation
  evidence. Do not organize or rename it.
- **Working collection:** the destination copy on which reviewed pymo mutations
  may be applied.
- **Quarantine:** storage outside the working collection for retained review
  material. Moving `dups` outside the working root makes it absent from fresh
  destination verification, just as deletion would, but quarantine preserves a
  recovery path.

The baseline and working collection must be distinct, non-nested roots. Two
copies on one physical device are not independent backups.

## Before pymo

1. Confirm the destination has enough capacity for the working collection,
   disposable cache, action history, and any retained quarantine.
2. Check filesystem case behavior and resolve case-folded name collisions
   before copying from a case-sensitive source to a case-insensitive target.
3. Perform the rescue or no-overwrite copy with an appropriate external tool.
   Retain that tool's evidence and do not assume an interrupted copy completed.
4. Keep the source and baseline unchanged. Direct all pymo mutations only at
   the working collection.
5. Create a private log directory outside both collection roots if persistent
   logs are wanted. Logs remain opt-in because paths and filenames are
   sensitive.

## Guided coordinator

The workflow introduced in v0.5.11 keeps the manual stages below as its
authority. Version 0.5.12 additionally contains every command-line path
expansion and resolution failure before private state can be created.
Version 0.6.3 adds an explicit private resume-directory shorthand without
changing the stage engine or any checkpoint.
Version 0.6.5 adds a separately specified private policy that may cross only
the exact validation, apply, duplicate-disposition, and final-signoff results the
operator authorized in advance.
Version 0.6.6 adds independently saved console and private stage-file logging
thresholds without changing the stage sequence, checkpoint authority, path
disclosure, or opt-in persistence boundary.
Version 0.6.7 adds explicit visibility profiles over the already-saved console
and disclosure settings without changing restart schema, workflow authority,
or the path-private migration-report contract.
Version 0.6.8 advances restart state to schema 4, unattended policy to schema
2, and the migration report to schema 2 so retained-in-place and external
quarantine remain explicit, distinct decisions.
First inspect the zero-write plan, then explicitly initialize one dedicated
private directory outside and non-nested with both collections:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection"
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs" --start
```

Common `--config`, `--show-ignored`, `--show-files`, `--verbose`/`--quiet`,
`--console-log-level`, `--file-log-level`, timestamp, `--workers`, `--no-cache`,
ffmpeg/ffprobe, and decode-timeout choices supplied at `--start` are fixed in
schema-4 restart state and carried only to applicable child commands. Later
explicit options must agree with that state. `--console-log-level` and
`--file-log-level` accept `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`.
The console selector cannot be combined with `--verbose` or `--quiet`; the file
selector controls each already-private per-stage log created under `--log-dir`.
Pymo appends no ordinary `--log-file` for the coordinator, rotates or prunes no
stage log, and grants no new disclosure or persistence authority through a
logging threshold.
Use the same released pymo version for the complete sequence.

As a shorthand for coherent console and path-disclosure choices, place one
profile before `migrate`:

```bash
pymo --visibility full migrate "/path/to/baseline" "/path/to/working-collection" --log-dir "/path/to/private-logs" --start
```

Full resolves to console `DEBUG` plus `--show-files` and `--show-ignored`;
private resolves to console `INFO` with paths hidden; quiet resolves to console
`WARNING` with paths hidden. The resolved values are stored in schema-4 state,
so `--resume` recovers them without repeating the profile. A profile cannot be
combined with an individual console or disclosure selector. It never changes
the private stage-file threshold or creates persistence by itself. Full
visibility cannot be used with migration-report `--json`, which remains
strictly path-private.

Inspect current state without advancing it, execute exactly one pending stage,
or advance routine work to the next operator checkpoint:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs"
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs" --run-next
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs" --run
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs" --interactive
```

Once initialized, later invocations may instead name only the exact private
directory and the desired existing action:

```bash
pymo migrate --resume "/path/to/private-logs"
pymo migrate --resume "/path/to/private-logs" --run-next
pymo migrate --resume "/path/to/private-logs" --run
pymo migrate --resume "/path/to/private-logs" --interactive
pymo migrate --resume "/path/to/private-logs" --unattended "/path/to/private-policy.json"
pymo migrate --resume "/path/to/private-logs" --json
```

`--resume` never searches the current directory, collections, parents, or a
default location. It cannot be combined with positional collections,
`--log-dir`, or `--start`. Common options come from strict restart state;
explicit repetitions are accepted only when they exactly match the recorded
values. Before any status or action, the coordinator revalidates the private
directory, exact pymo version, recorded roots, root/log separation, strict
lifecycle, and every required private outcome.

`--run` chains only routine successful evidence and preview children. It reloads
the strict restart lifecycle, requires exactly one new successful attempt for
the child it dispatched, retains its roots, version, options, and creation
binding, and verifies both collection-directory identities between stages. It
pauses after every successful validation because warning-only findings return
status 0. A successful preview pauses before its distinct mutation checkpoint.
After reviewing that preview, authorize only the pending child:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs" --run-next --apply
pymo migrate --resume "/path/to/private-logs" --run-next --apply
```

Then use `--run` again to continue routine evidence work. Use `--run-next`
instead whenever exactly one child stage is desired.

Use `--interactive` only from a real terminal. It runs routine stages like
`--run`, then asks a separate `[y/N]` question for a successful or status-one
validation review, one pending reviewed apply, duplicate disposition, and
final human sign-off. Only `y` or `yes` authorizes the
current checkpoint. `n`, `no`, or an empty line pauses normally except that a
pending status-one validation continues to return its recorded status 1 until
it is acknowledged. Invalid input, end-of-file, and redirected non-terminal
input return setup status 2 without advancing the checkpoint; Ctrl-C retains
status 130. Accepted mutations still use the existing one-stage apply path and
must pass the exact restart-transition and collection-identity checks before
any later child can run.

`--unattended PRIVATE_POLICY_JSON` is the non-interactive counterpart for a
previously understood migration. With positional roots and `--log-dir`, it
validates the policy, initializes new private state, and begins in one
invocation. With `--resume`, it continues only that exact run:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection" --log-dir "/path/to/private-logs" --unattended "/path/to/private-policy.json"
pymo migrate --resume "/path/to/private-logs" --unattended "/path/to/private-policy.json"
```

The mode creates a separate no-replace private binding record on first use and
also stores that policy payload digest in restart state. The binding record,
restart state, and byte-identical policy must agree on every unattended resume.
The log directory itself must remain owner-private and its ancestry must not
permit another user to replace it; ownership-safe sticky ancestors such as the
system temporary directory remain valid, but every ancestry component must be
owned by root or the current user. It also revalidates the current policy file,
strict lifecycle, typed outcomes, version and options binding, and both
collection identities between children and immediately before each authorized
transition. Every checkpoint has its own
exact expected aggregate; one authorization never covers another.
A missing or mismatched current authorization returns status 1 without
crossing it, while unsafe or changed authority returns setup status 2. An
unexpected child status remains exact. The full private file requirements,
schema-2 fields, checkpoint order, and resume behavior are in
[MIGRATION_POLICY.md](MIGRATION_POLICY.md).

A nonzero child status is recorded, returned unchanged, and stops both modes.
Rerun after resolving the cause. Status 1 from a validation checkpoint may be
advanced only after human review with `--accept-status`; the original status
remains in state. Verification, mutation, configuration, discovery, and native
tool failures cannot be acknowledged away.

After the successful without-`dups` simulation, `--run` stops normally and
returns 0 at the duplicate-disposition checkpoint. To keep the complete
review tree inside the working collection, record retained-in-place
disposition:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection" --log-dir "/path/to/private-logs" --retain-dups
pymo migrate --resume "/path/to/private-logs" --retain-dups
```

When the simulation found review files, `dups` must still be a real directory;
a missing, symbolic-link, or non-directory path returns status 1 without
advancing. Pymo leaves the tree and its contents untouched and reports that it
reclaimed no physical storage. When no review files exist, the same action
records that disposition is not applicable.

The established alternative remains available: move the complete review tree
outside the working collection using a separately reviewed procedure, then,
once the working `dups` path is absent, record the human checkpoint:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs" --confirm-quarantine
pymo migrate --resume "/path/to/private-logs" --confirm-quarantine
```

That confirmation proves only path absence plus the operator's acknowledgement,
not quarantine retention. Neither choice is deletion authority. A later
`--run` performs final fresh validation and
pauses for review. One more `--run` performs ordinary observed verification,
then stops at the human-signoff boundary. `--interactive` performs the same
applicable disposition check and asks for final sign-off; its accepted review
and sign-off attempts support honest resume but remain bookkeeping rather than
evidence.
Restart state and stage logs
are private operational records, not the collection action journal, current
media evidence, or deletion authority. An interrupted apply may have committed
its own append-only action run even if coordinator state did not advance; review
the child log and action history before rerunning.

Current coordinator status and each automatic or interactive stop also print a
concise migration synopsis. Its available facts come from strict aggregate
outcomes written by the child commands into the same explicit private log
directory. The synopsis reports only stages that actually ran, keeps paths and
filenames private, labels previewed versus isolated duplicates and simulated
versus observed preservation, and reports only measured child duration. A
potentially reclaimable duplicate total is not a claim that storage has been
reclaimed. Retained-in-place disposition explicitly reports no pymo storage
reclamation; even after external confirmation, pymo has proved only path
absence and recorded the operator's acknowledgement. The synopsis is convenient
bookkeeping, not fresh evidence, action history, quarantine proof, sign-off, or
deletion authority.

Use `--json` when a local program needs the same selected facts without parsing
the human synopsis. It is mutually exclusive with every workflow action,
requires existing private coordinator state and its existing lock, performs no
media analysis, and changes no state. It emits one compact schema-2 object to
standard output with no timestamps, progress, or runtime line. The report
distinguishes workflow progress and sign-off, previewed and observed duplicate
analysis, simulated and observed preservation, and pending, retained-in-place,
not-applicable, or externally retained-but-unverified review storage. It
contains no collection roots,
filenames, private record names, attempt identifiers, or timestamps. See the
[stable migration report contract](MIGRATION_REPORT.md) for every field and
compatibility rule.

## Stage 1: establish readable evidence

Run a path-private scan on both baseline and working collection:

```bash
pymo --log-file "/path/to/private-logs/01-baseline-scan.log" \
  scan "/path/to/baseline"
pymo --log-file "/path/to/private-logs/02-working-scan.log" \
  scan "/path/to/working-collection"
```

Run fresh validation. Use `--no-cache` on a read-only baseline, or select an
explicit cache outside it. Do not use `--reuse-validation` for migration
sign-off.

```bash
pymo --log-file "/path/to/private-logs/03-baseline-validation.log" \
  validate "/path/to/baseline" --full --no-cache
pymo --log-file "/path/to/private-logs/04-working-validation.log" \
  validate "/path/to/working-collection" --full
```

Validation status 1 means findings require review; it does not authorize repair,
quarantine, or exclusion. Unreadable, unstable, or unsupported evidence must
remain visible.

## Stage 2: prove the initial copy

```bash
pymo --log-file "/path/to/private-logs/05-initial-verification.log" \
  verify-migration "/path/to/baseline" "/path/to/working-collection"
```

Require a complete result for the intended contract before transforming the
working copy. Read the exact-byte, exact displayed-image, and strict
decoded-video layers separately. Pixel or playback equivalence does not prove
metadata, encoding, container, or original bytes.

The guided coordinator and direct standalone `verify-migration` both reject
aliased baseline and working roots by no-follow filesystem identity before
work begins. Case, Unicode, or other aliases cannot make one physical directory
serve as both roles, while genuinely distinct case-sensitive directories remain
valid. An uncertain identity is an invalid setup rather than usable migration
evidence.

## Stage 3: correct truthful extensions

This stage becomes available in released version 0.5.9 and runs before
organization or deterministic renaming:

```bash
pymo --log-file "/path/to/private-logs/06-extension-preview.log" \
  correct-extensions "/path/to/working-collection"
pymo --log-file "/path/to/private-logs/07-extension-apply.log" \
  correct-extensions "/path/to/working-collection" --apply
```

Review the complete preview first. The command will change names only from
fresh descriptor-pinned, confident, unambiguous packaged content evidence,
will change no file bytes, and will journal collision-safe reversible renames.
Valid synonyms, shared container families, weak probes, unsupported or corrupt
media, meaningful non-media content, and custom extensions remain untouched.
TIFF-derived image and camera-raw identities, audio-capable video families, and
raw MPEG elementary streams are explicitly non-authoritative. Mapped images
must fully decode every frame. The command does not consume validation cache
evidence. An extensionless conclusive media file may receive its canonical
suffix. Re-run migration verification after apply.

Use the same released pymo version for every command touching the working
collection. An older pymo that encounters the newer `correct_extensions` tool
identifier in schema-1 action history fails closed rather than ignoring it.

## Stage 4: organize and rename

Preview, apply, and verify each mutation separately:

```bash
pymo --log-file "/path/to/private-logs/08-organize-preview.log" \
  organize "/path/to/working-collection"
pymo --log-file "/path/to/private-logs/09-organize-apply.log" \
  organize "/path/to/working-collection" --apply

pymo --log-file "/path/to/private-logs/10-rename-preview.log" \
  rename "/path/to/working-collection"
pymo --log-file "/path/to/private-logs/11-rename-apply.log" \
  rename "/path/to/working-collection" --apply
```

After each apply, require the command's own verification and run fresh
directional migration verification against the unchanged baseline. Stop on any
unexpected result; do not continue merely because a later stage might pass.

## Stage 5: isolate exact media duplicates

Run image and video analysis independently because they own distinct folders
and exactness policies:

```bash
pymo --log-file "/path/to/private-logs/12-image-dups-preview.log" \
  find-image-duplicates "/path/to/working-collection"
pymo --log-file "/path/to/private-logs/13-image-dups-apply.log" \
  find-image-duplicates "/path/to/working-collection" --apply

pymo --log-file "/path/to/private-logs/14-video-dups-preview.log" \
  find-video-duplicates "/path/to/working-collection"
pymo --log-file "/path/to/private-logs/15-video-dups-apply.log" \
  find-video-duplicates "/path/to/working-collection" --apply
```

Image groups prove exact displayed pixels and video groups prove strict decoded
playback; neither finder is limited to byte-identical files. Nothing is deleted.
The `dups` tree remains part of ordinary migration verification. An explicit
simulation excludes it only from counterfactual evidence; external quarantine
removes it from the working root.

## Stage 6: simulate and choose duplicate disposition

Version 0.5.10 provides the required zero-write preview:

```bash
pymo --log-file "/path/to/private-logs/16-without-dups-simulation.log" \
  verify-migration "/path/to/baseline" "/path/to/working-collection" \
  --simulate-without-dups
```

The simulation freshly hashes the complete physical destination, inventories
`dups` separately, and prevents its regular files from satisfying destination
byte, pixel, or playback coverage. It also removes those files from simulated
multiplicity and destination-only accounting while retaining fail-closed unsafe,
unreadable, unstable, ignored, and other excluded evidence. Schema-5 JSON and
human output label every layer and final verdict simulated. A simulated
complete result is eligible only for human duplicate-disposition review. Its
status 0 therefore does not mean observed final sign-off; machine consumers
must require a later ordinary observed result with
`eligible-for-human-signoff`.

If the simulated evidence is acceptable after human review, either record
`--retain-dups` and keep the complete review tree physically in place, or move
the complete tree to retained quarantine outside the working root using a
separately reviewed procedure and record `--confirm-quarantine`. Do not delete
it. Then run ordinary fresh verification against the physical working
collection. That observed result, not the simulation or disposition record,
is the evidence that can enter final sign-off.

## Stage 7: final sign-off

1. Re-run full fresh validation on the working collection.
2. Re-run ordinary migration verification from baseline to working collection.
3. Confirm ignored and excluded entry counts and explicitly review any requested
   relative-path disclosures.
4. Confirm every applied pymo run committed in the append-only collection action
   log and that no interrupted run remains unresolved.
5. Record the named byte, image, video, and final layered verdicts in the
   external migration tracker.
6. Retain the baseline, source, and duplicate review storage under the chosen
   backup policy. Pymo completion never authorizes automatic deletion of any of
   them.

Version 0.5.11 reduces repetition by carrying one declared baseline, working
collection, and explicit private log directory through these stages. It
preserves the same stop points, previews, exit statuses, fresh evidence, and
human sign-off rather than turning the sequence into an unattended batch.
Version 0.5.12 retains and revalidates initial collection identities through
strict existing-root ancestry checks, so a
temporary disappearance or replacement cannot turn an alias into accepted
separation. It also resolves every coordinator path before any requested log
state is created. Case or Unicode aliases cannot make one physical directory
serve both collection roles or hide a log directory inside either collection.
Coordinator setup, unsafe-state, and invocation errors return status 2; a
`--run-next` attempt returns the child command's real status. Version 0.6.0's
`--run` selector retains that exact status behavior while chaining only routine
successes and revalidating collection identities between them.

Version 0.6.2 promotes the human synopsis to normal coordinator output. Retain
the external migration record as the operator's durable record and do not treat
the private outcome files as a stable interchange format. Version 0.6.4 exposes
only their selected aggregate projection as the separate versioned
machine-readable report contract.
Version 0.6.8 advances that projection to schema 2 and distinguishes pending,
retained-in-place, not-applicable, and externally retained-but-unverified
review storage. It does not change the final ordinary evidence requirement.
Before any resumed action, the coordinator revalidates every required private
outcome through its pinned private-directory boundary. Missing, replaced,
publicly readable, or malformed history stops before another child is run.
Version 0.6.3 lets that same strict continuation be located with
`--resume PRIVATE_STATE_DIRECTORY`; it adds no evidence or authorization and
does not change the original two-root form.
