"""Privacy-conscious logging for the pymo command-line interface."""

from __future__ import annotations

import logging
import os
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO, cast


class LoggingConfigurationError(RuntimeError):
    """The requested diagnostic logging surface is unsafe or invalid."""


def log_level_choices() -> tuple[str, ...]:
    """Return the conventional levels accepted by the public CLI."""
    return ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _level_number(value: str) -> int:
    normalized = value.upper()
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    try:
        return levels[normalized]
    except KeyError as error:
        raise LoggingConfigurationError("unsupported logging level") from error


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
        timestamp = (
            datetime.fromtimestamp(record.created)
            .astimezone()
            .isoformat(timespec="seconds")
        )
        context = f"{record.levelname} {record.name} " if self.include_context else ""
        message = record.getMessage()
        lines = message.splitlines() or [""]
        return "\n".join(f"{timestamp} {context}{line}" for line in lines)


class _PrivateAppendHandler(logging.StreamHandler[TextIO]):
    """Append to one explicit regular file without following its leaf."""

    def __init__(self, destination: Path) -> None:
        try:
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            flags = (
                os.O_WRONLY
                | os.O_APPEND
                | os.O_CREAT
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0)
            )
            descriptor = os.open(destination, flags, 0o600)
        except OSError as error:
            raise LoggingConfigurationError(
                "explicit diagnostic log could not be opened safely"
            ) from error
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise LoggingConfigurationError(
                    "explicit diagnostic log is not a safe regular file"
                )
            stream = os.fdopen(descriptor, "a", encoding="utf-8", newline="")
        except BaseException:
            os.close(descriptor)
            raise
        super().__init__(cast(TextIO, stream))

    def close(self) -> None:
        try:
            if self.stream is not None and not self.stream.closed:
                self.flush()
                self.stream.close()
        finally:
            super().close()


def configure_logging(
    *,
    verbose: bool = False,
    quiet: bool = False,
    log_file: Path | None = None,
    timestamps: bool = False,
    console_level: str | None = None,
    file_level: str | None = None,
) -> None:
    """Configure console logging and an optional explicitly requested file."""
    if verbose and quiet:
        raise LoggingConfigurationError("verbose and quiet logging conflict")
    if console_level is not None and (verbose or quiet):
        raise LoggingConfigurationError(
            "explicit console logging level conflicts with verbose or quiet"
        )
    if file_level is not None and log_file is None:
        raise LoggingConfigurationError(
            "file logging level requires an explicit diagnostic log"
        )

    logger = _logger()
    for handler in logger.handlers:
        if isinstance(handler, _PrivateAppendHandler):
            handler.close()
    logger.handlers.clear()
    console_threshold = (
        _level_number(console_level)
        if console_level is not None
        else logging.WARNING if quiet else logging.DEBUG if verbose else logging.INFO
    )
    file_threshold = (
        _level_number(file_level)
        if file_level is not None
        else logging.DEBUG if verbose else logging.INFO
    )
    logger.setLevel(
        min(console_threshold, file_threshold)
        if log_file is not None
        else console_threshold
    )

    stdout = logging.StreamHandler(sys.stdout)
    stdout.setLevel(console_threshold)
    stdout.addFilter(_MaximumLevel(logging.INFO))
    console_formatter: logging.Formatter = (
        _IsoLineFormatter(include_context=False)
        if timestamps
        else logging.Formatter("%(message)s")
    )
    stdout.setFormatter(console_formatter)
    logger.addHandler(stdout)

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setLevel(max(console_threshold, logging.WARNING))
    stderr.setFormatter(console_formatter)
    logger.addHandler(stderr)

    if log_file is not None:
        try:
            destination = log_file.expanduser().absolute()
        except (OSError, RuntimeError) as error:
            raise LoggingConfigurationError(
                "explicit diagnostic log path could not be resolved safely"
            ) from error
        file_handler = _PrivateAppendHandler(destination)
        file_handler.setLevel(file_threshold)
        file_handler.setFormatter(_IsoLineFormatter(include_context=True))
        logger.addHandler(file_handler)


def ensure_logging() -> None:
    logger = _logger()
    if not logger.handlers or any(
        isinstance(handler, logging.StreamHandler)
        and getattr(handler.stream, "closed", False)
        for handler in logger.handlers
    ):
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
