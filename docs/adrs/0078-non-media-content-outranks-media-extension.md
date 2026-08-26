# ADR 0078: A meaningful non-media content signature outranks a media extension

- Status: Accepted
- Date: 2026-08-25

## Context

Validation discovery classified a file from its content signature and then fell
back to the filename extension when that signature was not itself a media type.
The fallback ignored a positive non-media verdict, so a file whose content was
identified as text was still promoted to the media kind implied by its
extension, probed or decoded as media, and reported as damaged.

The practical case is an extension shared between a media container and a source
format: a transport-stream extension is also the conventional TypeScript source
extension. A healthy source file in a collection therefore produced a
decode-failure finding at error severity and a failing exit status for an
otherwise healthy collection. The same defect applied to any configured media
extension, so a text file named with a common video extension behaved
identically.

This contradicts the project's stated posture that findings are honest, that
unsupported or unrecognized content is never called corrupt, and that exit
status reflects real collection health.

The shared classifier already implemented the correct precedence and returned a
non-media verdict for these files. Only validation discovery overrode it;
organization consumes the classifier directly and was never affected.

## Decision

A meaningful non-media content signature outranks a media extension. Validation
discovery does not promote a file to a media kind on the strength of its
extension when the content signature has positively identified non-media
content.

Such a file is neither validated as media nor silently dropped. It is reported
as a discovery-level `extension_content_mismatch` finding at **warning**
severity, it is counted in the report as a non-media file, and no decoder or
native media tool is invoked for it. Warning severity does not change exit
status, so a collection whose only irregularity is a misnamed non-media file
exits successfully.

An empty stream is not a non-media content signature. It carries no signature at
all, so the extension remains the only available evidence and the file is still
validated as media, where an empty media file remains an error. The signature
utility spells the empty result differently when it reads a pathname than when
it reads standard input, and descriptor-pinned callers always use the latter, so
both spellings are packaged as generic types.

Where the content-signature utility is unavailable, there is no meaningful
signature and this precedence rule does not apply. Classification falls back to
the extension and already reports a distinct warning that it did so.

The filename MIME guess that remains in that situation is not a content
signature. It is derived from the same name the rule exists to check, and
platform MIME databases disagree about which media extensions they recognize.
Configured image and video extensions are therefore taken before any such guess
is interpreted, whether the utility is missing entirely or merely failed for one
file. Otherwise a machine whose database does not recognize a configured
extension would report genuine media as a naming mismatch without reading a byte
of it.

## Consequences

A healthy non-media file bearing a media extension no longer fails a collection.
The naming problem remains visible as a warning, so the information is not lost
and the user can still act on it.

Validation counts change for such files. They are no longer counted as pictures
or videos and are counted as other files instead, because that is what they are.
The report shape is unchanged, so the schema version is unchanged; only counts
that were previously wrong become right.

Damage detection is unaffected for damaged media that retains a media or generic
content signature. A file truncated or corrupted past its payload but still
carrying recognizable container magic is still validated and still reported as
an error. Only content positively identified as something else is exempted,
which is why synthetic fixtures standing in for damage must be damaged media
rather than text wearing a media extension.

That claim is deliberately narrow, and the limit it leaves is worth stating. If
damage destroys a file's header and its surviving bytes positively identify as
text or as some other non-media type, the file is observationally identical to a
non-media file that was misnamed on purpose. No local signature can separate the
two, so this decision reports it as a warning rather than a decode error. That
is an accepted trade rather than an oversight: the alternative is to keep
reporting healthy misnamed files as damaged media, which is the defect this
decision exists to correct. Damage severe enough to reach that state has already
destroyed the evidence needed to classify the file, and a warning naming the
disagreement is more truthful than an error asserting a decode that was never
attempted.

Container-family truthfulness, which reports a video whose container disagrees
with its extension, depends on this correction landing first. Until a file that
is not media at all stops being reported as invalid media, a finding about which
container a real video uses cannot be interpreted reliably.

The rule is only as good as the local content signature. It deliberately does
not attempt to identify non-media content without one, because guessing from the
extension is what produced the defect.
