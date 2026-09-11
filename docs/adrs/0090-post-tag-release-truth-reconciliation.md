# ADR 0090: Reconcile release truth only after tag proof

- Status: Accepted
- Date: 2026-09-11
- Extends: ADR 0086

## Context

A release candidate is not released merely because its local tests, independent
review, pull-request checks, or proposed release notes are complete. Calling it
released before the protected merge, exact-main quality gate, annotated tag,
and tag-triggered build are proven turns an expectation into a historical
claim.

The immutable tagged tree cannot both describe that tag as already published
and avoid anticipating publication. Current release status therefore belongs
in the latest authoritative documentation on `main`, reconciled after the tag
boundary exists.

## Decision

Before publication, the changelog labels the pending version `Unreleased` and
the roadmap labels it a release candidate. The release owner may create the
annotated version tag only after the reviewed pull request is merged and the
exact merge commit passes its required `main` quality gate.

After the remote tag object, peeled commit, and tag-triggered release workflow
are verified, a separate documentation-only pull request updates the changelog
date, roadmap status, and release evidence. That reconciliation does not move
or recreate the immutable tag and is not a second package release. It follows
the ordinary review and documentation/privacy gate, and it states explicitly
that the tagged source contains the truthful pre-publication ledger state.

## Consequences

- Release documentation never predicts a merge, tag, or hosted result.
- The latest `main` branch becomes the authoritative current-status view after
  a small post-tag reconciliation change.
- A tagged source archive may retain `Unreleased` or release-candidate wording
  that was true immediately before publication; the immutable tag and its
  verified workflow remain the package-version authority.
- A release worktree can be disposed after its product contribution, tag,
  installed-tool state, and integration are confirmed. The post-tag record uses
  its own branch and worktree.
