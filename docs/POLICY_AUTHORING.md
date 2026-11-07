# Review a migration before authorizing it

The v0.7.1 candidate adds `pymo policy plan`, `review`, and `accept` for a
complete retained-in-place migration. Planning and acceptance change no media,
collection layout, cache, lock or action history in either collection. They
read current files, including native full decoding when needed. They can be
expensive: acceptance recomputes the complete plan, and execution rechecks
namespace and bytes at every stage. No historical run or scratch media copy
supplies the plan.

## Commands

Prepare an existing owner-private directory outside both collections, with
mode `0700` and trusted ancestry. This directory must not be an ancestor of
either collection. Use fresh artifact names; pymo never replaces them.

```bash
pymo policy plan "/path/to/baseline" "/path/to/collection"
pymo policy plan "/path/to/baseline" "/path/to/collection" \
  --output "/private/planning/candidate.json" --apply
pymo policy review "/private/planning/candidate.json"
pymo policy accept "/private/planning/candidate.json" \
  --sha256 REVIEWED_CANDIDATE_SHA256 --output "/private/planning/policy.json"
pymo policy accept "/private/planning/candidate.json" \
  --sha256 REVIEWED_CANDIDATE_SHA256 --output "/private/planning/policy.json" --apply
```

The first command previews without writing. The second writes only the private
candidate. `review` shows all ten checkpoint decisions and their exact aggregate
expectations, including mutation digests, duplicate retention, and final sign-off.
The private candidate also lists each proposed source/target move and created or
removed directory. Candidate generation is not consent. `accept` defaults to a
preview; its separate `--apply` authorizes all listed decisions only if the exact
reviewed SHA-256, current version, target roots, source identities, content,
configuration, and recomputed complete plan still agree. It writes the
accepted policy and its separate acceptance receipt, never starts migration,
and grants no deletion authority. Keep both at their original paths; the receipt
is named by appending `.acceptance.json` to the policy filename.

Then use the existing executor, repeating the candidate's selected options:

```bash
pymo migrate "/path/to/baseline" "/path/to/collection" --no-cache \
  --log-dir "/private/run" --unattended "/private/planning/policy.json"
pymo migrate --resume "/private/run" --unattended "/private/planning/policy.json"
```

Authoring selects `--no-cache` deliberately. Optional `policy plan --config`,
`--ffmpeg`, `--ffprobe`, and `--decode-timeout` are saved in its exact execution
options and must also be repeated when starting the run. Existing guided full
validation uses system native tools; the native overrides belong to duplicate
analysis and migration verification. Changed options require a new plan.

Normal console output hides collection paths and filenames, including with
full visibility. Global persistent logging and disclosure selectors are refused;
explicit candidate and policy artifacts are the private output surfaces.
Artifact files are mode `0600`, owner-private, single-link regular files.
Candidates are bounded at 64 MiB; accepted policies retain the one-MiB limit.
Writes use verified private scratch and atomic no-replace publication. A policy
file alone is never authored execution authority: only after its exact published
bytes are verified is a separate receipt published, binding those bytes, the
reviewed candidate SHA-256, the exact policy path and tool version. The receipt
also binds the verified policy inode and its own exclusively allocated inode;
an identical-byte replacement does not inherit acceptance. The executor
requires both files and rechecks their bytes and identities during execution.
Interrupted or substituted artifacts are retained for manual review and are
never automatically adopted. A failed publication can leave a policy file
without a valid receipt, which cannot run. Use fresh output names after failure;
pymo does not remove or replace either file.

## Supported planning boundary

The complete workflow composes extension correction, organization, deterministic
renaming, exact image and video isolation, simulated verification without `dups`,
retained-in-place disposition, fresh final validation, and layered preservation.
Logical names drive naming/classification policy while stable descriptors still
read the unchanged original bytes. No planned move is applied during authoring.
Ignored entries remain protected; their entry identities are bound without
reading their content. Source bytes, embedded metadata and all duplicate media
remain present during execution; retaining `dups` reclaims no physical storage.

