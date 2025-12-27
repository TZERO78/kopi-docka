"""
Integration tests for hook script execution.

These tests create real hook scripts and verify they execute correctly
during backup/restore operations with actual side effects.

Requires Docker to be running.
"""

import os
import subprocess
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch


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


# Check if running as root
def is_root() -> bool:
    """Check if running as root."""
    return os.geteuid() == 0


pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_docker,
    pytest.mark.skipif(not docker_available(), reason="Docker daemon not available"),
]


@pytest.mark.integration
class TestHookScriptExecution:
    """Integration tests for hook script execution during backup/restore."""

    @pytest.fixture
    def hook_environment(self, tmp_path):
        """Create test environment with hook scripts and test volume."""
        if not is_root():
            pytest.skip("Requires root for backup/restore operations")

        # Create hook output directory
        hook_output_dir = tmp_path / "hook_output"
        hook_output_dir.mkdir()

        # Create hook scripts directory
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        # Create pre-backup hook script
        pre_backup_script = hooks_dir / "pre-backup.sh"
        pre_backup_script.write_text(
            f"""#!/bin/bash
set -e
echo "Pre-backup hook started" > {hook_output_dir}/pre-backup.log
echo "Hook type: $KOPI_DOCKA_HOOK_TYPE" >> {hook_output_dir}/pre-backup.log
echo "Unit name: $KOPI_DOCKA_UNIT_NAME" >> {hook_output_dir}/pre-backup.log
echo "$(date -Iseconds)" >> {hook_output_dir}/pre-backup.log
touch {hook_output_dir}/pre-backup-executed
exit 0
"""
        )
        pre_backup_script.chmod(0o755)

        # Create post-backup hook script
        post_backup_script = hooks_dir / "post-backup.sh"
        post_backup_script.write_text(
            f"""#!/bin/bash
set -e
echo "Post-backup hook started" > {hook_output_dir}/post-backup.log
echo "Hook type: $KOPI_DOCKA_HOOK_TYPE" >> {hook_output_dir}/post-backup.log
echo "Unit name: $KOPI_DOCKA_UNIT_NAME" >> {hook_output_dir}/post-backup.log
echo "$(date -Iseconds)" >> {hook_output_dir}/post-backup.log
touch {hook_output_dir}/post-backup-executed
exit 0
"""
        )
        post_backup_script.chmod(0o755)

        # Create pre-restore hook script
        pre_restore_script = hooks_dir / "pre-restore.sh"
        pre_restore_script.write_text(
            f"""#!/bin/bash
set -e
echo "Pre-restore hook started" > {hook_output_dir}/pre-restore.log
echo "Hook type: $KOPI_DOCKA_HOOK_TYPE" >> {hook_output_dir}/pre-restore.log
echo "Unit name: $KOPI_DOCKA_UNIT_NAME" >> {hook_output_dir}/pre-restore.log
echo "$(date -Iseconds)" >> {hook_output_dir}/pre-restore.log
touch {hook_output_dir}/pre-restore-executed
exit 0
"""
        )
        pre_restore_script.chmod(0o755)

        # Create post-restore hook script
        post_restore_script = hooks_dir / "post-restore.sh"
        post_restore_script.write_text(
            f"""#!/bin/bash
set -e
echo "Post-restore hook started" > {hook_output_dir}/post-restore.log
echo "Hook type: $KOPI_DOCKA_HOOK_TYPE" >> {hook_output_dir}/post-restore.log
echo "Unit name: $KOPI_DOCKA_UNIT_NAME" >> {hook_output_dir}/post-restore.log
echo "$(date -Iseconds)" >> {hook_output_dir}/post-restore.log
touch {hook_output_dir}/post-restore-executed
exit 0
"""
        )
        post_restore_script.chmod(0o755)

        # Create failing hook for testing error handling
        failing_hook_script = hooks_dir / "failing-hook.sh"
        failing_hook_script.write_text(
            f"""#!/bin/bash
echo "Failing hook executed" > {hook_output_dir}/failing-hook.log
echo "This hook will fail with exit code 1"
exit 1
"""
        )
        failing_hook_script.chmod(0o755)

        # Create test volume with data
        vol_name = f"kopi_hook_test_{os.getpid()}"
        subprocess.run(
            ["docker", "volume", "create", vol_name],
            capture_output=True,
            check=True,
        )

        # Write test data
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{vol_name}:/data",
                "alpine:latest",
                "sh",
                "-c",
                "echo 'hook test data' > /data/test.txt",
            ],
            capture_output=True,
            check=True,
        )

        yield {
            "hooks_dir": hooks_dir,
            "output_dir": hook_output_dir,
            "pre_backup_script": pre_backup_script,
            "post_backup_script": post_backup_script,
            "pre_restore_script": pre_restore_script,
            "post_restore_script": post_restore_script,
            "failing_hook_script": failing_hook_script,
            "vol_name": vol_name,
            "tmp_path": tmp_path,
        }

        # Cleanup
        subprocess.run(["docker", "volume", "rm", "-f", vol_name], capture_output=True)

    def test_hooks_execute_during_backup(self, hook_environment):
        """Test that pre/post backup hooks execute during backup operation."""
        from kopi_docka.cores.hooks_manager import HooksManager
        from kopi_docka.helpers.config import Config

        output_dir = hook_environment["output_dir"]

        # Create config with hook paths
        config = Mock(spec=Config)
        config.get = Mock(
            side_effect=lambda section, key, fallback=None: {
                "pre_backup": str(hook_environment["pre_backup_script"]),
                "post_backup": str(hook_environment["post_backup_script"]),
            }.get(key, fallback)
        )

        # Initialize hooks manager
        hooks_mgr = HooksManager(config)

        # Execute pre-backup hook
        print("\n=== Executing Pre-Backup Hook ===")
        success = hooks_mgr.execute_hook("pre_backup", unit_name="test_unit")
        assert success is True, "Pre-backup hook should succeed"

        # Verify pre-backup hook executed
        assert (output_dir / "pre-backup-executed").exists(), "Pre-backup marker file missing"
        assert (output_dir / "pre-backup.log").exists(), "Pre-backup log file missing"

        pre_backup_log = (output_dir / "pre-backup.log").read_text()
        assert "Pre-backup hook started" in pre_backup_log
        assert "pre_backup" in pre_backup_log
        assert "test_unit" in pre_backup_log

        # Execute post-backup hook
        print("\n=== Executing Post-Backup Hook ===")
        success = hooks_mgr.execute_hook("post_backup", unit_name="test_unit")
        assert success is True, "Post-backup hook should succeed"

        # Verify post-backup hook executed
        assert (output_dir / "post-backup-executed").exists(), "Post-backup marker file missing"
        assert (output_dir / "post-backup.log").exists(), "Post-backup log file missing"

        post_backup_log = (output_dir / "post-backup.log").read_text()
        assert "Post-backup hook started" in post_backup_log
        assert "post_backup" in post_backup_log
        assert "test_unit" in post_backup_log

        # Verify hook tracking
        executed = hooks_mgr.get_executed_hooks()
        assert len(executed) == 2
        assert any("pre-backup.sh" in hook for hook in executed)
        assert any("post-backup.sh" in hook for hook in executed)

        print("✓ Pre/Post backup hooks executed successfully")

    def test_hooks_execute_during_restore(self, hook_environment):
        """Test that pre/post restore hooks execute during restore operation."""
        from kopi_docka.cores.hooks_manager import HooksManager
        from kopi_docka.helpers.config import Config

        output_dir = hook_environment["output_dir"]

        # Create config with restore hook paths
        config = Mock(spec=Config)
        config.get = Mock(
            side_effect=lambda section, key, fallback=None: {
                "pre_restore": str(hook_environment["pre_restore_script"]),
                "post_restore": str(hook_environment["post_restore_script"]),
            }.get(key, fallback)
        )

        hooks_mgr = HooksManager(config)

        # Execute pre-restore hook
        print("\n=== Executing Pre-Restore Hook ===")
        success = hooks_mgr.execute_hook("pre_restore", unit_name="restore_unit")
        assert success is True

        # Verify execution
        assert (output_dir / "pre-restore-executed").exists()
        pre_restore_log = (output_dir / "pre-restore.log").read_text()
        assert "Pre-restore hook started" in pre_restore_log
        assert "pre_restore" in pre_restore_log
        assert "restore_unit" in pre_restore_log

        # Execute post-restore hook
        print("\n=== Executing Post-Restore Hook ===")
        success = hooks_mgr.execute_hook("post_restore", unit_name="restore_unit")
        assert success is True

        # Verify execution
        assert (output_dir / "post-restore-executed").exists()
        post_restore_log = (output_dir / "post-restore.log").read_text()
        assert "Post-restore hook started" in post_restore_log
        assert "post_restore" in post_restore_log

        print("✓ Pre/Post restore hooks executed successfully")

    def test_hook_failure_handling(self, hook_environment):
        """Test that failing hooks are properly handled."""
        from kopi_docka.cores.hooks_manager import HooksManager
        from kopi_docka.helpers.config import Config

        output_dir = hook_environment["output_dir"]

        # Create config with failing hook
        config = Mock(spec=Config)
        config.get = Mock(
            side_effect=lambda section, key, fallback=None: {
                "pre_backup": str(hook_environment["failing_hook_script"]),
            }.get(key, fallback)
        )

        hooks_mgr = HooksManager(config)

        # Execute failing hook
        print("\n=== Testing Failing Hook ===")
        success = hooks_mgr.execute_hook("pre_backup", unit_name="test_unit")

        # Should return False for failed hook
        assert success is False, "Failing hook should return False"

        # Verify hook was attempted
        assert (output_dir / "failing-hook.log").exists()

        print("✓ Failing hook properly handled")

    def test_hook_with_missing_script(self, hook_environment):
        """Test behavior when hook script doesn't exist."""
        from kopi_docka.cores.hooks_manager import HooksManager
        from kopi_docka.helpers.config import Config

        # Create config pointing to non-existent script
        config = Mock(spec=Config)
        config.get = Mock(
            side_effect=lambda section, key, fallback=None: {
                "pre_backup": "/nonexistent/hook.sh",
            }.get(key, fallback)
        )

        hooks_mgr = HooksManager(config)

        # Should return False when script not found
        success = hooks_mgr.execute_hook("pre_backup")
        assert success is False

        print("✓ Missing hook script properly handled")

    def test_hook_with_non_executable_script(self, hook_environment):
        """Test behavior when hook script is not executable."""
        from kopi_docka.cores.hooks_manager import HooksManager
        from kopi_docka.helpers.config import Config

        # Create non-executable script
        non_exec_script = hook_environment["hooks_dir"] / "non-exec.sh"
        non_exec_script.write_text("#!/bin/bash\necho 'test'\n")
        non_exec_script.chmod(0o644)  # Not executable

        config = Mock(spec=Config)
        config.get = Mock(
            side_effect=lambda section, key, fallback=None: {
                "pre_backup": str(non_exec_script),
            }.get(key, fallback)
        )

        hooks_mgr = HooksManager(config)

        # Should return False when script not executable
        success = hooks_mgr.execute_hook("pre_backup")
        assert success is False

        print("✓ Non-executable hook script properly handled")

    def test_hook_environment_variables(self, hook_environment):
        """Test that hooks receive correct environment variables."""
        from kopi_docka.cores.hooks_manager import HooksManager
        from kopi_docka.helpers.config import Config

        output_dir = hook_environment["output_dir"]

        # Create hook that dumps environment
        env_hook = hook_environment["hooks_dir"] / "env-hook.sh"
        env_hook.write_text(
            f"""#!/bin/bash
echo "KOPI_DOCKA_HOOK_TYPE=$KOPI_DOCKA_HOOK_TYPE" > {output_dir}/env-vars.log
echo "KOPI_DOCKA_UNIT_NAME=$KOPI_DOCKA_UNIT_NAME" >> {output_dir}/env-vars.log
exit 0
"""
        )
        env_hook.chmod(0o755)

        config = Mock(spec=Config)
        config.get = Mock(
            side_effect=lambda section, key, fallback=None: {
                "pre_backup": str(env_hook),
            }.get(key, fallback)
        )

        hooks_mgr = HooksManager(config)

        # Execute with specific unit name
        success = hooks_mgr.execute_hook("pre_backup", unit_name="my_test_unit")
        assert success is True

        # Verify environment variables were set
        env_log = (output_dir / "env-vars.log").read_text()
        assert "KOPI_DOCKA_HOOK_TYPE=pre_backup" in env_log
        assert "KOPI_DOCKA_UNIT_NAME=my_test_unit" in env_log

        print("✓ Hook environment variables correctly set")

    def test_hook_timeout_handling(self, hook_environment):
        """Test that long-running hooks time out properly."""
        from kopi_docka.cores.hooks_manager import HooksManager
        from kopi_docka.helpers.config import Config

        # Create slow hook
        slow_hook = hook_environment["hooks_dir"] / "slow-hook.sh"
        slow_hook.write_text(
            """#!/bin/bash
echo "Starting slow hook"
sleep 10
echo "This should not be reached"
exit 0
"""
        )
        slow_hook.chmod(0o755)

        config = Mock(spec=Config)
        config.get = Mock(
            side_effect=lambda section, key, fallback=None: {
                "pre_backup": str(slow_hook),
            }.get(key, fallback)
        )

        hooks_mgr = HooksManager(config)

        # Execute with short timeout
        print("\n=== Testing Hook Timeout ===")
        success = hooks_mgr.execute_hook("pre_backup", timeout=2)

        # Should return False on timeout
        assert success is False, "Timed out hook should return False"

        print("✓ Hook timeout properly handled")

    def test_hook_execution_order(self, hook_environment):
        """Test that hooks execute in correct order and track execution."""
        from kopi_docka.cores.hooks_manager import HooksManager
        from kopi_docka.helpers.config import Config

        output_dir = hook_environment["output_dir"]

        # Create ordered execution tracking file
        tracking_file = output_dir / "execution-order.log"

        # Create hooks that append to tracking file
        for hook_name in ["pre_backup", "post_backup", "pre_restore", "post_restore"]:
            hook_script = hook_environment["hooks_dir"] / f"{hook_name}-ordered.sh"
            hook_script.write_text(
                f"""#!/bin/bash
echo "{hook_name}" >> {tracking_file}
exit 0
"""
            )
            hook_script.chmod(0o755)

        config = Mock(spec=Config)
        config.get = Mock(
            side_effect=lambda section, key, fallback=None: {
                "pre_backup": str(hook_environment["hooks_dir"] / "pre_backup-ordered.sh"),
                "post_backup": str(hook_environment["hooks_dir"] / "post_backup-ordered.sh"),
                "pre_restore": str(hook_environment["hooks_dir"] / "pre_restore-ordered.sh"),
                "post_restore": str(hook_environment["hooks_dir"] / "post_restore-ordered.sh"),
            }.get(key, fallback)
        )

        hooks_mgr = HooksManager(config)

        # Execute in order
        print("\n=== Testing Hook Execution Order ===")
        hooks_mgr.execute_hook("pre_backup")
        hooks_mgr.execute_hook("post_backup")
        hooks_mgr.execute_hook("pre_restore")
        hooks_mgr.execute_hook("post_restore")

        # Verify order
        execution_log = tracking_file.read_text().strip().split("\n")
        assert execution_log == [
            "pre_backup",
            "post_backup",
            "pre_restore",
            "post_restore",
        ]

        # Verify all hooks were tracked
        executed = hooks_mgr.get_executed_hooks()
        assert len(executed) == 4

        print("✓ Hooks executed in correct order")

    def test_no_hook_configured(self, hook_environment):
        """Test that operations succeed when no hooks are configured."""
        from kopi_docka.cores.hooks_manager import HooksManager
        from kopi_docka.helpers.config import Config

        # Create config with no hooks
        config = Mock(spec=Config)
        config.get = Mock(return_value=None)

        hooks_mgr = HooksManager(config)

        # Should return True (success) when no hook configured
        success = hooks_mgr.execute_hook("pre_backup")
        assert success is True

        # No hooks should be tracked
        executed = hooks_mgr.get_executed_hooks()
        assert len(executed) == 0

        print("✓ No-hook scenario handled correctly")


