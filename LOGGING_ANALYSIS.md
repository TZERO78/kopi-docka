# Logging Analysis - helpers/logging.py

**Version:** 4.0.0
**Date:** 2025-12-22

This document analyzes the current state of `helpers/logging.py` and provides recommendations.

---

## Executive Summary

**Status: Well-Designed - Minimal Changes Recommended**

The logging module is already well-centralized and follows best practices:
- Singleton `LogManager` pattern
- Structured logging for systemd/journald
- Color support with ANSI fallback
- Context managers for operation timing
- Metrics logging

**Recommendation:** No major refactoring needed. Only minor improvements suggested.

---

## Current Architecture

### 1. Colors Class (Lines 52-64)

```python
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
```

**Analysis:**
- Used by `StructuredFormatter` for terminal output
- Separate from Rich colors (intentional - logging vs UI)
- Good for systemd journal output where Rich isn't available

**Status:** Good

### 2. StructuredFormatter Class (Lines 67-251)

```python
class StructuredFormatter(logging.Formatter):
    """
    Formatter that outputs structured logs for systemd/journald.
    In systemd environment: JSON-like key=value pairs
    In terminal: Colored, human-readable format
    """
```

**Features:**
- Auto-detects systemd environment (`JOURNAL_STREAM`)
- Auto-detects terminal color support
- Three output modes:
  - `_format_systemd()` - structured key=value for journald
  - `_format_colored()` - ANSI colors for terminal
  - `_format_plain()` - plain text fallback

**Status:** Excellent

### 3. LogManager Class (Lines 254-464)

```python
class LogManager:
    """Central log manager for Kopi-Docka."""
    _instance = None  # Singleton
    _initialized = False
```

**Features:**
- Singleton pattern (one instance per process)
- Configurable log levels
- File handler with rotation (optional)
- Journal handler support (systemd-python)
- Context manager for operation timing (`operation()`)
- Metrics logging (`log_metrics()`)
- Summary logging (`log_summary()`)

**Status:** Excellent

### 4. Convenience Functions (Lines 467-494)

```python
log_manager = LogManager()

def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance."""
    return log_manager.get_logger(name)

def setup_logging(config: Optional[Any] = None, verbose: bool = False):
    """Setup logging from config object."""
```

**Status:** Good

---

## Minor Issues Found

### Issue 1: LogManager.setup() vs LogManager.configure()

In `__main__.py`, the code calls `log_manager.configure()`:

```python
# __main__.py:114
log_manager.configure(level=log_level.upper())
```

But `LogManager` has a `setup()` method, not `configure()`:

```python
# logging.py:277
def setup(self, level: str = "INFO", ...):
```

**This is a bug!** The code should be calling `setup()`, not `configure()`.

**Fix:**
```python
# __main__.py:114
log_manager.setup(level=log_level.upper())
```

### Issue 2: Potential Duplication

Some command files create their own loggers without using the centralized `get_logger()`:

```python
# Example from some files
import logging
logger = logging.getLogger(__name__)  # Not using get_logger()
```

**Recommendation:** Audit all files and ensure they use:
```python
from ..helpers import get_logger
logger = get_logger(__name__)
```

---

## Recommendations

### Recommendation 1: Fix configure() Bug

**Priority:** HIGH

In `kopi_docka/__main__.py`, line 114:

```diff
 try:
-    log_manager.configure(level=log_level.upper())
+    log_manager.setup(level=log_level.upper())
 except Exception:
```

### Recommendation 2: Add Method Alias (Optional)

**Priority:** LOW

If backward compatibility is desired, add an alias:

```python
# In LogManager class
def configure(self, *args, **kwargs):
    """Alias for setup() for backward compatibility."""
    return self.setup(*args, **kwargs)
```

### Recommendation 3: Audit Logger Usage

**Priority:** MEDIUM

Ensure all command files use the centralized logger:

```python
# Correct
from ..helpers import get_logger
logger = get_logger(__name__)

# Incorrect
import logging
logger = logging.getLogger(__name__)
```

**Files to audit:**
- All files in `kopi_docka/commands/`
- All files in `kopi_docka/cores/`
- All files in `kopi_docka/backends/`

### Recommendation 4: Consider Console Logger (Optional)

**Priority:** LOW

For cases where Rich console output and logging should be coordinated:

```python
def console_log(level: str, message: str, console_only: bool = False):
    """
    Log message and optionally print to console.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        message: Message to log
        console_only: If True, only print to console, don't log
    """
    if not console_only:
        getattr(logger, level.lower())(message)

    # Also print to Rich console with appropriate styling
    if level == "ERROR":
        console.print(f"[red]✗ {message}[/red]")
    elif level == "WARNING":
        console.print(f"[yellow]⚠ {message}[/yellow]")
    elif level == "INFO":
        console.print(f"[green]✓ {message}[/green]")
```

---

## Integration with Rich

### Current Separation (Good)

The logging module intentionally uses ANSI colors (`Colors` class) rather than Rich:

1. **Logging** → ANSI colors for journald/systemd compatibility
2. **UI** → Rich for beautiful terminal output

This separation is correct because:
- journald doesn't understand Rich markup
- Log files should have plain or ANSI-colored text
- UI output should be beautiful and interactive

### No Changes Needed

The logging module should remain focused on logging, not UI output. The `ui_utils.py` module handles all Rich-based UI output.

---

## Usage Examples

### Correct Usage Pattern

```python
# In a command file
from ..helpers import get_logger, Config
from ..helpers.ui_utils import print_success, print_error, console

logger = get_logger(__name__)

def cmd_example():
    """Example command with proper logging and UI."""

    # User-facing output (Rich)
    print_success("Operation started")

    # Logging (for systemd journal and log files)
    logger.info("Operation started")

    try:
        # Do something
        result = do_something()

        # User-facing success (Rich)
        print_success(f"Completed: {result}")

        # Logging
        logger.info(f"Completed: {result}")

    except Exception as e:
        # User-facing error (Rich)
        print_error(f"Failed: {e}")

        # Logging with traceback
        logger.error(f"Failed: {e}", exc_info=True)
```

### Using Operation Context Manager

```python
from ..helpers.logging import log_manager

def backup_unit(unit):
    """Backup a unit with timing."""

    with log_manager.operation("backup", unit=unit.name):
        # Automatically logs start and end with duration
        do_backup(unit)

    # Logs:
    # INFO: Starting backup
    # INFO: ✓ Completed backup (5.2s)
```

---

## Files Analysis

### Files Using get_logger() Correctly

- `kopi_docka/commands/setup_commands.py`
- `kopi_docka/commands/backup_commands.py`
- `kopi_docka/commands/config_commands.py`
- `kopi_docka/commands/service_commands.py`
- `kopi_docka/commands/doctor_commands.py`
- Most core and backend modules

### Files to Verify

Run this command to find any files using raw `logging.getLogger()`:

```bash
grep -r "logging.getLogger" --include="*.py" kopi_docka/
```

---

## Conclusion

The logging module is well-designed and doesn't require major refactoring. The only actionable item is:

1. **Fix the `configure()` bug** in `__main__.py` (should be `setup()`)

Optional improvements:
- Add `configure()` as alias for backward compatibility
- Audit all files for consistent `get_logger()` usage

---

**End of Logging Analysis**
