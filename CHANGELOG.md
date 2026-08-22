# Changelog

All notable changes to `python-media-organizer` will be recorded here.

## 0.1.1 - 2026-08-21

- Adopt uv for reproducible environments, dependency locking, tests, and
  builds.
- Replace the static Setuptools version with Hatchling and Git-tag-derived
  hatch-vcs versioning.
- Read the runtime version from installed package metadata and test that it
  matches the distribution.
- Document the standards-compatible installation, development, build, and
  release workflow.

## 0.1.0 - 2026-08-21

- Package the organizer, deterministic renamer, and exact duplicate finders
  behind the `pymo` command.
- Preserve dry-run-first, collision-safe, verified, append-only reversible
  collection operations.
- Add strict image and video folder ownership under `pics`, `vids`, and `dups`.
- Add conservative FFmpeg-based exact decoded-playback video matching and a
  disposable collection-local fingerprint cache.
- Route output through privacy-conscious standard-library logging.
- Add synthetic unit, workflow, and real FFmpeg integration tests.
- Name each portable action journal `{collection-name}-actions-log.jsonl` and
  migrate the legacy fixed filename on the next applied journal write.
