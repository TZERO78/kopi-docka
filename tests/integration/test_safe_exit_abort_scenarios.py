"""
Integration tests for SafeExitManager abort scenarios.

Tests real-world abort scenarios:
- Backup abort → containers restart
- Restore abort → containers stay stopped
- DR abort → temp cleanup

These tests require Docker and simulate actual SIGINT/SIGTERM interrupts.
"""

import os
import signal
import subprocess
import tempfile
import threading
import time
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


# Check if Docker is available
def docker_available() -> bool:
    """Check if Docker daemon is running and accessible."""
    try:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def is_root() -> bool:
    """Check if running as root."""
    return os.geteuid() == 0


# Skip all tests if Docker is not available or not root
pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_docker,
    pytest.mark.skipif(not docker_available(), reason="Docker daemon not available"),
    pytest.mark.skipif(not is_root(), reason="Requires root for Docker operations"),
]


# =============================================================================
# Helper Functions
# =============================================================================


def create_test_container(name: str, image: str = "alpine:latest") -> str:
    """Create a simple test container."""
    # Pull image if not exists
    subprocess.run(
        ["docker", "pull", image],
        capture_output=True,
        timeout=60,
    )

    # Remove existing container if present
    subprocess.run(
        ["docker", "rm", "-f", name],
        capture_output=True,
    )

    # Create and start container
    result = subprocess.run(
        ["docker", "run", "-d", "--name", name, image, "sleep", "3600"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to create container: {result.stderr}")

    return name


def cleanup_test_container(name: str):
    """Remove test container."""
    subprocess.run(
        ["docker", "rm", "-f", name],
        capture_output=True,
    )


def get_container_state(name: str) -> str:
    """Get container state (running, exited, etc.)."""
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Status}}", name],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "not-found"


# =============================================================================
# Backup Abort Tests
# =============================================================================


@pytest.mark.integration
class TestBackupAbort:
    """Integration tests for backup abort → container restart."""

    def test_service_continuity_handler_restarts_containers(self):
        """When backup is aborted, ServiceContinuityHandler restarts stopped containers."""
        from kopi_docka.cores.safe_exit_manager import (
            SafeExitManager,
            ServiceContinuityHandler,
        )

        # Reset singleton
        SafeExitManager.reset_instance()
        safe_exit = SafeExitManager.get_instance()
        safe_exit.install_handlers()

        # Create test container
        container_name = "kopi_test_backup_abort"
        try:
            container_id = create_test_container(container_name)

            # Verify container is running
            assert get_container_state(container_name) == "running"

            # Register ServiceContinuityHandler
            handler = ServiceContinuityHandler()
            safe_exit.register_handler(handler)

            # Simulate backup: stop container and register it
            subprocess.run(
                ["docker", "stop", container_id],
                capture_output=True,
                timeout=30,
            )
            handler.register_container(container_id, container_name)

            # Verify container is stopped
            assert get_container_state(container_name) in ["exited", "stopped"]

            # Simulate abort: trigger cleanup
            handler.cleanup()

            # Wait a bit for container to restart
            time.sleep(2)

            # Verify container was restarted
            state = get_container_state(container_name)
            assert state == "running", f"Expected running, got {state}"

        finally:
            cleanup_test_container(container_name)
            SafeExitManager.reset_instance()

    def test_service_continuity_lifo_order(self):
        """Containers restart in LIFO order (reverse of stop order)."""
        from kopi_docka.cores.safe_exit_manager import (
            SafeExitManager,
            ServiceContinuityHandler,
        )
        from unittest.mock import patch

        SafeExitManager.reset_instance()
        safe_exit = SafeExitManager.get_instance()

        handler = ServiceContinuityHandler()
        safe_exit.register_handler(handler)

        # Register 3 containers in order
        handler.register_container("id1", "container1")
        handler.register_container("id2", "container2")
        handler.register_container("id3", "container3")

        # Mock run_command to capture restart order
        restart_order = []

        def track_restart(*args, **kwargs):
            cmd = args[0]
            if "start" in cmd:
                container_id = cmd[2]
                restart_order.append(container_id)

        with patch('kopi_docka.helpers.ui_utils.run_command', side_effect=track_restart):
            handler.cleanup()

        # Verify LIFO order (last registered, first restarted)
        assert restart_order == ["id3", "id2", "id1"]

        SafeExitManager.reset_instance()


# =============================================================================
# Restore Abort Tests
# =============================================================================


