# Contributing and release workflow

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
   pushes do not run CI automatically while the repository is private.
6. Require all pull-request `quality` platform checks to pass before a
   no-fast-forward or GitHub pull-request merge into `main`.
7. Confirm the automatic `main` checks pass on the resulting merge commit.
8. GitHub automatically deletes the merged remote head branch. Delete the
   corresponding local branch and prune stale remote-tracking refs as local
   maintenance.
9. Do not place an ordinary feature or fix commit directly on `main`.

Use manual workflow dispatch when platform evidence is needed before opening a
pull request or for an exceptional tag investigation. Each platform job has a
ten-minute ceiling. Version tags do not rerun the matrix automatically while
the repository is private.

GitHub Free exposes protected branches and rulesets only for public
repositories. Its APIs return HTTP 403 for this private repository, so the
following boundary is currently procedural: never force-push or delete `main`,
never merge without a pull request and every configured `quality` check, and
resolve every review conversation first. ADR 0046 remains current until a live
public ruleset is verified.

## Planned public controls

Version 0.5.8 prepares a separately authorized public transition under ADR
0081. It adopts Apache-2.0 and replaces individual platform checks as the
ruleset interface with one repository-owned, unconditional `quality-gate`.
None of the following is active merely because it is documented:

| Event | Planned evidence |
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

After the versioned preparation and an explicit visibility authorization,
activate one ruleset targeting only `refs/heads/main`, with no bypass actors:

- block force pushes and branch deletion;
- require a pull request, current branch, resolved conversations, and the
  GitHub-Actions-owned `quality-gate`;
- require zero approvals while there is only one human maintainer, because a
  required approval would make legitimate self-merges impossible; and
- retain merge commits as the explicit release boundary.

Add a second ruleset for `refs/tags/v*` that prevents updates and deletion.
Do not require linear history or signed commits under the current policy. Once
the no-bypass ruleset is active, merge through GitHub instead of pushing a
locally created merge commit to `main`. Read both rulesets back through the API
before describing `main` or release tags as protected.

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
   hatch-vcs; it does not rerun CI automatically while the repository is
   private.
6. Force-refresh the local editable installation and verify the exact CLI
   version after creating the tag:

   ```bash
   uv sync --locked --reinstall-package python-media-organizer
   uv run --locked pymo --version
   uv build
   ```

The CLI version must equal the tag without a development suffix, and both
distributions must build from the tagged commit. A manual workflow dispatch on
the tag is available when remote tag verification is specifically warranted.

The package is not currently published to PyPI. A release means a verified Git
tag plus locally buildable source and wheel artifacts.

After version 0.5.8 activates its public workflow, tag pushes run the narrower
artifact and isolated-install proof recorded in ADR 0081. That post-tag job is
additional evidence; it never authorizes creating a tag before the exact
`main` commit has passed its applicable gate.
