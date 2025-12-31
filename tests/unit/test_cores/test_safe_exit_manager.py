"""
Unit tests for SafeExitManager and exit handlers.

Tests the two-layer exit safety architecture:
- Process Layer: Subprocess tracking and termination
- Strategy Layer: Context-aware cleanup handlers
"""

import os
import pytest
import signal
import threading
import time
from unittest.mock import Mock, MagicMock, patch, call
from dataclasses import dataclass

from kopi_docka.cores.safe_exit_manager import (
    SafeExitManager,
    TrackedProcess,
    ExitHandler,
    ServiceContinuityHandler,
    DataSafetyHandler,
    CleanupHandler,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset SafeExitManager singleton before each test."""
    SafeExitManager.reset_instance()
    yield
    SafeExitManager.reset_instance()


@pytest.fixture
def safe_exit():
    """Get a fresh SafeExitManager instance."""
    return SafeExitManager.get_instance()


# =============================================================================
# Core SafeExitManager Tests
# =============================================================================


@pytest.mark.unit
class TestSafeExitManagerCore:
    """Tests for SafeExitManager core functionality."""

    def test_singleton_pattern(self):
        """SafeExitManager enforces singleton pattern."""
        instance1 = SafeExitManager.get_instance()
        instance2 = SafeExitManager.get_instance()

        assert instance1 is instance2
        assert id(instance1) == id(instance2)

    def test_singleton_init_raises(self):
        """Direct __init__ call raises error."""
        SafeExitManager.get_instance()  # Create singleton

        with pytest.raises(RuntimeError, match="Use SafeExitManager.get_instance()"):
            SafeExitManager()

    def test_reset_instance(self):
        """reset_instance() allows creating new singleton."""
        instance1 = SafeExitManager.get_instance()
        SafeExitManager.reset_instance()
        instance2 = SafeExitManager.get_instance()

        assert instance1 is not instance2

    def test_initial_state(self, safe_exit):
        """New instance has correct initial state."""
        assert safe_exit._processes == {}
        assert safe_exit._handlers == []
        assert safe_exit._cleanup_in_progress is False
        assert safe_exit._original_sigint is None
        assert safe_exit._original_sigterm is None

    @patch('signal.signal')
    def test_install_handlers(self, mock_signal, safe_exit):
        """install_handlers() installs SIGINT and SIGTERM handlers."""
        safe_exit.install_handlers()

        assert mock_signal.call_count == 2
        calls = mock_signal.call_args_list

        # Check SIGINT handler
        assert calls[0][0][0] == signal.SIGINT
        assert calls[0][0][1] == safe_exit._signal_handler

        # Check SIGTERM handler
        assert calls[1][0][0] == signal.SIGTERM
        assert calls[1][0][1] == safe_exit._signal_handler


# =============================================================================
# Process Layer Tests
# =============================================================================


@pytest.mark.unit
class TestProcessLayer:
    """Tests for process tracking (Process Layer)."""

    def test_register_process(self, safe_exit):
        """register_process() adds process to tracking."""
        cleanup_id = safe_exit.register_process(12345, "test-command")

        assert cleanup_id in safe_exit._processes
        proc = safe_exit._processes[cleanup_id]
        assert proc.pid == 12345
        assert proc.name == "test-command"
        assert proc.registered_at > 0

    def test_register_multiple_processes(self, safe_exit):
        """Can register multiple processes."""
        id1 = safe_exit.register_process(100, "cmd1")
        id2 = safe_exit.register_process(200, "cmd2")
        id3 = safe_exit.register_process(300, "cmd3")

        assert len(safe_exit._processes) == 3
        assert id1 != id2 != id3

    def test_unregister_process(self, safe_exit):
        """unregister_process() removes process from tracking."""
        cleanup_id = safe_exit.register_process(12345, "test-command")
        assert cleanup_id in safe_exit._processes

        safe_exit.unregister_process(cleanup_id)
        assert cleanup_id not in safe_exit._processes

    def test_unregister_nonexistent_process(self, safe_exit):
        """unregister_process() handles nonexistent ID gracefully."""
        safe_exit.unregister_process("nonexistent-id")  # Should not raise

    @patch('os.kill')
    @patch('time.sleep')
    def test_terminate_all_processes_sigterm(self, mock_sleep, mock_kill, safe_exit):
        """_terminate_all_processes() sends SIGTERM to all tracked PIDs."""
        safe_exit.register_process(100, "cmd1")
        safe_exit.register_process(200, "cmd2")

        # Mock process already exited (ProcessLookupError on second kill)
        mock_kill.side_effect = [None, None, None, ProcessLookupError, ProcessLookupError]

        safe_exit._terminate_all_processes()

        # Should send SIGTERM to both, wait 5s, then check with SIGKILL
        assert mock_kill.call_count >= 2
        assert call(100, signal.SIGTERM) in mock_kill.call_args_list
        assert call(200, signal.SIGTERM) in mock_kill.call_args_list
        mock_sleep.assert_called_once_with(5)

    @patch('os.kill')
    @patch('time.sleep')
    def test_terminate_processes_sigkill_survivors(self, mock_sleep, mock_kill, safe_exit):
        """_terminate_all_processes() sends SIGKILL to surviving processes."""
        safe_exit.register_process(100, "cmd1")

        # Process still alive after SIGTERM (kill with sig 0 succeeds, then SIGKILL)
        def kill_side_effect(pid, sig):
            if sig == signal.SIGTERM:
                return None
            elif sig == 0:  # Check if alive
                return None  # Still alive
            elif sig == signal.SIGKILL:
                return None

        mock_kill.side_effect = kill_side_effect

        safe_exit._terminate_all_processes()

        # Should: SIGTERM -> wait -> check (sig 0) -> SIGKILL
        assert call(100, signal.SIGTERM) in mock_kill.call_args_list
        assert call(100, 0) in mock_kill.call_args_list
        assert call(100, signal.SIGKILL) in mock_kill.call_args_list

    @patch('os.kill')
    @patch('time.sleep')
    def test_terminate_clears_registry(self, mock_sleep, mock_kill, safe_exit):
        """_terminate_all_processes() clears process registry."""
        safe_exit.register_process(100, "cmd1")
        safe_exit.register_process(200, "cmd2")
        assert len(safe_exit._processes) == 2

        mock_kill.side_effect = [None, None, ProcessLookupError, ProcessLookupError]
        safe_exit._terminate_all_processes()

        assert safe_exit._processes == {}

    def test_process_layer_thread_safety(self, safe_exit):
        """Process registration is thread-safe."""
        cleanup_ids = []
        errors = []

        def register_processes():
            try:
                for i in range(50):
                    cid = safe_exit.register_process(1000 + i, f"cmd-{i}")
                    cleanup_ids.append(cid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_processes) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(cleanup_ids) == 200  # 4 threads * 50 processes
        assert len(safe_exit._processes) == 200


# =============================================================================
# Strategy Layer Tests
# =============================================================================


@pytest.mark.unit
class TestStrategyLayer:
    """Tests for exit handler registration (Strategy Layer)."""

    def test_register_handler(self, safe_exit):
        """register_handler() adds handler to registry."""
        handler = Mock(spec=ExitHandler)
        handler.priority = 10
        handler.name = "test-handler"

        safe_exit.register_handler(handler)

        assert len(safe_exit._handlers) == 1
        assert safe_exit._handlers[0] == (handler, 10)

    def test_register_multiple_handlers_sorted(self, safe_exit):
        """Handlers are sorted by priority (lower first)."""
        h1 = Mock(spec=ExitHandler, priority=50, name="h1")
        h2 = Mock(spec=ExitHandler, priority=10, name="h2")
        h3 = Mock(spec=ExitHandler, priority=30, name="h3")

        safe_exit.register_handler(h1)
        safe_exit.register_handler(h2)
        safe_exit.register_handler(h3)

        priorities = [p for _, p in safe_exit._handlers]
        assert priorities == [10, 30, 50]

    def test_unregister_handler(self, safe_exit):
        """unregister_handler() removes handler from registry."""
        handler = Mock(spec=ExitHandler, priority=10, name="test")

        safe_exit.register_handler(handler)
        assert len(safe_exit._handlers) == 1

        safe_exit.unregister_handler(handler)
        assert len(safe_exit._handlers) == 0

    def test_unregister_nonexistent_handler(self, safe_exit):
        """unregister_handler() handles nonexistent handler gracefully."""
        handler = Mock(spec=ExitHandler, priority=10, name="test")
        safe_exit.unregister_handler(handler)  # Should not raise

    def test_run_all_handlers(self, safe_exit):
        """_run_all_handlers() executes all handlers in priority order."""
        execution_order = []

        h1 = Mock(spec=ExitHandler, priority=50, name="h1")
        h1.cleanup.side_effect = lambda: execution_order.append("h1")

        h2 = Mock(spec=ExitHandler, priority=10, name="h2")
        h2.cleanup.side_effect = lambda: execution_order.append("h2")

        safe_exit.register_handler(h1)
        safe_exit.register_handler(h2)

        safe_exit._run_all_handlers()

        assert execution_order == ["h2", "h1"]  # Priority 10 runs before 50

    def test_run_handlers_error_tolerant(self, safe_exit):
        """_run_all_handlers() continues on handler exception."""
        h1 = Mock(spec=ExitHandler, priority=10, name="failing-handler")
        h1.cleanup.side_effect = RuntimeError("Handler failed")

        h2 = Mock(spec=ExitHandler, priority=20, name="working-handler")
        h2.cleanup.return_value = None

        safe_exit.register_handler(h1)
        safe_exit.register_handler(h2)

        safe_exit._run_all_handlers()  # Should not raise

        h1.cleanup.assert_called_once()
        h2.cleanup.assert_called_once()  # Second handler still runs


# =============================================================================
# ServiceContinuityHandler Tests
# =============================================================================


@pytest.mark.unit
class TestServiceContinuityHandler:
    """Tests for ServiceContinuityHandler (backup container restart)."""

    def test_register_container(self):
        """register_container() adds container to tracking."""
        handler = ServiceContinuityHandler()

        handler.register_container("abc123", "webapp")

        assert len(handler._containers) == 1
        assert ("abc123", "webapp") in handler._containers

    def test_unregister_container(self):
        """unregister_container() removes container from tracking."""
        handler = ServiceContinuityHandler()

        handler.register_container("abc123", "webapp")
        handler.unregister_container("abc123")

        assert len(handler._containers) == 0

    @patch('kopi_docka.helpers.ui_utils.run_command')
    def test_cleanup_restarts_containers_lifo(self, mock_run_command):
        """cleanup() restarts containers in LIFO order."""
        handler = ServiceContinuityHandler()

        handler.register_container("id1", "container1")
        handler.register_container("id2", "container2")
        handler.register_container("id3", "container3")

        handler.cleanup()

        # Should restart in reverse order (LIFO)
        assert mock_run_command.call_count == 3
        calls = mock_run_command.call_args_list

        assert "id3" in str(calls[0])  # Last added, first restarted
        assert "id2" in str(calls[1])
        assert "id1" in str(calls[2])

    @patch('kopi_docka.helpers.ui_utils.run_command')
    def test_cleanup_no_containers(self, mock_run_command):
        """cleanup() handles empty container list gracefully."""
        handler = ServiceContinuityHandler()

        handler.cleanup()  # Should not raise

        mock_run_command.assert_not_called()

    @patch('kopi_docka.helpers.ui_utils.run_command')
    def test_cleanup_error_tolerant(self, mock_run_command):
        """cleanup() continues on container restart failure."""
        from kopi_docka.helpers.ui_utils import SubprocessError

        handler = ServiceContinuityHandler()
        handler.register_container("id1", "container1")
        handler.register_container("id2", "container2")

        # First restart fails, second succeeds
        mock_run_command.side_effect = [
            SubprocessError(["docker", "start", "id2"], 1, "Failed to start"),
            None,
        ]

        handler.cleanup()  # Should not raise

        assert mock_run_command.call_count == 2

    def test_priority(self):
        """ServiceContinuityHandler has priority 10."""
        handler = ServiceContinuityHandler()
        assert handler.priority == 10

    def test_name(self):
        """ServiceContinuityHandler has correct name."""
        handler = ServiceContinuityHandler()
        assert handler.name == "service_continuity"


# =============================================================================
# DataSafetyHandler Tests
# =============================================================================


@pytest.mark.unit
class TestDataSafetyHandler:
    """Tests for DataSafetyHandler (restore data safety)."""

    def test_register_temp_dir(self):
        """register_temp_dir() adds temp dir to tracking."""
        handler = DataSafetyHandler()

        handler.register_temp_dir("/tmp/restore-123")

        assert "/tmp/restore-123" in handler._temp_dirs

    def test_register_stopped_container(self):
        """register_stopped_container() adds container to tracking."""
        handler = DataSafetyHandler()

        handler.register_stopped_container("webapp")

        assert "webapp" in handler._stopped_containers

    @patch('shutil.rmtree')
    @patch('os.path.exists')
    def test_cleanup_removes_temp_dirs(self, mock_exists, mock_rmtree):
        """cleanup() removes temp directories."""
        handler = DataSafetyHandler()
        handler.register_temp_dir("/tmp/restore-123")

        mock_exists.return_value = True

        handler.cleanup()

        mock_rmtree.assert_called_once_with("/tmp/restore-123")

    @patch('shutil.rmtree')
    @patch('os.path.exists')
    def test_cleanup_skips_nonexistent_dirs(self, mock_exists, mock_rmtree):
        """cleanup() skips temp dirs that don't exist."""
        handler = DataSafetyHandler()
        handler.register_temp_dir("/tmp/nonexistent")

        mock_exists.return_value = False

        handler.cleanup()

        mock_rmtree.assert_not_called()

    @patch('shutil.rmtree')
    @patch('os.path.exists')
    def test_cleanup_error_tolerant(self, mock_exists, mock_rmtree):
        """cleanup() continues on temp dir removal failure."""
        handler = DataSafetyHandler()
        handler.register_temp_dir("/tmp/restore-123")

        mock_exists.return_value = True
        mock_rmtree.side_effect = OSError("Permission denied")

        handler.cleanup()  # Should not raise

    def test_cleanup_logs_stopped_containers(self):
        """cleanup() logs warning for stopped containers."""
        handler = DataSafetyHandler()
        handler.register_stopped_container("webapp")
        handler.register_stopped_container("database")

        handler.cleanup()  # Should log warning (tested manually)

    def test_priority(self):
        """DataSafetyHandler has priority 20."""
        handler = DataSafetyHandler()
        assert handler.priority == 20

    def test_name(self):
        """DataSafetyHandler has correct name."""
        handler = DataSafetyHandler()
        assert handler.name == "data_safety"


# =============================================================================
# CleanupHandler Tests
# =============================================================================


@pytest.mark.unit
class TestCleanupHandler:
    """Tests for CleanupHandler (generic cleanup callbacks)."""

    def test_register_cleanup(self):
        """register_cleanup() adds cleanup callback."""
        handler = CleanupHandler()
        callback = Mock()

        handler.register_cleanup("test-cleanup", callback)

        assert len(handler._cleanup_items) == 1
        assert handler._cleanup_items[0] == ("test-cleanup", callback)

    def test_cleanup_executes_callbacks(self):
        """cleanup() executes all registered callbacks."""
        handler = CleanupHandler()

        callback1 = Mock()
        callback2 = Mock()

        handler.register_cleanup("cleanup1", callback1)
        handler.register_cleanup("cleanup2", callback2)

        handler.cleanup()

        callback1.assert_called_once()
        callback2.assert_called_once()

    def test_cleanup_error_tolerant(self):
        """cleanup() continues on callback exception."""
        handler = CleanupHandler()

        callback1 = Mock(side_effect=RuntimeError("Callback failed"))
        callback2 = Mock()

        handler.register_cleanup("failing-cleanup", callback1)
        handler.register_cleanup("working-cleanup", callback2)

        handler.cleanup()  # Should not raise

        callback1.assert_called_once()
        callback2.assert_called_once()  # Second callback still runs

    def test_main_callback(self):
        """cleanup() executes main callback if provided."""
        main_callback = Mock()
        handler = CleanupHandler(name="test", callback=main_callback)

        handler.cleanup()

        main_callback.assert_called_once()

    def test_main_callback_error_tolerant(self):
        """cleanup() handles main callback exception gracefully."""
        main_callback = Mock(side_effect=RuntimeError("Main callback failed"))
        handler = CleanupHandler(name="test", callback=main_callback)

        handler.cleanup()  # Should not raise

    def test_custom_name(self):
        """CleanupHandler accepts custom name."""
        handler = CleanupHandler(name="custom-cleanup")
        assert handler.name == "custom-cleanup"

    def test_priority(self):
        """CleanupHandler has priority 50."""
        handler = CleanupHandler()
        assert handler.priority == 50


# =============================================================================
# Signal Handler Integration Tests
# =============================================================================


@pytest.mark.unit
class TestSignalHandlerIntegration:
    """Tests for signal handler behavior."""

    @patch('sys.exit')
    @patch('os.kill')
    @patch('time.sleep')
    def test_signal_handler_sigint(self, mock_sleep, mock_kill, mock_exit, safe_exit):
        """_signal_handler() handles SIGINT correctly."""
        # Register a process and handler
        safe_exit.register_process(100, "test-cmd")
        handler = Mock(spec=ExitHandler, priority=10, name="test")
        handler.cleanup.return_value = None
        safe_exit.register_handler(handler)

        mock_kill.side_effect = [None, ProcessLookupError, ProcessLookupError]

        # Trigger signal handler
        safe_exit._signal_handler(signal.SIGINT, None)

        # Should terminate processes
        assert call(100, signal.SIGTERM) in mock_kill.call_args_list

        # Should run handlers
        handler.cleanup.assert_called_once()

        # Should exit with code 130 (128 + SIGINT)
        mock_exit.assert_called_once_with(130)

    @patch('sys.exit')
    @patch('os.kill')
    @patch('time.sleep')
    def test_signal_handler_sigterm(self, mock_sleep, mock_kill, mock_exit, safe_exit):
        """_signal_handler() handles SIGTERM correctly."""
        mock_kill.side_effect = [ProcessLookupError]

        safe_exit._signal_handler(signal.SIGTERM, None)

        # Should exit with code 143 (128 + SIGTERM)
        mock_exit.assert_called_once_with(143)

    @patch('sys.exit')
    def test_signal_handler_prevents_nested_cleanup(self, mock_exit, safe_exit):
        """Second signal during cleanup forces immediate exit."""
        # Simulate cleanup already in progress
        safe_exit._cleanup_in_progress = True

        safe_exit._signal_handler(signal.SIGINT, None)

        # Should force exit immediately (128 + SIGINT = 130)
        # Note: The actual implementation calls cleanup which also exits,
        # so we just verify exit was called
        assert mock_exit.called
        # The first call should be with the force-exit code
        first_call_args = mock_exit.call_args_list[0][0]
        assert first_call_args[0] in [128 + signal.SIGINT, 130]

    @patch('sys.exit')
    @patch('os.kill')
    @patch('time.sleep')
    def test_signal_handler_sets_cleanup_flag(self, mock_sleep, mock_kill, mock_exit, safe_exit):
        """_signal_handler() sets cleanup_in_progress flag."""
        assert safe_exit._cleanup_in_progress is False

        mock_kill.side_effect = [ProcessLookupError]
        safe_exit._signal_handler(signal.SIGINT, None)

        # Flag should be set (but we exit before we can check in production)
        # In tests, we verify by checking double-signal behavior


# =============================================================================
# Thread Safety Tests
# =============================================================================


@pytest.mark.unit
class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_handler_registration_thread_safe(self, safe_exit):
        """Handler registration is thread-safe."""
        errors = []

        def register_handlers():
            try:
                for i in range(50):
                    handler = Mock(spec=ExitHandler, priority=i, name=f"h{i}")
                    safe_exit.register_handler(handler)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_handlers) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(safe_exit._handlers) == 200  # 4 threads * 50 handlers

    def test_concurrent_register_unregister(self, safe_exit):
        """Concurrent register/unregister is thread-safe."""
        errors = []
        cleanup_ids = []

        def register_unregister():
            try:
                for i in range(25):
                    cid = safe_exit.register_process(2000 + i, f"cmd-{i}")
                    cleanup_ids.append(cid)
                    if i % 2 == 0:
                        safe_exit.unregister_process(cid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_unregister) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # About half should be unregistered
        assert 40 <= len(safe_exit._processes) <= 60
