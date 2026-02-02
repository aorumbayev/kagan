"""Debug logging with in-app viewer support.

Captures both Textual log() calls and Python logging module logs
into a ring buffer that can be viewed via F12.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any


class LogSource(Enum):
    """Source of the log entry."""

    TEXTUAL = "TEXTUAL"
    LOGGING = "LOGGING"


@dataclass(slots=True)
class LogEntry:
    """A captured log entry."""

    group: str  # Level name (DEBUG, INFO, WARNING, ERROR, etc.)
    message: str
    timestamp: float
    source: LogSource


# Global log buffer (ring buffer)
MAX_LOG_LINES = 2000
log_buffer: deque[LogEntry] = deque(maxlen=MAX_LOG_LINES)

# Track generation to detect buffer clears
_buffer_generation: int = 0


class KaganLogger:
    """Simple logger that captures logs for in-app viewing and passes to Textual."""

    def __call__(self, *args: object, **kwargs: Any) -> None:
        """Log at INFO level (default)."""
        self.info(*args, **kwargs)

    def _log(self, level: str, *args: object, **kwargs: Any) -> None:
        """Internal logging method."""
        # Build the log message
        output = " ".join(str(arg) for arg in args)
        if kwargs:
            key_values = " ".join(f"{key}={value!r}" for key, value in kwargs.items())
            output = f"{output} {key_values}" if output else key_values

        # Store in buffer
        log_buffer.append(
            LogEntry(
                group=level,
                message=output,
                timestamp=time.time(),
                source=LogSource.TEXTUAL,
            )
        )

        # Also pass to Textual's devtools logger
        try:
            from textual import log as textual_log

            textual_log(output)
        except Exception:
            pass

    def debug(self, *args: object, **kwargs: Any) -> None:
        """Log at DEBUG level."""
        self._log("DEBUG", *args, **kwargs)

    def info(self, *args: object, **kwargs: Any) -> None:
        """Log at INFO level."""
        self._log("INFO", *args, **kwargs)

    def warning(self, *args: object, **kwargs: Any) -> None:
        """Log at WARNING level."""
        self._log("WARNING", *args, **kwargs)

    def error(self, *args: object, **kwargs: Any) -> None:
        """Log at ERROR level."""
        self._log("ERROR", *args, **kwargs)


class DebugLogHandler(logging.Handler):
    """Logging handler that captures logs to the debug buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            log_buffer.append(
                LogEntry(
                    group=record.levelname,
                    message=msg,
                    timestamp=record.created,
                    source=LogSource.LOGGING,
                )
            )
        except Exception:
            self.handleError(record)


_debug_logging_initialized: bool = False


def setup_debug_logging() -> None:
    """Set up the debug logging handler for Python's logging module.

    This is idempotent - calling it multiple times has no effect after the first call.
    """
    global _debug_logging_initialized

    if _debug_logging_initialized:
        return

    handler = DebugLogHandler()
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))

    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    _debug_logging_initialized = True

    # Add a startup log entry
    log.info("Debug logging initialized - press F12 to view logs")


def clear_log_buffer() -> None:
    """Clear the log buffer."""
    global _buffer_generation
    log_buffer.clear()
    _buffer_generation += 1


def get_buffer_generation() -> int:
    """Get the current buffer generation (incremented on clear)."""
    return _buffer_generation


# Create the global logger instance (replaces `from textual import log`)
log = KaganLogger()
