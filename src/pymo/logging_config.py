"""Privacy-conscious logging for the pymo command-line interface."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO


def _logger() -> logging.Logger:
    """Return logging's process-wide named singleton without mirroring it."""
    value = logging.getLogger("pymo")
    value.propagate = False
    return value


class _MaximumLevel(logging.Filter):
    def __init__(self, maximum: int) -> None:
        super().__init__()
        self.maximum = maximum

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.maximum


class _IsoLineFormatter(logging.Formatter):
    """Prefix every physical line, including lines inside one log message."""

    def __init__(self, *, include_context: bool) -> None:
        super().__init__()
        self.include_context = include_context

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).astimezone().isoformat(
            timespec="seconds"
        )
        context = (
            f"{record.levelname} {record.name} " if self.include_context else ""
        )
        message = record.getMessage()
        lines = message.splitlines() or [""]
        return "\n".join(f"{timestamp} {context}{line}" for line in lines)


def configure_logging(
    *,
    verbose: bool = False,
    quiet: bool = False,
    log_file: Path | None = None,
    timestamps: bool = False,
) -> None:
    """Configure console logging and an optional explicitly requested file."""
    logger = _logger()
    logger.handlers.clear()
    level = logging.WARNING if quiet else logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    stdout = logging.StreamHandler(sys.stdout)
    stdout.setLevel(level)
    stdout.addFilter(_MaximumLevel(logging.INFO))
    console_formatter: logging.Formatter = (
        _IsoLineFormatter(include_context=False)
        if timestamps
        else logging.Formatter("%(message)s")
    )
    stdout.setFormatter(console_formatter)
    logger.addHandler(stdout)

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setLevel(logging.WARNING)
    stderr.setFormatter(console_formatter)
    logger.addHandler(stderr)

    if log_file is not None:
        destination = log_file.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(destination, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        file_handler.setFormatter(_IsoLineFormatter(include_context=True))
        logger.addHandler(file_handler)


def ensure_logging() -> None:
    logger = _logger()
    if not logger.handlers:
        configure_logging()


def emit(
    *values: object,
    sep: str = " ",
    end: str = "\n",
    file: TextIO | None = None,
    flush: bool = False,
) -> None:
    """Route existing human-facing output through the logging system.

    The signature intentionally mirrors ``print`` so existing, carefully
    tested command output can migrate without changing its text.
    """
    del flush
    ensure_logging()
    logger = _logger()
    message = sep.join(str(value) for value in values)
    if end and end != "\n":
        message += end
    if file is sys.stderr:
        logger.error(message)
    else:
        logger.info(message)
