"""Deterministic, privacy-safe elapsed-time and work-rate reporting."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


def format_duration(seconds: float) -> str:
    """Render a non-negative duration compactly without false precision."""
    seconds = max(0.0, seconds)
    if seconds < 10:
        return f"{seconds:.1f}s"
    total_seconds = int(round(seconds))
    days, remainder = divmod(total_seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, remaining_seconds = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if remaining_seconds or not parts:
        parts.append(f"{remaining_seconds}s")
    return " ".join(parts)


def format_bytes(size: float) -> str:
    value = max(0.0, float(size))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


@dataclass
class ProgressMeter:
    """Track bounded work and produce periodic aggregate status messages."""

    total_items: int
    total_bytes: int | None
    interval_seconds: int
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    completed_items: int = 0
    completed_bytes: int = 0
    _started_at: float = field(init=False, repr=False)
    _last_reported_at: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        now = self.clock()
        self._started_at = now
        self._last_reported_at = now

    @property
    def elapsed(self) -> float:
        return max(0.0, self.clock() - self._started_at)

    def _is_due(self, now: float, force: bool) -> bool:
        return force or now - self._last_reported_at >= self.interval_seconds

    def _eta_seconds(self, elapsed: float) -> float | None:
        if self.total_bytes and self.completed_bytes:
            remaining = max(0, self.total_bytes - self.completed_bytes)
            return elapsed * remaining / self.completed_bytes
        if self.total_items and self.completed_items:
            remaining = max(0, self.total_items - self.completed_items)
            return elapsed * remaining / self.completed_items
        return None

    def _status(self, label: str, now: float) -> str:
        elapsed = max(0.0, now - self._started_at)
        details = [f"{label} {self.completed_items}/{self.total_items}"]
        if self.total_items:
            details[-1] += f" ({self.completed_items / self.total_items * 100:.1f}%)"
        if self.total_bytes is not None:
            details.append(
                f"{format_bytes(self.completed_bytes)}/{format_bytes(self.total_bytes)}"
            )
        details.append(f"elapsed {format_duration(elapsed)}")
        if elapsed > 0 and self.completed_bytes:
            details.append(f"{format_bytes(self.completed_bytes / elapsed)}/s")
        elif elapsed > 0 and self.completed_items:
            details.append(f"{self.completed_items / elapsed:.1f} file(s)/s")
        eta = self._eta_seconds(elapsed)
        if eta is not None and self.completed_items < self.total_items:
            details.append(f"ETA {format_duration(eta)}")
        return "; ".join(details)

    def advance(
        self, label: str, *, byte_count: int = 0, force: bool = False
    ) -> str | None:
        self.completed_items += 1
        self.completed_bytes += max(0, byte_count)
        now = self.clock()
        if not self._is_due(now, force or self.completed_items == self.total_items):
            return None
        self._last_reported_at = now
        return self._status(label, now)

    def heartbeat(self, label: str, active_item: int) -> str | None:
        """Report that one long item is active without claiming completion."""
        now = self.clock()
        if not self._is_due(now, False):
            return None
        self._last_reported_at = now
        status = self._status(label, now)
        return f"{status}; item {active_item}/{self.total_items} still running"
