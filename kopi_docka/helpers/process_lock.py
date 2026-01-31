################################################################################
# KOPI-DOCKA
#
# @file:        process_lock.py
# @module:      kopi_docka.helpers
# @description: Global process lock to prevent concurrent backup execution
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     6.0.2
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025-2026 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Global process lock using fcntl.flock() to prevent concurrent backup execution.

Features:
- Non-blocking lock acquisition
- Auto-release on process termination (kernel-managed)
- PID tracking for debugging
- Fallback path if /run is not writable
"""

import fcntl
import os
from pathlib import Path
from typing import Optional

from .logging import get_logger

logger = get_logger(__name__)

# Lock file locations
DEFAULT_LOCK_PATH = "/run/kopi-docka.lock"
FALLBACK_LOCK_PATH = "/tmp/kopi-docka.lock"


class ProcessLock:
    """
    Non-blocking file lock using fcntl.flock().
    
    Prevents multiple concurrent executions of critical operations like backup.
    The kernel automatically releases the lock when the process terminates,
    even on crashes (no stale lock problem).
    
    Usage:
        lock = ProcessLock()
        if not lock.acquire():
            print(f"Already running (PID: {lock.get_holder_pid()})")
            sys.exit(0)
        try:
            # ... do work ...
        finally:
            lock.release()
    
    Or as context manager:
        with ProcessLock() as lock:
            # ... do work ...
    """
    
    def __init__(self, lock_path: Optional[str] = None):
        """
        Initialize process lock.
        
        Args:
            lock_path: Custom lock file path. If None, uses /run/kopi-docka.lock
                      with fallback to /tmp/kopi-docka.lock if /run is not writable.
        """
        self.lock_path = Path(lock_path) if lock_path else self._get_default_lock_path()
        self._fd: Optional[int] = None
        self._locked = False
    
    def _get_default_lock_path(self) -> Path:
        """Determine appropriate lock path based on permissions."""
        if os.access("/run", os.W_OK):
            return Path(DEFAULT_LOCK_PATH)
        logger.debug(f"/run not writable, using fallback: {FALLBACK_LOCK_PATH}")
        return Path(FALLBACK_LOCK_PATH)
    
    def acquire(self) -> bool:
        """
        Try to acquire the lock (non-blocking).
        
        Returns:
            True if lock acquired successfully, False if already locked by another process.
        """
        try:
            # Open or create lock file
            self._fd = os.open(
                str(self.lock_path),
                os.O_CREAT | os.O_RDWR,
                0o644
            )
            
            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Write our PID for debugging
            os.ftruncate(self._fd, 0)
            os.write(self._fd, f"{os.getpid()}\n".encode())
            os.fsync(self._fd)
            
            self._locked = True
            logger.debug(f"Lock acquired: {self.lock_path} (PID: {os.getpid()})")
            return True
            
        except (BlockingIOError, OSError) as e:
            # Lock is held by another process
            logger.debug(f"Lock acquisition failed: {e}")
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            return False
    
    def release(self) -> None:
        """Release the lock."""
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                logger.debug(f"Lock released: {self.lock_path}")
            except OSError as e:
                logger.warning(f"Error releasing lock: {e}")
            finally:
                self._fd = None
                self._locked = False
    
    def get_holder_pid(self) -> Optional[int]:
        """
        Read PID of current lock holder from lock file.
        
        Returns:
            PID of lock holder, or None if cannot be determined.
        """
        try:
            if self.lock_path.exists():
                content = self.lock_path.read_text().strip()
                return int(content)
        except (FileNotFoundError, ValueError, PermissionError):
            pass
        return None
    
    def is_locked(self) -> bool:
        """Check if this instance holds the lock."""
        return self._locked
    
    def __enter__(self) -> "ProcessLock":
        """Context manager entry - acquire lock or raise."""
        if not self.acquire():
            holder_pid = self.get_holder_pid()
            raise BlockingIOError(
                f"Lock held by another process (PID: {holder_pid})"
            )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - release lock."""
        self.release()
    
    def __del__(self):
        """Destructor - ensure lock is released."""
        if self._locked:
            self.release()