@pytest.mark.integration
@pytest.mark.slow
class TestHooksWithRealBackup:
    """Test hooks integrated with actual backup operations."""

    @pytest.fixture
    def backup_with_hooks_environment(self, tmp_path):
        """Set up complete environment for backup with hooks."""
        if not is_root():
            pytest.skip("Requires root for backup operations")

        # Create hook tracking directory
        hook_tracking = tmp_path / "hook_tracking"
        hook_tracking.mkdir()

        # Create maintenance mode simulation script
        maintenance_script = tmp_path / "maintenance-mode.sh"
        maintenance_script.write_text(
            f"""#!/bin/bash
if [ "$KOPI_DOCKA_HOOK_TYPE" = "pre_backup" ]; then
    echo "Enabling maintenance mode for $KOPI_DOCKA_UNIT_NAME" > {hook_tracking}/maintenance.log
    touch {hook_tracking}/maintenance-enabled
elif [ "$KOPI_DOCKA_HOOK_TYPE" = "post_backup" ]; then
    echo "Disabling maintenance mode for $KOPI_DOCKA_UNIT_NAME" >> {hook_tracking}/maintenance.log
    rm -f {hook_tracking}/maintenance-enabled
    touch {hook_tracking}/maintenance-disabled
fi
exit 0
"""
        )
        maintenance_script.chmod(0o755)

        # Create test volume
        vol_name = f"kopi_hook_backup_test_{os.getpid()}"
        subprocess.run(
            ["docker", "volume", "create", vol_name],
            capture_output=True,
            check=True,
        )

        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{vol_name}:/data",
                "alpine:latest",
                "sh",
                "-c",
                "echo 'backup with hooks' > /data/test.txt",
            ],
            capture_output=True,
            check=True,
        )

        yield {
            "maintenance_script": maintenance_script,
            "hook_tracking": hook_tracking,
            "vol_name": vol_name,
            "tmp_path": tmp_path,
        }

        # Cleanup
        subprocess.run(["docker", "volume", "rm", "-f", vol_name], capture_output=True)

    def test_backup_with_maintenance_mode_hooks(self, backup_with_hooks_environment):
        """Test realistic scenario with maintenance mode hooks during backup."""
        from kopi_docka.cores.hooks_manager import HooksManager
        from kopi_docka.helpers.config import Config

        hook_tracking = backup_with_hooks_environment["hook_tracking"]
        maintenance_script = backup_with_hooks_environment["maintenance_script"]

        # Create config
        config = Mock(spec=Config)
        config.get = Mock(
            side_effect=lambda section, key, fallback=None: {
                "pre_backup": str(maintenance_script),
                "post_backup": str(maintenance_script),
            }.get(key, fallback)
        )

        hooks_mgr = HooksManager(config)

        # Simulate backup workflow
        print("\n=== Simulating Backup with Maintenance Mode ===")

        # Pre-backup: Enable maintenance mode
        success = hooks_mgr.execute_hook("pre_backup", unit_name="nextcloud")
        assert success is True
        assert (hook_tracking / "maintenance-enabled").exists()
        print("✓ Maintenance mode enabled")

        # Simulate backup happening here...
        print("  [Backup operations would happen here]")

        # Post-backup: Disable maintenance mode
        success = hooks_mgr.execute_hook("post_backup", unit_name="nextcloud")
        assert success is True
        assert not (hook_tracking / "maintenance-enabled").exists()
        assert (hook_tracking / "maintenance-disabled").exists()
        print("✓ Maintenance mode disabled")

        # Verify log
        maintenance_log = (hook_tracking / "maintenance.log").read_text()
        assert "Enabling maintenance mode" in maintenance_log
        assert "Disabling maintenance mode" in maintenance_log
        assert "nextcloud" in maintenance_log

        print("\n=== ✅ MAINTENANCE MODE HOOK TEST COMPLETE ===")
