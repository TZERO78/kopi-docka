################################################################################
# KOPI-DOCKA
#
# @file:        logging.py
# @module:      kopi_docka.logging
# @description: Central logging setup with structured journal and colorful console output.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - StructuredFormatter switches between journald key/value and ANSI colors
# - LogManager.setup wires console, journald, and rotating file handlers
# - log_manager.operation context measures durations and error counts
################################################################################

"""
Logging module for Kopi-Docka.

This module provides centralized logging configuration with:
- Structured logging for systemd/journald
- File and console output
- Log rotation
- Context managers for operations
- Performance metrics
"""

import logging
import logging.handlers
import sys
import time
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Optional: Echte journald structured logs
try:
    from systemd.journal import JournalHandler

    _HAS_JOURNAL = True
except ImportError:
    _HAS_JOURNAL = False


# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for pretty terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"


class StructuredFormatter(logging.Formatter):
    """
    Formatter that outputs structured logs for systemd/journald.

    In systemd environment: JSON-like key=value pairs
    In terminal: Colored, human-readable format
    """

    # Map log levels to colors
    LEVEL_COLORS = {
        "DEBUG": Colors.GRAY,
        "INFO": Colors.GREEN,
        "WARNING": Colors.YELLOW,
        "ERROR": Colors.RED,
        "CRITICAL": Colors.RED + Colors.BOLD,
    }

    # Map log levels to symbols
    LEVEL_SYMBOLS = {
        "DEBUG": "🔍",
        "INFO": "✓",
        "WARNING": "⚠",
        "ERROR": "✗",
        "CRITICAL": "🔥",
    }

    def __init__(self, use_colors: bool = None, use_systemd: bool = None):
        """
        Initialize formatter.

        Args:
            use_colors: Force color output (auto-detect if None)
            use_systemd: Force systemd format (auto-detect if None)
        """
        super().__init__()

        # Auto-detect if running under systemd
        if use_systemd is None:
            self.use_systemd = self._is_systemd()
        else:
            self.use_systemd = use_systemd

        # Auto-detect if terminal supports colors
        if use_colors is None:
            self.use_colors = self._supports_color() and not self.use_systemd
        else:
            self.use_colors = use_colors

    def _is_systemd(self) -> bool:
        """Check if running under systemd."""
        # systemd setzt JOURNAL_STREAM
        return (not sys.stderr.isatty()) and ("JOURNAL_STREAM" in os.environ)

    def _supports_color(self) -> bool:
        """Check if terminal supports colors."""
        # Wir loggen auf STDERR → dort prüfen
        if not hasattr(sys.stderr, "isatty"):
            return False
        if not sys.stderr.isatty():
            return False
        if os.environ.get("NO_COLOR"):
            return False
        if os.environ.get("TERM") == "dumb":
            return False
        return True

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record.

        Args:
            record: Log record to format

        Returns:
            Formatted log string
        """
        if self.use_systemd:
            return self._format_systemd(record)
        elif self.use_colors:
            return self._format_colored(record)
        else:
            return self._format_plain(record)

    def _format_systemd(self, record: logging.LogRecord) -> str:
        """Format for systemd/journald with structured fields."""
        # Build structured fields
        fields = []

        # Standard fields
        fields.append(f"PRIORITY={self._syslog_priority(record.levelno)}")
        fields.append(f"LEVEL={record.levelname}")
        fields.append(f"MODULE={record.module}")
        fields.append(f"FUNCTION={record.funcName}")

        # Add extra fields from record
        if hasattr(record, "unit_name"):
            fields.append(f"UNIT={record.unit_name}")
        if hasattr(record, "duration"):
            fields.append(f"DURATION={record.duration:.3f}")
        if hasattr(record, "size_bytes"):
            fields.append(f"SIZE={record.size_bytes}")
        if hasattr(record, "metrics"):
            # Metrics als JSON für structured logging
            try:
                fields.append("METRICS=" + json.dumps(record.metrics, separators=(",", ":")))
            except Exception:
                pass

        # Message at the end
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)

        # Combine fields and message
        return f"{' '.join(fields)} MESSAGE={msg}"

    def _format_colored(self, record: logging.LogRecord) -> str:
        """Format with colors for terminal output."""
        # Get color for level
        color = self.LEVEL_COLORS.get(record.levelname, "")
        symbol = self.LEVEL_SYMBOLS.get(record.levelname, "•")

        # Time
        time_str = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

        # Build colored output
        parts = [
            f"{Colors.GRAY}{time_str}{Colors.RESET}",
            f"{color}{symbol} {record.levelname:8}{Colors.RESET}",
        ]

        # Add module/function for DEBUG
        if record.levelname == "DEBUG":
            parts.append(f"{Colors.GRAY}[{record.module}.{record.funcName}]{Colors.RESET}")

        # Message
        msg = record.getMessage()

        # Highlight certain patterns
        if self.use_colors and record.levelname == "INFO":
            # Highlight success patterns
            msg = msg.replace("✓", f"{Colors.GREEN}✓{Colors.RESET}")
            msg = msg.replace("success", f"{Colors.GREEN}success{Colors.RESET}")

        elif self.use_colors and record.levelname in ("ERROR", "CRITICAL"):
            # Highlight error patterns
            msg = msg.replace("✗", f"{Colors.RED}✗{Colors.RESET}")
            msg = msg.replace("failed", f"{Colors.RED}failed{Colors.RESET}")

        parts.append(msg)

        # Exception info
        if record.exc_info:
            parts.append("\n" + self.formatException(record.exc_info))

        return " ".join(parts)

    def _format_plain(self, record: logging.LogRecord) -> str:
        """Format plain text output."""
        time_str = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

        msg = f"{time_str} - {record.levelname:8} - {record.getMessage()}"

        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)

        return msg

    def _syslog_priority(self, levelno: int) -> int:
        """Convert Python log level to syslog priority."""
        # Syslog priorities: DEBUG=7, INFO=6, WARNING=4, ERROR=3, CRITICAL=2
        if levelno <= logging.DEBUG:
            return 7
        elif levelno <= logging.INFO:
            return 6
        elif levelno <= logging.WARNING:
            return 4
        elif levelno <= logging.ERROR:
            return 3
        else:
            return 2


class LogManager:
    """
    Central log manager for Kopi-Docka.

    Provides unified logging configuration and helper methods.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize log manager."""
        if not self._initialized:
            self.logger = logging.getLogger("kopi-docka")
            self.start_time = time.time()
            self._initialized = True

    def setup(
        self,
        level: str = "INFO",
        log_file: Optional[Path] = None,
        max_size_mb: int = 100,
        backup_count: int = 5,
        verbose: bool = False,
    ):
        """
        Setup logging configuration.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: Optional log file path
            max_size_mb: Max size per log file in MB
            backup_count: Number of rotated log files to keep
            verbose: Enable verbose (DEBUG) logging
        """
        # Clear existing handlers
        self.logger.handlers.clear()

        # Set level
        if verbose:
            level = "DEBUG"
        self.logger.setLevel(getattr(logging, level.upper()))

        # Handler wählen: Echter JournalHandler wenn möglich, sonst Console
        console_handler = None

        if ("JOURNAL_STREAM" in os.environ) and _HAS_JOURNAL:
            # Echter systemd.journal Handler - structured fields funktionieren!
            journal_handler = JournalHandler()
            # Nur message, fields kommen via 'extra' dict
            journal_handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(journal_handler)
        else:
            # Fallback: Console handler (stderr for systemd compatibility)
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(StructuredFormatter())
            self.logger.addHandler(console_handler)

        # File handler with rotation (optional)
        if log_file:
            try:
                log_file = Path(log_file).expanduser()
                log_file.parent.mkdir(parents=True, exist_ok=True)

                file_handler = logging.handlers.RotatingFileHandler(
                    log_file,
                    maxBytes=max_size_mb * 1024 * 1024,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
                # Plain format für Files (keine Farben)
                file_handler.setFormatter(StructuredFormatter(use_colors=False, use_systemd=False))
                self.logger.addHandler(file_handler)

            except Exception as e:
                self.logger.warning(f"Could not setup file logging: {e}")

        # Propagate to root logger for libraries
        self.logger.propagate = False

        # Root logger für third-party libraries (nur wenn console handler da ist)
        if console_handler is not None:
            logging.root.handlers = [console_handler]
            logging.root.setLevel(logging.WARNING)  # Less verbose for libraries

    def get_logger(self, name: str = None) -> logging.Logger:
        """
        Get a logger instance.

        Args:
            name: Logger name (module name typically)

        Returns:
            Logger instance
        """
        if name:
            return logging.getLogger(f"kopi-docka.{name}")
        return self.logger

    @contextmanager
    def operation(self, name: str, unit: Optional[str] = None, **kwargs):
        """
        Context manager for logging operations with timing.

        Args:
            name: Operation name
            unit: Optional backup unit name
            **kwargs: Additional context fields

        Example:
            with log_manager.operation('backup', unit='my-stack'):
                # do backup
                pass  # Automatically logs start, end, duration
        """
        start_time = time.time()

        # Create context dict for structured logging
        context = {"operation": name}
        if unit:
            context["unit_name"] = unit
        context.update(kwargs)

        # Log start with extra fields for journald
        self.logger.info(f"Starting {name}", extra=context)

        try:
            yield

            # Success
            duration = time.time() - start_time
            context["duration"] = duration
            self.logger.info(f"✓ Completed {name} ({duration:.1f}s)", extra=context)

        except Exception as e:
            # Failure
            duration = time.time() - start_time
            context["duration"] = duration
            context["error"] = str(e)
            self.logger.error(
                f"✗ Failed {name} ({duration:.1f}s): {e}", extra=context, exc_info=True
            )
            raise

    def log_metrics(self, metrics: Dict[str, Any], level: str = "INFO"):
        """
        Log metrics/statistics.

        Args:
            metrics: Dictionary of metrics
            level: Log level
        """
        # Format metrics for logging
        metric_str = " ".join(f"{k}={v}" for k, v in metrics.items())

        # Pass metrics as extra for structured logging in journald
        self.logger.log(
            getattr(logging, level.upper()),
            f"Metrics: {metric_str}",
            extra={"metrics": metrics},
        )

    def log_summary(self, total_units: int, successful: int, failed: int, duration: float):
        """
        Log backup summary.

        Args:
            total_units: Total backup units
            successful: Successful backups
            failed: Failed backups
            duration: Total duration in seconds
        """
        # Determine level based on results
        if failed == 0:
            level = "INFO"
            symbol = "✓"
            status = "SUCCESS"
        elif failed < total_units:
            level = "WARNING"
            symbol = "⚠"
            status = "PARTIAL"
        else:
            level = "ERROR"
            symbol = "✗"
            status = "FAILED"

        self.logger.log(
            getattr(logging, level),
            f"{symbol} Backup {status}: {successful}/{total_units} units "
            f"({duration:.1f}s total)",
            extra={
                "total_units": total_units,
                "successful": successful,
                "failed": failed,
                "duration": duration,
                "status": status,
            },
        )

        # Exit with error code if failed
        if failed > 0:
            sys.exit(1)


# Global instance
log_manager = LogManager()


# Convenience functions
def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance."""
    return log_manager.get_logger(name)


def setup_logging(config: Optional[Any] = None, verbose: bool = False):
    """
    Setup logging from config object.

    Args:
        config: Config object with logging settings
        verbose: Override with verbose logging
    """
    if config:
        log_manager.setup(
            level=config.get("logging", "level", "INFO"),
            log_file=config.get("logging", "file"),
            max_size_mb=config.getint("logging", "max_size_mb", 100),
            backup_count=config.getint("logging", "backup_count", 5),
            verbose=verbose,
        )
    else:
        log_manager.setup(verbose=verbose)


# For module imports
__all__ = [
    "LogManager",
    "log_manager",
    "get_logger",
    "setup_logging",
    "Colors",
    "StructuredFormatter",
]
