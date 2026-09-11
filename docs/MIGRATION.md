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
operator loop stops before every apply, after any nonzero child status, at the
external-quarantine checkpoint, and after final evidence becomes eligible for
human sign-off. It asks no questions and grants no mutation authority.
[ADR 0087](adrs/0087-operator-first-migration-roadmap.md) keeps interactive
checkpoints, reports, saved context, logging and visibility policy, duplicate
disposition, queues, and benchmark-gated scheduling as separate later releases;
[ADR 0088](adrs/0088-safe-migration-operator-loop.md) records this first loop
boundary.

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
First inspect the zero-write plan, then explicitly initialize one dedicated
private directory outside and non-nested with both collections:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection"
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs" --start
```

Common `--config`, `--show-ignored`, `--show-files`, `--verbose`/`--quiet`, timestamp,
`--workers`, `--no-cache`, ffmpeg/ffprobe, and decode-timeout choices supplied
at `--start` are fixed in schema-1 restart state and carried only to applicable
child commands. Later explicit options must agree with that state. Use the same
released pymo version for the complete sequence.

Inspect current state without advancing it, execute exactly one pending stage,
or advance routine work to the next operator checkpoint:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs"
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs" --run-next
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs" --run
```

`--run` chains only routine successful evidence and preview children. It reloads
the strict restart lifecycle without changing its roots, version, options, or
creation binding, and verifies both collection-directory identities between
stages. A successful preview pauses before its distinct mutation checkpoint.
After reviewing that preview, authorize only the pending child:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs" --run-next --apply
```

Then use `--run` again to continue routine evidence work. Use `--run-next`
instead whenever exactly one child stage is desired.

A nonzero child status is recorded, returned unchanged, and stops both modes.
Rerun after resolving the cause. Status 1 from a validation checkpoint may be
advanced only after human review with `--accept-status`; the original status
remains in state. Verification, mutation, configuration, discovery, and native
tool failures cannot be acknowledged away.

After the successful without-`dups` simulation, `--run` stops normally and
returns 0 at the expected external-quarantine checkpoint. Move or
retain the complete review tree outside the working collection using a
separately reviewed procedure; pymo performs no move. Once the working `dups`
path is absent, record the human checkpoint:

```bash
pymo migrate "/path/to/baseline" "/path/to/working-collection" \
  --log-dir "/path/to/private-logs" --confirm-quarantine
```

That confirmation proves only path absence plus the operator's acknowledgement,
not quarantine retention. A later `--run` performs final fresh validation and
ordinary observed verification, then stops at the human-signoff boundary.
Restart state and stage logs
are private operational records, not the collection action journal, current
media evidence, or deletion authority. An interrupted apply may have committed
its own append-only action run even if coordinator state did not advance; review
the child log and action history before rerunning.

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
The `dups` tree remains part of ordinary migration verification until an
explicit simulation or external quarantine removes it from the working root.

## Stage 6: simulate and quarantine duplicate review material

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
complete result is eligible only for human quarantine review. Its status 0
therefore does not mean observed final sign-off; machine consumers must require
an ordinary observed result with `eligible-for-human-signoff` after the move.

If the simulated evidence is acceptable after human review, move the complete
review tree to retained quarantine outside the working root using a separately
reviewed procedure. Do not delete it. Then run ordinary fresh verification
against the physical working collection and compare it with the simulation.
Only the ordinary post-move result can enter final sign-off.

## Stage 7: final sign-off

1. Re-run full fresh validation on the working collection.
2. Re-run ordinary migration verification from baseline to working collection.
3. Confirm ignored and excluded entry counts and explicitly review any requested
   relative-path disclosures.
4. Confirm every applied pymo run committed in the append-only collection action
   log and that no interrupted run remains unresolved.
5. Record the named byte, image, video, and final layered verdicts in the
   external migration tracker.
6. Retain the baseline, source, and quarantine under the chosen backup policy.
   Pymo completion never authorizes automatic deletion of any of them.

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

The released coordinator does not yet synthesize the final operator report.
Record initial and final inventory and health, extension corrections,
organization and rename counts, image/video duplicate counts and potential
storage recovery, quarantine disposition, cache reuse, stage durations, known
warnings, and the final preservation verdict in the external migration record.
Version 0.6.2 promotes that synopsis to normal pymo output; version 0.6.4 adds
its stable machine-readable artifact.
