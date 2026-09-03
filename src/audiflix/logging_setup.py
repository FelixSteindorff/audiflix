"""Central logging configuration with rotating log files.

Audiflix writes diagnostics to ``<config dir>/logs/audiflix.log`` (rotating,
five files of one megabyte each). The log is the primary tool for debugging
player, network and background-thread problems that a screen-reader user cannot
see on screen.

Two rules apply everywhere:

* **Never log secrets.** :class:`RedactingFilter` strips ``token=`` query
  parameters and ``Authorization`` header values from every record, so a stray
  URL in an exception message cannot leak an auth token into the log file.
* **Never swallow an exception silently.** Use :func:`log_exception` (or
  ``logger.exception``) instead of ``except Exception: pass``.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
from pathlib import Path
from typing import Any

LOG_FILENAME = "audiflix.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5

_LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(threadName)s] %(name)s: %(message)s"

# token=<value> in URLs/query strings, and bearer/refresh tokens in headers.
_TOKEN_PATTERNS = [
    re.compile(r"((?:token|access_token|refresh_token|apikey|api_key)=)[^&\s\"']+", re.I),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/-]+=*", re.I),
    re.compile(r"((?:x-refresh-token|authorization)['\"]?\s*[:=]\s*['\"]?)[^\s,'\"}]+", re.I),
]

_configured = False


def redact(text: str) -> str:
    """Return ``text`` with any recognisable auth token replaced."""
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(r"\1<redacted>", text)
    return text


class RedactingFilter(logging.Filter):
    """Removes auth tokens from messages and arguments before they are written."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = _redact_args(record.args)
        return True


def _redact_args(args: Any) -> Any:
    if isinstance(args, dict):
        return {key: redact(value) if isinstance(value, str) else value for key, value in args.items()}
    if isinstance(args, tuple):
        return tuple(redact(a) if isinstance(a, str) else a for a in args)
    return args


def log_dir() -> Path:
    """Directory for log files (created on demand)."""
    from audiflix.config import config_dir

    path = config_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(level: int | str | None = None, *, console: bool | None = None) -> Path | None:
    """Configure the root logger once. Returns the log file path (or ``None``).

    ``level`` defaults to the ``AUDIFLIX_LOG_LEVEL`` environment variable, then
    to ``INFO``. A console handler is added when running from a terminal (the
    packaged GUI executable has no console).
    """
    global _configured
    if _configured:
        return _current_log_path()

    if level is None:
        level = os.environ.get("AUDIFLIX_LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    redactor = RedactingFilter()
    formatter = logging.Formatter(_LOG_FORMAT)

    path: Path | None = None
    try:
        path = log_dir() / LOG_FILENAME
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redactor)
        root.addHandler(file_handler)
    except OSError as exc:  # read-only config dir, permissions, ...
        path = None
        # Logging is not available yet, so stderr is the only channel left.
        print(f"Audiflix: could not open log file: {exc}", file=sys.stderr)  # noqa: T201

    if console is None:
        console = sys.stderr is not None and sys.stderr.isatty()
    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(redactor)
        root.addHandler(stream_handler)

    _configured = True
    logging.getLogger(__name__).debug("Logging initialised (level=%s)", logging.getLevelName(level))
    return path


def _current_log_path() -> Path | None:
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            return Path(handler.baseFilename)
    return None


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper so modules do not import :mod:`logging` directly."""
    return logging.getLogger(name)


def log_exception(logger: logging.Logger, message: str, *args: Any) -> None:
    """Log a caught exception with traceback.

    Use this in ``except`` blocks that intentionally continue, so failures stay
    diagnosable instead of disappearing into ``pass``.
    """
    logger.exception(message, *args)
