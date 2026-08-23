"""Shared typed facts derived from local video structure."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProbeInfo:
    """Normalized structural facts used by exact-playback analysis."""

    display_width: int
    display_height: int
    duration_us: int
    video_start_us: int
    audio_start_us: int | None
    audio_sample_rate: int | None
    audio_channels: int | None
    audio_layout: str | None
    has_audio: bool

    @property
    def candidate_key(self) -> tuple[object, ...]:
        # This intentionally omits codecs, containers, and source pixel format.
        # Files in different basic buckets cannot produce the same canonical
        # playback, while files in the same bucket still require full decoding.
        return (
            self.display_width,
            self.display_height,
            self.has_audio,
            self.audio_sample_rate,
            self.audio_channels,
            self.audio_layout,
        )
