# Contributing and release workflow

Unless explicitly stated otherwise, a contribution intentionally submitted for
inclusion in this project is accepted under the Apache License, Version 2.0,
without additional terms or conditions.

This project favors small, auditable changes and conservative media safety.
Read the root `AGENTS.md`, `HANDOFF.md`, and relevant ADRs before changing
behavior.

## Local setup

```bash
uv sync --locked
uv run --locked pre-commit install
```

FFmpeg and ffprobe are external runtime dependencies for real video integration
tests. They are intentionally not bundled through a Python wrapper.

## Branches and review

1. Start a short-lived branch from current `main`. Use a descriptive prefix
   such as `fix/`, `feature/`, `docs/`, or `ci/`.
2. Keep one primary purpose per branch and patch release.
3. Add synthetic tests and update the changelog, roadmap, handoff, and ADRs that
   are affected by the same change.
4. Run the local gate before pushing:

   ```bash
   uv run --locked pre-commit run --all-files
   uv run --locked pytest --cov=pymo --cov-report=term-missing
   uv build
   ```

5. Push the branch and open a pull request targeting `main`. Ordinary branch
   pushes do not run CI automatically.
6. Require the unconditional pull-request `quality-gate` to pass before a
   no-fast-forward or GitHub pull-request merge into `main`.
7. Confirm the automatic `quality-gate` passes on the resulting merge commit.
8. GitHub automatically deletes the merged remote head branch. Delete the
   corresponding local branch and prune stale remote-tracking refs as local
   maintenance.
9. Do not place an ordinary feature or fix commit directly on `main`.

Use manual workflow dispatch when full-platform evidence is needed outside a
pull request. Each platform job has a ten-minute ceiling. Repository Actions is
enabled with read-only tokens, immutable action references, a narrow action
allowlist, and approval required for every external contributor.

GitHub API readback confirms active no-bypass rulesets for public `main` and
`refs/tags/v*`. Never force-push or delete `main`, never merge without an
up-to-date pull request and the configured required check, and resolve every
review conversation first. Release tags cannot be updated or deleted. ADR 0081
supersedes ADR 0046's former private-Free eligibility boundary.

## Versioned public controls

Version 0.5.8 completes the controlled public transition under ADR 0081. It
adopts Apache-2.0 and replaces individual platform checks as the ruleset
interface with one repository-owned, unconditional `quality-gate`:

| Event | Versioned evidence |
| --- | --- |
| Ordinary branch push | None; a pull request owns pre-merge evidence. |
| Pull request | Always classify the change and publish `quality-gate`. Documentation-only changes run documentation/privacy checks; runtime, packaging, toolchain, and workflow changes run Ubuntu, pinned Fedora, and macOS. |
| Push to `main` | Repeat the applicable gate on the exact merge commit. |
| `v*` tag | Check eligible `main` ancestry, versioned artifacts, and an isolated Linux installation without repeating the complete platform suite. |
| Manual dispatch | Run an explicitly requested bounded full-platform diagnostic. |
| Schedule | Nothing until a separate maintenance decision exists. |

Required-check workflows must not use trigger path filters that can leave a
required check pending. A repository-owned classifier fails closed, conditional
jobs follow its outputs, and the aggregate job runs with `always()` semantics
and fails unless every job required for that scope succeeded. Workflows retain
read-only permissions, pinned third-party actions and containers, bounded
runtime, no pull-request secrets, and no self-hosted execution of untrusted
code. Every external contributor requires maintainer approval before a workflow
runs.

The active ruleset targets only `refs/heads/main`, with no bypass actors, and
must continue to:

- block force pushes and branch deletion;
- require a pull request, current branch, resolved conversations, and the
  GitHub-Actions-owned `quality-gate`;
- require zero approvals while there is only one human maintainer, because a
  required approval would make legitimate self-merges impossible; and
- retain merge commits as the explicit release boundary.

The second active ruleset for `refs/tags/v*` prevents updates and deletion. Do
not require linear history or signed commits under the current policy. Merge
through GitHub instead of pushing a locally created merge commit to `main`.
Read both rulesets back through the API after any hosted policy change.

Public issues use structured privacy-conscious forms with blank issues disabled.
Security reports use `SECURITY.md` plus GitHub private vulnerability reporting.
Discussions, the wiki, and other unused interaction surfaces remain disabled
initially.

## Release classification

- Patch: one backward-compatible correction, safety hardening, internal
  refactor, or small additive behavior with one primary purpose.
- Minor: a coherent new subsystem, command family, or intentional pre-1.0
  compatibility boundary.
- Major: the stable post-1.0 incompatible-change boundary.

Double-digit patch numbers are expected. Do not combine unrelated work to keep
the tag count small.

## Release procedure

1. Ensure the roadmap target, changelog entry, handoff, tests, and any ADR are
   complete on the release branch.
2. Pass the local gate, open the pull request, and pass its `quality` checks.
3. Merge the branch into `main` and verify the automatic checks on the merge
   commit.
4. Create an annotated `vX.Y.Z` tag on the verified merge commit.
5. Push the tag. The tag is the authoritative package version through
   hatch-vcs and runs the narrower release workflow when Actions is enabled.
6. Force-refresh the local editable installation and verify the exact CLI
   version after creating the tag:

   ```bash
   uv sync --locked --reinstall-package python-media-organizer
   uv run --locked pymo --version
   uv build
   ```

The CLI version must equal the tag without a development suffix, and both
distributions must build from the tagged commit.

The package is not currently published to PyPI. A release means a verified Git
tag plus locally buildable source and wheel artifacts.

Version 0.5.8 tag pushes run the narrower ancestry, artifact, and
isolated-install proof recorded in ADR 0081 whenever Actions is enabled. That
post-tag job is additional evidence; it never authorizes creating a tag before
the exact `main` commit has passed its applicable gate.
