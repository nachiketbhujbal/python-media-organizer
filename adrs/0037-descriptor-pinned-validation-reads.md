# ADR 0037: Pin validation reads to no-follow descriptors

- Status: Accepted
- Date: 2026-08-22

## Context

Checking a pathname immediately before and after decoding detects replacement,
but it does not stop a pathname from being replaced by a symbolic link between
the check and the decoder's open call. A decoder could briefly read a file
outside the collection even though the eventual report rejects the result.

## Decision

Open each validation candidate relative to directory descriptors rooted at the
resolved collection. Refuse symbolic links at every collection path component
and at the file, require the opened regular-file state to equal discovery, and
keep that descriptor pinned through classification and decoding. Pillow reads
duplicated Python file handles; `file`, ffprobe, and FFmpeg receive only an
inherited `/dev/fd` reference. Recheck both the descriptor and pathname before
closing.

## Consequences

A concurrent rename or symbolic-link swap cannot redirect validation content
reads. The run reports the candidate as changed and asks for a retry. This uses
the project's existing POSIX platform boundary and intentionally treats the
resolved collection root as the trusted traversal anchor.
