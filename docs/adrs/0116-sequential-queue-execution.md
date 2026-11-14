# ADR 0116: Sequential queue execution

- Status: Accepted
- Date: 2026-11-13
- Builds on: ADR 0114, ADR 0112, ADR 0097

## Context

Queue declarations are validated without execution in version 0.7.2. Running
several approved collection workflows must preserve independent state, exact
policy bindings, fresh checkpoint evidence and first-failure stopping.

## Decision

Reserve version 0.7.3 for `pymo queue run MANIFEST`. Without `--apply` it
performs the existing zero-write declaration plan. Explicit `--apply` starts
new jobs in declared order through the existing unattended migration engine.
The manifest itself supplies no checkpoint authority; each complete reviewed
policy remains authoritative only for its exact roots, version and evidence.

Validate the complete queue before creating state. Revalidate bindings before
each job, exclusively create its declared private state directory, and never
adopt an occupied destination. Preserve every started job's state and logs on
failure or interruption. Advance only after exact successful completion and
strict outcome/lifecycle verification; return the first unhandled status.

Retry, resume, skip, aggregate queue reporting and concurrency remain separate
roadmap units. This command performs no initial copying or permanent cleanup
and does not turn queue completion into source-removal authority.

## Acceptance

Require synthetic multi-job execution, dry-run immutability, policy and root
substitution refusal, late destination occupation, interruption and exact
status propagation, first-failure stopping, independent exact-SHA review and
the complete release gates. No production collections are required.

## Review-led hardening

Independent review reproduced a replaced-lock window and a replaced-directory
write path in the initial candidate. The queue now carries an ephemeral private
I/O binding through the existing engine and children. It binds full no-follow
ancestry, the allocated lock inode and each exclusively allocated stage-log
inode, constrains log/outcome creation and
restart reads/replacement to the original directory, and rechecks the lock at
engine transitions. Private child arguments carry only that constraint, never
checkpoint authority. No persistent schema or standalone migration default
changes. Partial state and staging artifacts remain retained for inspection.

Binding failures in child outcome I/O use the existing controlled, path-private
error boundary. A changed binding must not emit raw exceptions or tracebacks.

## Independent implementation review

Terra-medium review accepts `c0409fd85e31a9672c9538930bf05620904f5dbc` after
independently closing QUEUE-EXEC-R01 through R04. Its focused runs passed 131
queue/outcome tests and the three lifecycle substitution tests. The owner
passed 140 focused tests, static/all-file hooks, 862 complete-suite tests with
two existing filesystem skips at 88 percent subprocess-aware coverage, and
isolated installed-wheel acceptance. The exact release and hosted gates remain
separate prerequisites.
