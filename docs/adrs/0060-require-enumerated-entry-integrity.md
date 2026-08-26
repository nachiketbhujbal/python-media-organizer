# ADR 0060: Require integrity for every enumerated entry

- Status: Accepted
- Date: 2026-08-22

## Context

ADR 0059 made directory traversal and immediate listing fail closed, but a
damaged filesystem can expose a subtler inconsistency: enumeration returns a
filename while metadata lookup for the same name returns `ENOENT` or another
error. Python's `Path.is_file()`, `is_dir()`, and `is_symlink()` predicates
normally convert those errors to `False`. A planner can therefore omit the
entry while incorrectly treating the directory walk as complete.

An entry can also change between enumeration and inspection. If a name listed
as a non-directory becomes a directory, a walk may never visit its contents;
if a listed directory becomes another type, the plan was derived from a stale
namespace partition.

## Decision

Every name returned within a mutation, undo, duplicate-analysis, or organizer-
verification ownership boundary must pass explicit `lstat` inspection. Failure
to inspect any enumerated name raises the shared path-private discovery error.
Entries returned in the directory portion of a recursive walk must still be a
directory or symbolic link; entries returned in the non-directory portion must
not have become a directory.

Organization, renaming, action-log snapshots, and both exact duplicate finders
use this classification. Symbolic links and non-regular filesystem objects keep
their existing conservative handling. Configured ignored directory contents
remain outside traversal, but the ignored entry point itself must be
inspectable before it can define that boundary.

Report-only scan and validation retain their evidence behavior: an unresolvable
entry increments an unreadable finding and processing continues over readable
neighbors. They do not convert the failure into ignore policy.

## Consequences

A ghost directory entry now prevents mutation planning, undo, and duplicate
analysis from creating state or claiming a complete view. Transient deletion
during discovery also requires a rerun instead of being silently omitted.

The additional metadata lookup per entry increases discovery work slightly.
That cost is required for preservation correctness and does not decode or hash
media content.
