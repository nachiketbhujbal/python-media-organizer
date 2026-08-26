# ADR 0053: Report cache activity as completed facts

- Status: Accepted
- Date: 2026-08-22

## Context

The exact-video finder reported cache “hits” and “misses” followed by the
generic promise that incremental updates were enabled. A missing candidate
record means a fingerprint is required, but it does not prove that decoding
will succeed or that a new record will be durably published. The output did not
say how many writes actually completed.

The same sentence described `--no-cache` as disabled while still presenting
hit and miss counts. Although the implementation skipped both the read and
write paths, that wording could imply a lookup had occurred. Calling all decode
work “uncached” was similarly unclear when caching had been deliberately
disabled.

## Decision

For cache-enabled runs, report candidate-relevant reusable records and required
fingerprints immediately after lookup. After fingerprinting, report new records
that were durably persisted and required fingerprints that were not persisted.
Increment the persisted count only after the atomic cache update returns
successfully.

For `--no-cache`, state explicitly that no records are read or written and how
many fingerprints are required. Do not emit cache lookup or cache update lines
for that run. Describe the decode workload as candidate content rather than as
“uncached” content.

## Consequences

The report separates inputs known at lookup time from durable outcomes known
only after processing. A failed or changed candidate can no longer be mistaken
for a newly cached record, and a zero-required warm run clearly reports zero
new records.

This changes human wording only. The cache remains a disposable,
collection-local acceleration artifact; previews still persist successful
fingerprints by default, `--no-cache` still prevents every cache read and
write, and exact duplicate semantics are unchanged.
