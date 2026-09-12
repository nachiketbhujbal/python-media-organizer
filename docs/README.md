# Project documentation

The repository root contains the package overview and the operational files
needed by coding agents. Durable engineering documentation lives here:

- [Roadmap](ROADMAP.md) — promoted releases, status, and acceptance criteria.
- [Changelog](CHANGELOG.md) — behavior that has shipped.
- [Research](RESEARCH.md) — evaluated products, open questions, and ideas that
  do not yet have a committed release.
- [Adversarial code review](CODE_REVIEW.md) — findings and their resolution
  history.
- [Contributing and releases](CONTRIBUTING.md) — local gates, branches, CI, and
  release procedure.
- [Production migration runbook](MIGRATION.md) — the collection-by-collection
  baseline, transformation, verification, quarantine, and sign-off sequence.
- [Stable migration report](MIGRATION_REPORT.md) — schema 2 invocation,
  compatibility, privacy, and authority boundaries for `migrate --json`.
- [Architecture](ARCHITECTURE.md) — package boundaries and allowed dependency
  direction.
- [Architecture decisions](adrs/README.md) — one durable decision per record.

Version 0.5.8 adds the selected Apache-2.0 license at the repository root so
hosting sites and package consumers can discover it reliably. ADR 0081 records
the public-governance and contained-CI decision plus the controlled early public
bootstrap. Branch, tag, workflow, and external-contributor controls are active;
issue and private-security intake follow the versioned files onto `main`.
Version 0.5.9 adds reversible truthful-extension correction;
ADR 0082 records its fresh-evidence, packaged-policy, journal, and ambiguity
boundaries.
Version 0.5.10 adds zero-write preservation simulation without destination
`dups`; ADR 0083 records its full physical inventory, filtered comparison,
explicit simulated-verdict, and post-quarantine verification boundaries.
Version 0.5.11 adds guided single-collection migration; ADR 0084 records its
one-stage execution, private restart/log state, explicit apply and validation
acknowledgement checkpoints, external-quarantine stop, and fresh final-proof
boundaries.
Version 0.5.12 hardens shared migration-root identity; ADR 0085 records its
alias-resistant, stable existing-root boundary. Version 0.5.13 reconciles the
current documentation with the verified 0.5.12 release and records
privacy-preserving real-collection workflow trials as the next product phase;
ADR 0086 records that documentation and evidence boundary.
The resulting operational evidence promotes an operator-first version 0.6
sequence; ADR 0087 records a fine-grained progression through operator control,
reporting, visibility, duplicate disposition, queue execution, and measured
concurrency. Version 0.6.0 adds only the foreground safe operator loop; ADR
0088 records its automatic-success and explicit-checkpoint boundaries. Version
0.6.1 adds the explicit terminal-only interactive selector; ADR 0089 records
its conservative per-question consent and private resume-state boundaries.
Version 0.6.8 adds retained-in-place duplicate disposition; ADR 0103 records
its no-move, no-delete, no-storage-reclamation, and fresh-final-evidence
boundaries.
