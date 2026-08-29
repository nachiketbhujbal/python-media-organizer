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
