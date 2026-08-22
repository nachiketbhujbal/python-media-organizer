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

5. Push the branch and require the GitHub `quality` check to pass before a
   no-fast-forward merge or pull-request merge into `main`.
6. Do not place an ordinary feature or fix commit directly on `main`.

For a sole-maintainer GitHub ruleset, require a pull request, the `quality`
status check, and resolved conversations; block force pushes and branch
deletion. Do not require approval from another person unless another active
maintainer exists, because that would prevent legitimate self-merges. Repository
rules are configured in GitHub settings and are not stored by this workflow.

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
2. Pass the local gate and the branch `quality` check.
3. Merge the branch into `main` and verify the same check on the merge commit.
4. Create an annotated `vX.Y.Z` tag on the verified merge commit.
5. Push the tag and verify its `quality` run. The tag is the authoritative
   package version through hatch-vcs.
6. Force-refresh the local editable installation when checking a newly created
   tag:

   ```bash
   uv sync --locked --reinstall-package python-media-organizer
   uv run --locked pymo --version
   ```

The package is not currently published to PyPI. A release means a verified Git
tag plus locally buildable source and wheel artifacts.
