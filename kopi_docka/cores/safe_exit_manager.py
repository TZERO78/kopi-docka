"""
Safe Exit Manager - Two-Layer Architecture for graceful shutdown.

Layer 1 (Process): Automatic subprocess tracking via run_command
Layer 2 (Strategy): Context-aware cleanup handlers per manager
"""

import os
import signal
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from ..helpers.logging import get_logger

# Optional systemd integration
try:
    from .service_manager import sd_notify_stopping, sd_notify_watchdog
    HAS_SD_NOTIFY = True
except ImportError:
    HAS_SD_NOTIFY = False

logger = get_logger(__name__)


@dataclass
class TrackedProcess:
    """A subprocess registered for cleanup on abort."""

    pid: int
    name: str
    registered_at: float


class ExitHandler:
    """Base class for exit handlers (Strategy pattern)."""

    priority: int = 100  # Lower = higher priority
    name: str = "base"

    def cleanup(self) -> None:
        """Override in subclass."""
        raise NotImplementedError


class SafeExitManager:
    """
    Singleton manager for graceful shutdown with two-layer architecture.

    Process Layer: Tracks all subprocesses, terminates on abort
    Strategy Layer: Context-aware cleanup handlers (container restart, temp cleanup)
    """

    _instance: Optional["SafeExitManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        if SafeExitManager._instance is not None:
            raise RuntimeError("Use SafeExitManager.get_instance()")

        # Process Layer
        self._processes: Dict[str, TrackedProcess] = {}
        self._process_lock = threading.Lock()

        # Strategy Layer
        self._handlers: List[Tuple[ExitHandler, int]] = []
        self._handler_lock = threading.Lock()

        # State
        self._cleanup_in_progress = False
        self._original_sigint = None
        self._original_sigterm = None

    @classmethod
    def get_instance(cls) -> "SafeExitManager":
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing only)."""
        with cls._lock:
            cls._instance = None

    # --------------- Signal Installation ---------------

    def install_handlers(self) -> None:
        """Install SIGINT/SIGTERM handlers. Call once at startup."""
        self._original_sigint = signal.signal(signal.SIGINT, self._signal_handler)
        self._original_sigterm = signal.signal(signal.SIGTERM, self._signal_handler)
        logger.debug("SafeExitManager: Signal handlers installed")

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle SIGINT/SIGTERM with graceful cleanup."""
        sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"

        if self._cleanup_in_progress:
            logger.warning(f"Received {sig_name} during cleanup - forcing exit")
            sys.exit(128 + signum)

        self._cleanup_in_progress = True
        logger.warning(f"Received {sig_name} - starting emergency cleanup...")

        # Notify systemd that we're stopping gracefully
        if HAS_SD_NOTIFY:
            sd_notify_stopping("Emergency cleanup in progress")

        # Layer 1: Terminate all tracked processes
        self._terminate_all_processes()

        # Reset watchdog before running handlers (can take time)
        if HAS_SD_NOTIFY:
            sd_notify_watchdog()

        # Layer 2: Run all registered handlers (sorted by priority)
        self._run_all_handlers()

        exit_code = 130 if signum == signal.SIGINT else 143
        logger.info(f"Cleanup complete, exiting with code {exit_code}")
        sys.exit(exit_code)

    # --------------- Process Layer ---------------

    def register_process(self, pid: int, name: str) -> str:
        """Register a subprocess for tracking. Returns cleanup_id."""
        cleanup_id = str(uuid.uuid4())
        with self._process_lock:
            self._processes[cleanup_id] = TrackedProcess(
                pid=pid, name=name, registered_at=time.time()
            )
        logger.debug(f"SafeExit: Registered process {name} (PID {pid})")
        return cleanup_id

    def unregister_process(self, cleanup_id: str) -> None:
        """Remove a process from tracking."""
        with self._process_lock:
            if cleanup_id in self._processes:
                proc = self._processes.pop(cleanup_id)
                logger.debug(f"SafeExit: Unregistered process {proc.name}")

    def _terminate_all_processes(self) -> None:
        """Terminate all tracked processes (SIGTERM -> SIGKILL)."""
        with self._process_lock:
            if not self._processes:
                logger.debug("No tracked processes to terminate")
                return

            count = len(self._processes)
            logger.warning(f"EMERGENCY: Terminating {count} tracked process(es)...")

            # First pass: SIGTERM
            for cleanup_id, proc in list(self._processes.items()):
                try:
                    os.kill(proc.pid, signal.SIGTERM)
                    logger.info(f"  SIGTERM -> {proc.name} (PID {proc.pid})")
                except ProcessLookupError:
                    logger.debug(f"  Process {proc.name} already exited")
                except Exception as e:
                    logger.error(f"  Failed to SIGTERM {proc.name}: {e}")

            # Wait for graceful termination
            time.sleep(5)

            # Second pass: SIGKILL for survivors
            for cleanup_id, proc in list(self._processes.items()):
                try:
                    os.kill(proc.pid, 0)  # Check if still alive
                    os.kill(proc.pid, signal.SIGKILL)
                    logger.warning(f"  SIGKILL -> {proc.name} (PID {proc.pid})")
                except ProcessLookupError:
                    pass
                except Exception as e:
                    logger.error(f"  Failed to SIGKILL {proc.name}: {e}")

            self._processes.clear()

    # --------------- Strategy Layer ---------------

    def register_handler(self, handler: ExitHandler) -> None:
        """Register an exit handler."""
        with self._handler_lock:
            self._handlers.append((handler, handler.priority))
            self._handlers.sort(key=lambda x: x[1])
        logger.debug(
            f"SafeExit: Registered handler {handler.name} (priority {handler.priority})"
        )

    def unregister_handler(self, handler: ExitHandler) -> None:
        """Remove an exit handler."""
        with self._handler_lock:
            self._handlers = [(h, p) for h, p in self._handlers if h is not handler]
        logger.debug(f"SafeExit: Unregistered handler {handler.name}")

    def _run_all_handlers(self) -> None:
        """Run all registered handlers in priority order."""
        with self._handler_lock:
            handlers = list(self._handlers)

        if not handlers:
            logger.debug("No exit handlers registered")
            return

        logger.info(f"Running {len(handlers)} exit handler(s)...")
        for handler, priority in handlers:
            try:
                logger.info(f"  Running handler: {handler.name}")
                handler.cleanup()
            except Exception as e:
                logger.error(f"  Handler {handler.name} failed: {e}")


