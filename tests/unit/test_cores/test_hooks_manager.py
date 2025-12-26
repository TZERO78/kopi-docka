"""
Unit tests for HooksManager class.

Tests hook script execution, error handling, timeout behavior,
environment variables, and executed hooks tracking.
"""

import os
import pytest
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

from kopi_docka.cores.hooks_manager import HooksManager
from kopi_docka.helpers.constants import (
    HOOK_PRE_BACKUP,
    HOOK_POST_BACKUP,
    HOOK_PRE_RESTORE,
    HOOK_POST_RESTORE,
)


def make_mock_config(hook_script: str = None) -> Mock:
    """Create a mock Config object for hooks testing."""
    config = Mock()

    def get_side_effect(section, key, fallback=None):
        if section == "backup.hooks" and key and hook_script:
            return hook_script
        return fallback

    config.get.side_effect = get_side_effect
    return config


# =============================================================================
# Hook Execution Success Tests
# =============================================================================


@pytest.mark.unit
class TestHookExecution:
    """Tests for successful hook execution."""

    def test_execute_hook_success(self, tmp_path):
        """Hook executes successfully and returns True."""
        # Create executable hook script
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")

            result = manager.execute_hook(HOOK_PRE_BACKUP, "testunit")

        assert result is True
        mock_run.assert_called_once()

    def test_execute_hook_with_output(self, tmp_path):
        """Hook execution captures stdout and stderr."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\necho 'Hook output'\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout="Hook output\n", stderr=""
            )

            result = manager.execute_hook(HOOK_PRE_BACKUP)

        assert result is True
        # Verify subprocess.run was called with capture_output=True
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["capture_output"] is True
        assert call_kwargs["text"] is True

    def test_no_hook_configured_returns_true(self, tmp_path):
        """When no hook is configured, execution returns True."""
        config = make_mock_config(hook_script=None)
        manager = HooksManager(config)

        result = manager.execute_hook(HOOK_PRE_BACKUP)

        assert result is True

    def test_hook_nonzero_exit_returns_false(self, tmp_path):
        """Hook with non-zero exit code returns False."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 1\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1, stdout="", stderr="Error occurred"
            )

            result = manager.execute_hook(HOOK_PRE_BACKUP)

        assert result is False


# =============================================================================
# Hook Script Validation Tests
# =============================================================================


