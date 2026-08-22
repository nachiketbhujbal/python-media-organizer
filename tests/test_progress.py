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
    meter = ProgressMeter(20, 20 * 1024 * 1024, 10, clock=clock)

    clock.now = 5
    assert meter.advance("processed", byte_count=1024 * 1024) is None
    clock.now = 10
    message = meter.advance("processed", byte_count=1024 * 1024)

    assert message is not None
    assert "processed 2/20 (10.0%)" in message
    assert "2.0 MiB/20.0 MiB" in message
    assert "204.8 KiB/s" in message
    assert "ETA 1m 30s" in message


def test_heartbeat_does_not_claim_current_item_is_complete() -> None:
    clock = Clock()
    meter = ProgressMeter(2, 2_000, 10, clock=clock)
    clock.now = 10

    message = meter.heartbeat("fingerprinted", 1)

    assert message is not None
    assert "fingerprinted 0/2" in message
    assert "item 1/2 still running" in message


def test_progress_uses_ten_stable_count_milestones() -> None:
    clock = Clock()
    meter = ProgressMeter(100, None, 60, clock=clock)
    messages = [meter.advance("processed") for _ in range(100)]

    reported = [message for message in messages if message is not None]

    assert len(reported) == 10
    for step, message in enumerate(reported, start=1):
        assert f"processed {step * 10}/100 ({step * 10:.1f}%)" in message


def test_heartbeat_prevents_an_immediate_nonmilestone_completion_row() -> None:
    clock = Clock()
    meter = ProgressMeter(100, None, 10, clock=clock)
    clock.now = 10
    assert meter.heartbeat("processed", 1) is not None
    clock.now = 11

    assert meter.advance("processed") is None