# ===== Strategy Handlers =====


class ServiceContinuityHandler(ExitHandler):
    """Handler for backup: Restart stopped containers on abort."""

    priority = 10
    name = "service_continuity"

    def __init__(self):
        self._containers: List[Tuple[str, str]] = []  # (id, name)
        self._lock = threading.Lock()

    def register_container(self, container_id: str, container_name: str) -> None:
        """Register a container that was stopped for backup."""
        with self._lock:
            self._containers.append((container_id, container_name))
        logger.debug(f"ServiceContinuity: Registered {container_name}")

    def unregister_container(self, container_id: str) -> None:
        """Remove container from tracking."""
        with self._lock:
            self._containers = [
                (cid, name) for cid, name in self._containers if cid != container_id
            ]

    def cleanup(self) -> None:
        """Restart all tracked containers (LIFO order)."""
        from ..helpers.ui_utils import SubprocessError, run_command

        with self._lock:
            containers = list(reversed(self._containers))  # LIFO

        if not containers:
            logger.info("ServiceContinuity: No containers to restart")
            return

        logger.warning(f"ServiceContinuity: Restarting {len(containers)} container(s)...")

        for container_id, container_name in containers:
            try:
                logger.info(f"  Starting {container_name}...")
                run_command(
                    ["docker", "start", container_id],
                    f"Emergency restart {container_name}",
                    timeout=30,
                )
                logger.info(f"  [OK] {container_name} started")
            except SubprocessError as e:
                logger.error(f"  [FAILED] {container_name}: {e.stderr}")
            except Exception as e:
                logger.error(f"  [FAILED] {container_name}: {e}")


class DataSafetyHandler(ExitHandler):
    """Handler for restore: Keep containers stopped, cleanup temp."""

    priority = 20
    name = "data_safety"

    def __init__(self):
        self._temp_dirs: List[str] = []
        self._stopped_containers: List[str] = []
        self._lock = threading.Lock()

    def register_temp_dir(self, path: str) -> None:
        """Register a temporary directory for cleanup."""
        with self._lock:
            self._temp_dirs.append(path)

    def register_stopped_container(self, container_name: str) -> None:
        """Register a container that should remain stopped for safety."""
        with self._lock:
            self._stopped_containers.append(container_name)

    def cleanup(self) -> None:
        """Clean up temp directories and warn about stopped containers."""
        import shutil

        with self._lock:
            temp_dirs = list(self._temp_dirs)
            containers = list(self._stopped_containers)

        for path in temp_dirs:
            try:
                if os.path.exists(path):
                    shutil.rmtree(path)
                    logger.info(f"DataSafety: Removed temp dir {path}")
            except Exception as e:
                logger.warning(f"DataSafety: Failed to remove {path}: {e}")

        if containers:
            logger.warning("DataSafety: Containers remain STOPPED for safety:")
            for name in containers:
                logger.warning(f"  - {name}")
            logger.warning("Manually restart: docker start <container_name>")


class CleanupHandler(ExitHandler):
    """Generic cleanup handler for arbitrary callbacks."""

    priority = 50
    name = "cleanup"

    def __init__(self, name: str = "cleanup", callback: Optional[Callable] = None):
        self.name = name
        self._callback = callback
        self._cleanup_items: List[Tuple[str, Callable]] = []
        self._lock = threading.Lock()

    def register_cleanup(self, name: str, callback: Callable) -> None:
        """Register a cleanup callback."""
        with self._lock:
            self._cleanup_items.append((name, callback))

    def cleanup(self) -> None:
        """Execute all registered cleanup callbacks."""
        with self._lock:
            items = list(self._cleanup_items)

        for name, callback in items:
            try:
                logger.info(f"Cleanup: Running {name}")
                callback()
            except Exception as e:
                logger.warning(f"Cleanup: {name} failed: {e}")

        if self._callback:
            try:
                self._callback()
            except Exception as e:
                logger.warning(f"Cleanup: Main callback failed: {e}")
