# ADR 0097: Pre-authorized unattended migration

- Status: Accepted
- Date: 2026-09-12
- Builds on: ADR 0089

## Context

Versions 0.6.0 through 0.6.4 retain the one-stage migration engine while adding
safe foreground advancement, terminal questions, an aggregate human synopsis,
explicit saved-context resume, and stable path-private reporting. They still
require an operator to answer each validation, reviewed-apply, external-
quarantine, and final-signoff checkpoint while the run is active.

Long-running local analysis makes that supervision burdensome. An operator who
already knows the exact decisions they are willing to approve needs a way to
state those decisions before the run without creating a general yes-to-all
switch or turning coordinator bookkeeping into evidence.

## Decision

Version 0.6.5 adds `pymo migrate --unattended PRIVATE_POLICY_JSON` over the
existing one-stage coordinator. It may initialize a new explicitly located
private run when positional roots and `--log-dir` are supplied, or continue one
exact existing run through `--resume`. The selector is mutually exclusive with
every other workflow action and never accepts `--apply`.

Policy schema 1 has exactly six top-level fields: `schema_version`,
`tool_version`, canonical absolute `baseline` and `working` roots, the complete
saved coordinator `options` object, and an ordered `authorizations` list. Each
authorization names one known checkpoint, its one allowed decision, and the
exact aggregate typed outcome expected from the preceding evidence stage.
Authorizations may be omitted deliberately, but must be unique and follow
workflow order. An omitted current checkpoint is an ordinary attention-needed
stop, not implied consent.

Validation authority binds status, inventory bytes and counts, health counts,
sorted finding severity/code/count triples, and whether a cache issue exists.
No policy may accept incomplete discovery or a cache issue. Apply authority
binds the matching successful transformation or exact-duplicate preview,
including its complete aggregate plan and a versioned SHA-256 digest of the
ordered private source/target decisions and the descriptor-pinned SHA-256 of
every planned source. This prevents an equal-count or same-path but different-
content plan from inheriting authority. The coordinator passes that reviewed
digest privately to the apply child, which recomputes and compares the current
plan before its first mutation; organization and rename also carry that exact
file evidence into the journaled move boundary. External-quarantine authority binds a
successful complete without-`dups` simulation and its review-tree totals.
Final-signoff authority binds a successful complete ordinary final
verification with no unaccounted or unsupported source content. Policy
authority never substitutes for those freshly executed outcomes.

The policy is path-sensitive private data. It must be a stable no-follow
regular file outside both collections, no larger than one MiB, with one hard
link and no group or other permissions. Its exact bytes and filesystem identity
are fixed for the invocation and rechecked throughout the loop. The first
unattended use creates a separate private create-once, no-replace binding
record containing the policy payload SHA-256 and the run's exact version,
roots, options, and creation time, then stores the same digest in private
restart state. The binding record, state, and byte-identical policy must agree
on every later unattended resume. The exact policy bytes may be relocated to
another safe private path, but editing, reformatting, or substituting policy
content is rejected. Pymo never replaces the independent binding record and
fails closed if it is missing, unsafe, malformed, or inconsistent. Unattended
operation requires the log directory itself to be owner-private and rejects
ancestry writable by another user except where sticky-directory ownership
semantics protect the next component. Every ancestry component must be owned by
root or the current user, preventing an untrusted owner from making a previously
non-writable parent replaceable later. It checks this before opening the
coordinator lock. If binding creation succeeds but initial state publication
does not, the same byte-identical policy may recover the recorded creation time
and publish only the missing initial state; it never replaces the binding. The
coordinator also revalidates
strict restart history, typed outcomes, the exact pymo version, saved options,
roots, creation binding, and both live collection identities between children
and immediately before a pre-authorized transition.

An exact match records the same existing checkpoint action used by interactive
operation: successful review acknowledgement, status-one acknowledgement,
reviewed apply, quarantine confirmation, or sign-off. This records that the
operator authorized the decision conditionally in advance; it does not claim
that a person was present at that moment and remains bookkeeping rather than
preservation evidence. One authorization never covers a later checkpoint.

A valid policy with missing or mismatched expected evidence stops path-
privately with status 1 before that checkpoint. Malformed, unsafe, changed, or
binding-mismatched policy and unsafe coordinator state stop with setup status 2.
An unexpected child status is recorded and returned unchanged. Ctrl-C remains
130. A present working `dups` path returns status 1 at external quarantine;
the same unchanged policy may resume only after the operator separately moves
or retains that complete tree and the working path is absent.

The mode will not move quarantine, delete media, weaken preview-before-apply,
broaden one authorization to a later checkpoint, fabricate evidence or human
sign-off, alter the action journal, change exact-media analysis, or add logging,
visibility, queue, or scheduling behavior.

## Consequences

- Unattended operation remains explicit, local, versioned, and fail closed.
- Repeated, well-understood collection shapes can complete in one invocation;
  first-time or changing collections remain better suited to manual or
  interactive review until their expected evidence is known.
- The existing one-stage engine and interactive/manual selectors remain
  compatible and authoritative for their current boundaries.
- The public policy contract is documented separately from private restart and
  outcome schemas; incompatible policy changes require a schema-version change.
- Automatic duplicate disposition and permanent cleanup remain outside this
  release.
