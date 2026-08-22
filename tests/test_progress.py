from __future__ import annotations

from pymo.progress import ProgressMeter, format_bytes, format_duration


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_duration_and_byte_formatting() -> None:
    assert format_duration(0.25) == "0.2s"
    assert format_duration(65) == "1m 5s"
    assert format_duration(3_661) == "1h 1m 1s"
    assert format_bytes(512) == "512 B"
    assert format_bytes(1_572_864) == "1.5 MiB"


def test_progress_reports_observed_rate_and_eta() -> None:
    clock = Clock()
    meter = ProgressMeter(4, 4 * 1024 * 1024, 10, clock=clock)

    clock.now = 5
    assert meter.advance("processed", byte_count=1024 * 1024) is None
    clock.now = 10
    message = meter.advance("processed", byte_count=1024 * 1024)

    assert message is not None
    assert "processed 2/4 (50.0%)" in message
    assert "2.0 MiB/4.0 MiB" in message
    assert "204.8 KiB/s" in message
    assert "ETA 10s" in message


def test_heartbeat_does_not_claim_current_item_is_complete() -> None:
    clock = Clock()
    meter = ProgressMeter(2, 2_000, 10, clock=clock)
    clock.now = 10

    message = meter.heartbeat("fingerprinted", 1)

    assert message is not None
    assert "fingerprinted 0/2" in message
    assert "item 1/2 still running" in message