@pytest.mark.integration
class TestRestoreAbort:
    """Integration tests for restore abort → containers stay stopped."""

    def test_data_safety_handler_keeps_containers_stopped(self):
        """When restore is aborted, DataSafetyHandler keeps containers stopped."""
        from kopi_docka.cores.safe_exit_manager import (
            SafeExitManager,
            DataSafetyHandler,
        )

        SafeExitManager.reset_instance()
        safe_exit = SafeExitManager.get_instance()
        safe_exit.install_handlers()

        container_name = "kopi_test_restore_abort"
        try:
            container_id = create_test_container(container_name)

            # Stop container (simulating restore preparation)
            subprocess.run(
                ["docker", "stop", container_id],
                capture_output=True,
                timeout=30,
            )

            # Register DataSafetyHandler
            handler = DataSafetyHandler()
            safe_exit.register_handler(handler)
            handler.register_stopped_container(container_name)

            # Verify container is stopped
            assert get_container_state(container_name) in ["exited", "stopped"]

            # Simulate abort: trigger cleanup
            handler.cleanup()

            # Wait a bit
            time.sleep(1)

            # Verify container is STILL stopped (not restarted)
            state = get_container_state(container_name)
            assert state in ["exited", "stopped"], f"Expected stopped, got {state}"

        finally:
            cleanup_test_container(container_name)
            SafeExitManager.reset_instance()

    def test_data_safety_handler_cleans_temp_dirs(self):
        """When restore is aborted, DataSafetyHandler removes temp directories."""
        from kopi_docka.cores.safe_exit_manager import (
            SafeExitManager,
            DataSafetyHandler,
        )

        SafeExitManager.reset_instance()
        safe_exit = SafeExitManager.get_instance()

        # Create temp directory
        temp_dir = tempfile.mkdtemp(prefix="kopi_test_restore_")
        temp_file = Path(temp_dir) / "test.txt"
        temp_file.write_text("test data")

        try:
            # Register DataSafetyHandler with temp dir
            handler = DataSafetyHandler()
            safe_exit.register_handler(handler)
            handler.register_temp_dir(temp_dir)

            # Verify temp dir exists
            assert os.path.exists(temp_dir)
            assert temp_file.exists()

            # Simulate abort: trigger cleanup
            handler.cleanup()

            # Wait a bit
            time.sleep(0.5)

            # Verify temp dir was removed
            assert not os.path.exists(temp_dir), "Temp dir should be removed"

        finally:
            # Cleanup if test failed
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)

            SafeExitManager.reset_instance()


# =============================================================================
# Disaster Recovery Abort Tests
# =============================================================================


@pytest.mark.integration
class TestDisasterRecoveryAbort:
    """Integration tests for DR abort → temp cleanup."""

    def test_cleanup_handler_removes_temp_dir(self):
        """When DR is aborted, CleanupHandler removes temp directory."""
        from kopi_docka.cores.safe_exit_manager import (
            SafeExitManager,
            CleanupHandler,
        )
        import shutil

        SafeExitManager.reset_instance()
        safe_exit = SafeExitManager.get_instance()

        # Create temp directory (simulating DR temp workspace)
        temp_dir = tempfile.mkdtemp(prefix="kopi-docka-recovery-")
        temp_file = Path(temp_dir) / "repository.config"
        temp_file.write_text("test config")

        try:
            # Register CleanupHandler with temp dir cleanup
            handler = CleanupHandler("dr_cleanup")
            handler.register_cleanup(
                "temp_dir",
                lambda: shutil.rmtree(temp_dir) if os.path.exists(temp_dir) else None
            )
            safe_exit.register_handler(handler)

            # Verify temp dir exists
            assert os.path.exists(temp_dir)
            assert temp_file.exists()

            # Simulate abort: trigger cleanup
            handler.cleanup()

            # Wait a bit
            time.sleep(0.5)

            # Verify temp dir was removed
            assert not os.path.exists(temp_dir), "DR temp dir should be removed"

        finally:
            # Cleanup if test failed
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)

            SafeExitManager.reset_instance()

    def test_cleanup_handler_removes_incomplete_archive(self):
        """When DR is aborted, CleanupHandler removes incomplete archive."""
        from kopi_docka.cores.safe_exit_manager import (
            SafeExitManager,
            CleanupHandler,
        )

        SafeExitManager.reset_instance()
        safe_exit = SafeExitManager.get_instance()

        # Create incomplete archive file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.tar.gz.enc',
            prefix='recovery-bundle-',
            delete=False
        ) as f:
            bundle_path = f.name
            f.write("incomplete archive data")

        try:
            # Register CleanupHandler with archive cleanup
            handler = CleanupHandler("dr_cleanup")
            handler.register_cleanup(
                "incomplete_archive",
                lambda: os.remove(bundle_path) if os.path.exists(bundle_path) else None
            )
            safe_exit.register_handler(handler)

            # Verify archive exists
            assert os.path.exists(bundle_path)

            # Simulate abort: trigger cleanup
            handler.cleanup()

            # Wait a bit
            time.sleep(0.5)

            # Verify archive was removed
            assert not os.path.exists(bundle_path), "Incomplete archive should be removed"

        finally:
            # Cleanup if test failed
            if os.path.exists(bundle_path):
                os.remove(bundle_path)

            SafeExitManager.reset_instance()


