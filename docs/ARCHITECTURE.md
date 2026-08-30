# Package architecture

The `pymo` package is organized around product ownership and safety boundaries,
not file size alone. Dependencies should flow from command coordination into
domain subsystems and then into shared safety infrastructure. Lower layers must
not import a command entry point.

## Boundaries

```text
CLI dispatch
  -> command coordinators
       -> duplicates/, cache/, and migration/ subsystems
            -> shared safety and policy modules
```

- `cli.py` and `__main__.py` select a command and own no media policy.
- `organize.py`, `rename.py`, `correct_extensions.py`, `scan.py`, and
  `validate.py` are user-facing command coordinators. `verify_migration.py`
  coordinates the directional preservation report. Their staged functions
  remain directly testable.
- `duplicates/` owns exact duplicate policy. Images and videos remain separate
  because their definitions of equivalent content and their native dependencies
  differ; `common.py` contains only shared layout and move-plan policy.
- `cache/` owns disposable derived state. `service.py` is the schema and safe
  SQLite publication boundary, `hashes.py` owns whole-file observation and
  descriptor-hash policy, `images.py` owns displayed-pixel evidence,
  `paths.py` owns writable-target selection, `probes.py` owns normalized video
  structure evidence, `validation.py` owns health evidence,
  `status.py` owns zero-write reporting, `warm.py` owns reusable media
  population, `refresh.py` owns forced selected recomputation, and `cli.py`
  dispatches nested cache operations. The
  package `__init__.py` exposes the supported storage facade used by producers.
- `migration/` owns path-independent preservation evidence. `inventory.py`
  owns fresh stable byte inventory, `coverage.py` owns directional identity and
  multiplicity accounting, `images.py` owns exact displayed-image coverage,
  `videos.py` owns strict decoded-playback coverage, and `report.py` owns the
  root-free public schema. `verdict.py` owns final layered accounting and
  disposition policy, while `simulation.py` owns the explicit counterfactual
  destination view and separate duplicate-review inventory. Final namespace
  stability remains in `inventory.py`; command dispatch and disposable cache
  ownership stay outside this domain.
- `action_log.py` owns the authoritative append-only mutation journal. It is
  deliberately outside `cache/` because journal evidence is portable and
  authoritative while cache state is derived and disposable.
- `classification.py`, `collection.py`, `config.py`, `discovery.py`,
  `file_safety.py`, `extension_truth.py`, `image_content.py`, `video_content.py`,
  `logging_config.py`, `progress.py`, and `video.py` are shared foundations.
  They may not depend on a specific command or duplicate-media implementation.
  `image_content.py` owns the versioned descriptor-to-displayed-pixel
  normalization shared by duplicate and migration domains, but neither
  domain's discovery, cache, report, or mutation policy.
  `video_content.py` owns the equivalent descriptor-based probe, native-tool,
  and exact-playback normalization shared by those domains under the same
  ownership restriction.
  `extension_truth.py` owns fresh Pillow format and confidence-gated ffprobe
  container evidence; the correction command retains discovery, packaged
  policy selection, collision, reporting, and mutation ownership.

## Review rules

A new subpackage is justified when several modules share one lifecycle,
invariant set, or public facade. A large module is not split merely to reduce a
line count: a split must improve ownership, dependency direction, independent
testing, or replacement safety without scattering one invariant across files.

Command modules remain at the package root while each maps directly to a public
CLI verb. `action_log.py` remains one module while its parser, lifecycle model,
locking, and execution rules change together. The existing `duplicates/`
boundary remains intact rather than merging image and video policy. These
decisions should be revisited when a second implementation or independently
owned lifecycle appears, not during unrelated feature work.

Internal modules may change between pre-1.0 releases. User-facing CLI contracts,
on-disk schemas, journal semantics, safety guarantees, and the curated cache
facade require an explicit compatibility decision before they change.
