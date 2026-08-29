# ADR 0081: Adopt public governance and contained continuous integration

- Status: Accepted
- Date: 2026-08-29

## Context

The repository is private under GitHub Free. Hosted Actions are deliberately
disabled after the private allowance was exhausted, and GitHub does not expose
branch protection or rulesets for this private repository on the current plan.
The project therefore has strong procedural release controls but cannot yet
enforce them at the server boundary.

The maintainer intends to make the repository public only after its licensing,
contribution, issue, security-reporting, workflow, branch, and tag policies are
ready. Public standard GitHub-hosted runners remove the private-minute
constraint, but unlimited minutes do not justify running redundant or
unbounded workflows. Public pull requests also introduce untrusted workflow
input and require an explicit approval and least-privilege policy.

Repository authority and source licensing are separate boundaries. A license
governs what recipients may do with their copies; GitHub rules govern who may
change this repository, merge to `main`, publish a tag, or consume hosted
automation.

## Decision

Adopt the Apache License, Version 2.0 in version 0.5.8. Add the complete license
at the repository root, declare the SPDX expression in package metadata, and
state in contribution guidance that accepted contributions use the same
license. The explicit copyright and patent grants, patent-termination clause,
notice-retention requirements, and absence of a trademark grant fit a
permissive public utility while preserving clear project identity. No history
rewrite is required before the visibility change.

Keep the repository private until the versioned public-readiness changes have
passed their release boundary and the maintainer separately authorizes the
hosted visibility change. Changing visibility, enabling Actions, configuring
issue/security features, and activating rulesets are external operations rather
than effects of installing or tagging the package.

When public, configure Actions with this event contract:

| Event | Required work |
| --- | --- |
| Ordinary branch push | No workflow run. Pull requests own pre-merge evidence. |
| Pull request | Always run a repository-owned change classifier and one unconditional `quality-gate`. Run documentation/privacy checks for documentation-only changes. Run the complete Ubuntu, pinned Fedora, and macOS gates for runtime, packaging, toolchain, or workflow changes. |
| Push to `main` | Repeat the applicable checks on the exact merge commit. A later tag cannot retroactively certify an unchecked commit. |
| `v*` tag | Verify that the tag targets an eligible verified `main` commit, build wheel and source distributions, confirm artifact versions, and install the wheel in isolation on Linux. Do not repeat the full platform suite already required on the exact commit. |
| Manual dispatch | Permit an explicitly requested full-platform diagnostic or release-candidate run with bounded inputs. |
| Schedule | Run nothing until a separate maintenance need and decision exist. |

The classifier compares repository-owned base and head commit identities and
fails closed if it cannot determine scope. Do not rely on GitHub trigger path
filters for a required check: a required workflow must always produce the
stable aggregate result. The aggregate job runs with `always()` semantics and
fails unless every job required for the classified change succeeded. GitHub
Actions remains the expected source of that required status.

Keep workflow permissions read-only by default, pin third-party actions and
containers by digest, cap job runtimes, expose no repository secrets to pull
request code, and never attach a self-hosted runner to an untrusted public pull
request. Require maintainer approval before workflows run for every external
contributor, not merely a contributor's first pull request.

After the repository becomes public, activate and verify through the GitHub API
one no-bypass ruleset for `refs/heads/main` that:

- blocks force pushes and deletion;
- requires a pull request, an up-to-date branch, resolved conversations, and
  the unconditional `quality-gate` from GitHub Actions;
- requires zero GitHub approvals while there is only one human maintainer, so
  the maintainer is not locked out of legitimate self-merges;
- permits merge commits because the explicit merge boundary is part of release
  history; and
- does not require signed commits until signing is adopted and proven
  separately.

Add a tag ruleset for `refs/tags/v*` that prevents update and deletion after
creation. Do not claim either ruleset is active until the live API returns the
expected configuration.

Keep public interaction structured. Disable blank public issues, provide
privacy-conscious bug and feature forms, add a security policy, and enable
private vulnerability reporting. New issue forms must warn against posting
media, collection names, private paths, or unreviewed logs. Leave discussions,
the wiki, and other unused surfaces disabled initially. Temporary GitHub
interaction limits remain an incident-response control rather than a permanent
substitute for triage.

## Activation sequence

1. Restore hosted capacity and re-enable Actions while the repository remains
   private.
2. Complete the exact pull-request and exact-`main` checks, merge, and tag
   version 0.5.7.
3. Rebase the implemented version 0.5.8 branch onto that verified `main` and
   repeat its complete local gate so the stacked history does not substitute
   for evidence against the release base.
4. Complete independent review, the local gate, exact pull-request checks,
   exact-`main` checks, tag verification, and installed-version proof for
   version 0.5.8 while the repository is still private.
5. Re-run the repository/history/privacy audit and obtain the maintainer's
   explicit visibility authorization.
6. Make the repository public, enable Actions, require approval for every
   external contributor's workflow, configure issue and private-security
   reporting, and activate the branch and tag rulesets.
7. Read the hosted settings back through the API and run a deliberate public
   full-platform certification before calling the transition complete.

## Consequences

- The source becomes genuinely open source under a permissive license with an
  explicit patent boundary; forks do not gain authority over this repository,
  its `main` branch, releases, or project identity.
- Public standard-runner availability permits full platform coverage where it
  supplies real evidence, while stable classification and aggregation prevent
  redundant or skipped-required-check behavior.
- Sole-maintainer operation remains possible without weakening the PR,
  conversation, exact-commit, force-push, deletion, and tag boundaries.
- Public visibility exposes repository history, pull requests, issues, and
  available Actions logs. The final audit is therefore an activation gate, not
  a documentation formality.
- This decision supersedes ADR 0046's eligibility prerequisite once the live
  public rulesets are verified. Until then, ADR 0046's procedural boundary
  remains current. It also supersedes the unshipped private-minute trigger
  design drafted for version 0.5.8; useful tag-verification and event-separation
  ideas survive only where they match this contained public contract.

## Primary references

- Apache License, Version 2.0:
  <https://www.apache.org/licenses/LICENSE-2.0.html>
- GitHub Actions billing and public standard runners:
  <https://docs.github.com/en/billing/concepts/product-billing/github-actions>
- GitHub repository rulesets:
  <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets>
- Approval for workflows from public forks:
  <https://docs.github.com/en/actions/how-tos/manage-workflow-runs/approve-runs-from-forks>
- GitHub issue-template controls:
  <https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository>
- GitHub private vulnerability reporting:
  <https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately>
