# Changelog

All notable changes to `python-media-organizer` will be recorded here.

## 0.1.3 - 2026-08-22

- Move media classification lists, rename noise tokens, image-inspection
  extensions, and the default video decode timeout into packaged TOML policy.
- Add frozen typed configuration sections with strict validation, additive
  custom arrays, and command-line timeout precedence.
- Centralize fixed collection paths in an immutable `CollectionLayout` rather
  than exposing structural names as scattered configuration or globals.
- Replace tool and action strings with stable enums, remove mutable command and
  logger globals, and retain only justified on-disk version constants.
- Preserve existing organization, rename, exact duplicate, action-log, undo,
  privacy, and dry-run behavior with expanded synthetic coverage.

## 0.1.2 - 2026-08-21

- Add validated, packaged TOML defaults shared by organization, renaming, and
  both exact duplicate finders.
- Ignore common operating-system metadata, version-control directories, pymo
  configuration, and disposable cache artifacts without moving, renaming,
  fingerprinting, deleting, or action-logging them.
- Support collection-root `.pymo.toml` extensions and alternate `--config`
  files while keeping built-in safety rules active.
- Allow organizer verification to preserve source trees that contain only
  ignored metadata, and reject invalid configuration before mutation.
- Expand synthetic regression coverage for shared ignore behavior, config
  parsing, CLI forwarding, package data, and undo compatibility.

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
