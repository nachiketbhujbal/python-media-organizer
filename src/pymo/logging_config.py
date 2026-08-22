"""Privacy-conscious logging for the pymo command-line interface."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TextIO


LOGGER_NAME = "pymo"
logger = logging.getLogger(LOGGER_NAME)
logger.propagate = False


class _MaximumLevel(logging.Filter):
    def __init__(self, maximum: int) -> None:
        super().__init__()
        self.maximum = maximum

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.maximum


def configure_logging(
    *, verbose: bool = False, quiet: bool = False, log_file: Path | None = None
) -> None:
    """Configure console logging and an optional explicitly requested file."""
    logger.handlers.clear()
    level = logging.WARNING if quiet else logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    stdout = logging.StreamHandler(sys.stdout)
    stdout.setLevel(level)
    stdout.addFilter(_MaximumLevel(logging.INFO))
    stdout.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(stdout)

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setLevel(logging.WARNING)
    stderr.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(stderr)

    if log_file is not None:
        destination = log_file.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(destination, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        logger.addHandler(file_handler)


def ensure_logging() -> None:
    if not logger.handlers:
        configure_logging()


def emit(
    *values: object,
    sep: str = " ",
    end: str = "\n",
    file: TextIO | None = None,
    flush: bool = False,
) -> None:
    """Route legacy human-facing output through the logging system.

    The signature intentionally mirrors ``print`` so existing, carefully
    tested command output can migrate without changing its text.
    """
    del flush
    ensure_logging()
    message = sep.join(str(value) for value in values)
    if end and end != "\n":
        message += end
    if file is sys.stderr:
        logger.error(message)
    else:
        logger.info(message)

