# ADR 0046: Defer main protection until the private repository is eligible

- Status: Accepted
- Date: 2026-08-22

## Context

The repository is intentionally private and owned by a GitHub Free personal
account. On 2026-08-22, authenticated requests to both the repository-ruleset
and classic branch-protection APIs returned HTTP 403 with instructions to
upgrade to GitHub Pro or make the repository public. GitHub's documented
availability matches that result: Free accounts receive these protections for
public repositories, while private repositories require Pro, Team, or
Enterprise. See GitHub's availability notes for
[protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)
and [repository rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets).

The project still needs `main` to reject deletion and non-fast-forward pushes,
and it should enforce the pull-request, platform-check, and conversation
resolution process already followed manually. Pretending those controls are
active would be less safe than recording the actual boundary.

## Decision

Keep the repository private. Until GitHub Pro is enabled or the user explicitly
makes the repository public, treat the following rules as mandatory procedure:
never force-push or delete `main`; use a pull request; require all three
platform checks; and resolve every review conversation before merge.

As soon as the repository is eligible, create one active ruleset targeting
only `refs/heads/main`, with no bypass actors. It must:

- restrict branch deletion;
- block force pushes;
- require a pull request with review-thread resolution;
- require `quality (ubuntu-latest)`, `quality (macos-latest)`, and
  `quality (fedora-42)` against the current branch; and
- require zero approving reviews while the repository has only one maintainer.

Do not require linear history because the project deliberately uses merge
commits for release boundaries. Do not require signed commits until signing is
introduced in a separate decision. After activation, use GitHub's pull-request
merge operation instead of pushing a local merge commit directly to `main`.
Verify the active rules through GitHub's API before calling the branch
protected.

## Consequences

Server-side protection is unavailable while the current private-Free boundary
remains. Local hooks, CI, and documented discipline reduce mistakes but cannot
technically prevent an authenticated force push or branch deletion. A Pro
upgrade or deliberate public transition unlocks the specified enforcement
without requiring a design revisit. This decision clarifies the eligibility
assumption in ADR 0042; it does not weaken its branch-and-review policy.