@pytest.mark.unit
class TestHookScriptValidation:
    """Tests for hook script validation (existence, permissions)."""

    def test_hook_script_not_found(self, tmp_path):
        """Hook script that doesn't exist returns False."""
        nonexistent_script = tmp_path / "nonexistent.sh"

        config = make_mock_config(str(nonexistent_script))
        manager = HooksManager(config)

        result = manager.execute_hook(HOOK_PRE_BACKUP)

        assert result is False

    def test_hook_script_not_executable(self, tmp_path):
        """Hook script without execute permission returns False."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        # Don't set executable permission

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        result = manager.execute_hook(HOOK_PRE_BACKUP)

        assert result is False

    def test_hook_script_path_expansion(self, tmp_path):
        """Hook script path with ~ is expanded."""
        # Mock expanduser to return our tmp_path
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config("~/test-hook.sh")
        manager = HooksManager(config)

        with patch("pathlib.Path.expanduser", return_value=hook_script):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

                result = manager.execute_hook(HOOK_PRE_BACKUP)

        assert result is True


# =============================================================================
# Hook Timeout Tests
# =============================================================================


@pytest.mark.unit
class TestHookTimeout:
    """Tests for hook timeout handling."""

    def test_hook_timeout_returns_false(self, tmp_path):
        """Hook that times out returns False."""
        hook_script = tmp_path / "slow-hook.sh"
        hook_script.write_text("#!/bin/bash\nsleep 10\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=str(hook_script), timeout=1
            )

            result = manager.execute_hook(HOOK_PRE_BACKUP, timeout=1)

        assert result is False

    def test_hook_custom_timeout(self, tmp_path):
        """Hook respects custom timeout parameter."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            manager.execute_hook(HOOK_PRE_BACKUP, timeout=60)

        # Verify timeout was passed to subprocess.run
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 60

    def test_hook_default_timeout(self, tmp_path):
        """Hook uses default timeout of 300s when not specified."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            manager.execute_hook(HOOK_PRE_BACKUP)

        # Verify default timeout
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 300


# =============================================================================
# Environment Variables Tests
# =============================================================================


@pytest.mark.unit
class TestHookEnvironmentVariables:
    """Tests for environment variables passed to hooks."""

    def test_hook_receives_hook_type_env(self, tmp_path):
        """Hook receives KOPI_DOCKA_HOOK_TYPE environment variable."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            manager.execute_hook(HOOK_PRE_BACKUP)

        # Verify environment variables
        call_kwargs = mock_run.call_args[1]
        env = call_kwargs["env"]
        assert "KOPI_DOCKA_HOOK_TYPE" in env
        assert env["KOPI_DOCKA_HOOK_TYPE"] == HOOK_PRE_BACKUP

    def test_hook_receives_unit_name_env(self, tmp_path):
        """Hook receives KOPI_DOCKA_UNIT_NAME when unit_name provided."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            manager.execute_hook(HOOK_PRE_BACKUP, unit_name="mystack")

        # Verify environment variables
        call_kwargs = mock_run.call_args[1]
        env = call_kwargs["env"]
        assert "KOPI_DOCKA_UNIT_NAME" in env
        assert env["KOPI_DOCKA_UNIT_NAME"] == "mystack"

    def test_hook_no_unit_name_env_when_not_provided(self, tmp_path):
        """KOPI_DOCKA_UNIT_NAME not set when unit_name is None."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            manager.execute_hook(HOOK_PRE_BACKUP, unit_name=None)

        # Verify unit_name not in env
        call_kwargs = mock_run.call_args[1]
        env = call_kwargs["env"]
        assert "KOPI_DOCKA_UNIT_NAME" not in env

    def test_hook_inherits_system_environment(self, tmp_path):
        """Hook inherits system environment variables."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        # Set a test env var
        os.environ["TEST_VAR"] = "test_value"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            manager.execute_hook(HOOK_PRE_BACKUP)

        # Verify system env is preserved
        call_kwargs = mock_run.call_args[1]
        env = call_kwargs["env"]
        assert "TEST_VAR" in env
        assert env["TEST_VAR"] == "test_value"

        # Cleanup
        del os.environ["TEST_VAR"]


# =============================================================================
# Executed Hooks Tracking Tests
# =============================================================================


@pytest.mark.unit
class TestExecutedHooksTracking:
    """Tests for tracking executed hooks."""

    def test_get_executed_hooks_empty(self):
        """get_executed_hooks returns empty list initially."""
        config = make_mock_config()
        manager = HooksManager(config)

        hooks = manager.get_executed_hooks()

        assert hooks == []

    def test_executed_hooks_tracked_on_success(self, tmp_path):
        """Successful hook execution is tracked."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            manager.execute_hook(HOOK_PRE_BACKUP)

        hooks = manager.get_executed_hooks()
        assert len(hooks) == 1
        assert "pre_backup:test-hook.sh" in hooks

    def test_executed_hooks_not_tracked_on_failure(self, tmp_path):
        """Failed hook execution is NOT tracked."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 1\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error")

            manager.execute_hook(HOOK_PRE_BACKUP)

        hooks = manager.get_executed_hooks()
        assert len(hooks) == 0

    def test_multiple_hooks_tracked(self, tmp_path):
        """Multiple successful hooks are tracked."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            manager.execute_hook(HOOK_PRE_BACKUP)
            manager.execute_hook(HOOK_POST_BACKUP)

        hooks = manager.get_executed_hooks()
        assert len(hooks) == 2
        assert "pre_backup:test-hook.sh" in hooks
        assert "post_backup:test-hook.sh" in hooks

    def test_get_executed_hooks_returns_copy(self, tmp_path):
        """get_executed_hooks returns a copy, not reference."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            manager.execute_hook(HOOK_PRE_BACKUP)

        hooks1 = manager.get_executed_hooks()
        hooks2 = manager.get_executed_hooks()

        # Modify the first list
        hooks1.append("fake:hook")

        # Second list should not be affected
        assert len(hooks2) == 1
        assert "fake:hook" not in hooks2


# =============================================================================
# Hook Type Convenience Methods Tests
# =============================================================================


@pytest.mark.unit
class TestHookTypeConvenienceMethods:
    """Tests for pre_backup, post_backup, pre_restore, post_restore methods."""

    def test_execute_pre_backup(self, tmp_path):
        """execute_pre_backup calls execute_hook with correct type."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch.object(manager, "execute_hook", return_value=True) as mock_exec:
            result = manager.execute_pre_backup("testunit")

        assert result is True
        mock_exec.assert_called_once_with(HOOK_PRE_BACKUP, "testunit")

    def test_execute_post_backup(self, tmp_path):
        """execute_post_backup calls execute_hook with correct type."""
        config = make_mock_config()
        manager = HooksManager(config)

        with patch.object(manager, "execute_hook", return_value=True) as mock_exec:
            result = manager.execute_post_backup("testunit")

        assert result is True
        mock_exec.assert_called_once_with(HOOK_POST_BACKUP, "testunit")

    def test_execute_pre_restore(self, tmp_path):
        """execute_pre_restore calls execute_hook with correct type."""
        config = make_mock_config()
        manager = HooksManager(config)

        with patch.object(manager, "execute_hook", return_value=True) as mock_exec:
            result = manager.execute_pre_restore("testunit")

        assert result is True
        mock_exec.assert_called_once_with(HOOK_PRE_RESTORE, "testunit")

    def test_execute_post_restore(self, tmp_path):
        """execute_post_restore calls execute_hook with correct type."""
        config = make_mock_config()
        manager = HooksManager(config)

        with patch.object(manager, "execute_hook", return_value=True) as mock_exec:
            result = manager.execute_post_restore("testunit")

        assert result is True
        mock_exec.assert_called_once_with(HOOK_POST_RESTORE, "testunit")


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.unit
class TestHookErrorHandling:
    """Tests for hook execution error handling."""

    def test_hook_exception_returns_false(self, tmp_path):
        """Hook that raises exception returns False."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Unexpected error")

            result = manager.execute_hook(HOOK_PRE_BACKUP)

        assert result is False

    def test_hook_permission_error(self, tmp_path):
        """Hook with permission issues is handled gracefully."""
        hook_script = tmp_path / "test-hook.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        config = make_mock_config(str(hook_script))
        manager = HooksManager(config)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = PermissionError("Permission denied")

            result = manager.execute_hook(HOOK_PRE_BACKUP)

        assert result is False