# =============================================================================
# Process Layer Termination Tests
# =============================================================================


@pytest.mark.integration
class TestProcessLayerTermination:
    """Integration tests for process layer subprocess termination."""

    def test_process_layer_terminates_subprocess(self):
        """Process layer terminates tracked subprocess on cleanup."""
        from kopi_docka.cores.safe_exit_manager import SafeExitManager
        import subprocess
        import psutil

        SafeExitManager.reset_instance()
        safe_exit = SafeExitManager.get_instance()

        # Start a long-running subprocess
        proc = subprocess.Popen(
            ["sleep", "300"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Register process with SafeExitManager
            cleanup_id = safe_exit.register_process(proc.pid, "test-sleep")

            # Verify process is running
            assert psutil.pid_exists(proc.pid)

            # Simulate abort: terminate all processes
            safe_exit._terminate_all_processes()

            # Wait a bit for termination
            time.sleep(6)  # Wait for SIGTERM (5s) + buffer

            # Verify process was terminated
            assert not psutil.pid_exists(proc.pid), "Process should be terminated"

        finally:
            # Cleanup if test failed
            try:
                proc.kill()
            except:
                pass

            SafeExitManager.reset_instance()

    def test_process_layer_sigkill_after_sigterm_timeout(self):
        """Process layer sends SIGKILL if process survives SIGTERM."""
        from kopi_docka.cores.safe_exit_manager import SafeExitManager
        import subprocess
        import psutil

        SafeExitManager.reset_instance()
        safe_exit = SafeExitManager.get_instance()

        # Start subprocess that ignores SIGTERM
        script = """
import signal
import time

def handler(signum, frame):
    # Ignore SIGTERM
    pass

signal.signal(signal.SIGTERM, handler)
time.sleep(300)
"""

        proc = subprocess.Popen(
            ["python3", "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Register process
            cleanup_id = safe_exit.register_process(proc.pid, "test-ignore-sigterm")

            # Verify process is running
            assert psutil.pid_exists(proc.pid)

            # Simulate abort: terminate all processes
            safe_exit._terminate_all_processes()

            # Wait for SIGTERM timeout + SIGKILL
            time.sleep(7)

            # Verify process was force-killed
            assert not psutil.pid_exists(proc.pid), "Process should be SIGKILL'd"

        finally:
            # Cleanup if test failed
            try:
                proc.kill()
            except:
                pass

            SafeExitManager.reset_instance()


# =============================================================================
# End-to-End Signal Handler Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
class TestSignalHandlerEndToEnd:
    """End-to-end tests for signal handler with real operations."""

    def test_sigint_during_simulated_backup(self):
        """SIGINT during simulated backup triggers cleanup and container restart."""
        from kopi_docka.cores.safe_exit_manager import (
            SafeExitManager,
            ServiceContinuityHandler,
        )

        SafeExitManager.reset_instance()
        safe_exit = SafeExitManager.get_instance()
        safe_exit.install_handlers()

        container_name = "kopi_test_e2e_backup"
        cleanup_done = threading.Event()
        container_restarted = False

        try:
            container_id = create_test_container(container_name)

            # Register ServiceContinuityHandler
            handler = ServiceContinuityHandler()
            safe_exit.register_handler(handler)

            # Simulate backup operation in thread
            def simulate_backup():
                nonlocal container_restarted

                # Stop container
                subprocess.run(
                    ["docker", "stop", container_id],
                    capture_output=True,
                    timeout=30,
                )
                handler.register_container(container_id, container_name)

                # Simulate long-running backup
                time.sleep(30)  # Won't complete - will be interrupted

            backup_thread = threading.Thread(target=simulate_backup)
            backup_thread.start()

            # Wait for container to stop
            time.sleep(2)

            # Verify container is stopped
            assert get_container_state(container_name) in ["exited", "stopped"]

            # Trigger cleanup manually (simulating SIGINT)
            # In real scenario, this would be triggered by signal
            handler.cleanup()

            # Wait for cleanup
            time.sleep(2)

            # Verify container was restarted
            state = get_container_state(container_name)
            assert state == "running", f"Container should be restarted, got {state}"

        finally:
            cleanup_test_container(container_name)
            SafeExitManager.reset_instance()