Planning refuses incomplete discovery, unsafe or changing input, uninspectable
media, unsupported exact analysis, ambiguous case-folded names, noncanonical
reserved directory spellings, occupied destinations, ignored review-tree entries,
or existing working action history. Healthy warnings such as a correctable
extension mismatch remain visible and may be reviewed. A partial plan is never
published as a complete candidate.

Managed quarantine is an explicit unsupported virtual transition: its existing
exact manifest includes future directory identities and change times that cannot
be known before isolation. `--quarantine-destination` therefore stops authoring
without a candidate. Existing stage-by-stage and manually authored schema-4
managed-copy/rename workflows remain available. This restriction does not weaken
their exact manifest or fresh verification checks. Human-managed external
quarantine is likewise not predicted by this authoring command.

Interrupted execution keeps the normal action journals and strict stage engine.
If a child partially moved files before interruption, the authored namespace no
longer matches its pending stage: unattended resume refuses further mutation.
Inspect the journal and use the existing reviewed recovery/undo workflow; do not
edit policy or restart state to make it pass. Automatic queue recovery is later
work. Production cleanup and migration readiness remain separate decisions.

## Candidate schema 1

The UTF-8 JSON object has exactly `schema_version: 1`,
`kind: "unaccepted-migration-plan"`, `policy`, and `transitions`. `policy` is the
proposed schema-5 fields without an acceptance declaration or receipt.
Extracting the proposed inner object does not produce executable authority.
`transitions` contains the five preview stages, each with `stage`, `moves`, `create_directories`, and
`remove_directories`. Each move has collection-relative `source`, `target`,
whole-file `sha256`, and `bytes`. This is sensitive local review material.
The wrapper is rejected by the unattended executor.

The displayed candidate SHA-256 covers the exact stored bytes, including JSON
formatting. Acceptance re-reads those bytes and recomputes every plan field;
changing either the artifact or declared target requires another review.

## Authored policy schema 5

Schema 5 retains every schema-4 field and adds `acceptance` and `plan_binding`.
`acceptance` has exactly `candidate_sha256` and the absolute `record` path. The
separate receipt has schema version 1, kind `accepted-migration-policy`,
`tool_version`, `candidate_sha256`, `policy_path`, `policy_sha256`,
`policy_identity`, and `record_identity`. The identity fields are ordered
`[device, inode]` integer pairs. The record identity comes from the pinned
exclusive scratch descriptor before writing, not from a later pathname lookup.
Its strict
contents must match the exact accepted policy; a missing or mismatched receipt
is refused before any run state is created. This is explicit local acceptance
evidence, not cryptographic proof against an owner who deliberately constructs
authority; manually authored schema 4 remains an independent supported path.

`plan_binding` contains:

- `baseline_initial`: SHA-256 over the initial baseline root identity, scoped
  paths, file identities, bytes, times, directory identities, and ignored entry
  observations.
- `working_initial`: the equivalent initial working snapshot.
- `working_stages`: 25 ordered namespace digests, before each of the 24 fixed
  stages and after the last stage. They bind root identity, logical paths,
  original file device/inode/size/mtime and SHA-256, directory names, and
  ignored entry observations. They omit future directory inodes and file ctimes,
  which cannot survive or precede a rename unchanged.
- `configuration`: the selected configuration paths and fresh content digests,
  with absence explicitly represented.

Digest input is canonical sorted-key compact JSON with a trailing newline.
Schema changes must version this contract. The accepted policy must authorize
all ten checkpoints and select retained duplicates. The initial baseline binding
remains required at every stage; initial working identity is additionally checked
through the first apply, and the corresponding planned namespace is checked
thereafter. Each existing child still recomputes its own evidence and exact
mutation digest immediately before apply. These bindings add constraints and
never turn bookkeeping into preservation evidence.

Schema 4 remains supported for existing manually prepared policy contracts.
Coordinator state, outcome, and report schemas do not change in this release.
