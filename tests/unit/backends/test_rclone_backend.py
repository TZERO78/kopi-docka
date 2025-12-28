"""
Unit tests for rclone backend configuration detection and dependency checking.

Tests the enhanced config detection with permission error handling and status reporting.
Also tests REQUIRED_TOOLS dependency enforcement.
Related to GitHub issue #29: Rclone Config Detection & User Experience Fix
"""

import os
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import pytest

from kopi_docka.backends.rclone import RcloneBackend, ConfigStatus, ConfigDetectionResult
from kopi_docka.helpers.dependency_helper import ToolInfo


@pytest.fixture
def rclone_backend():
    """Create a RcloneBackend instance for testing."""
    backend = RcloneBackend()
    return backend


@pytest.fixture
def mock_env_sudo_user(monkeypatch):
    """Mock SUDO_USER environment variable."""
    monkeypatch.setenv("SUDO_USER", "testuser")


@pytest.fixture
def mock_env_no_sudo_user(monkeypatch):
    """Remove SUDO_USER environment variable."""
    monkeypatch.delenv("SUDO_USER", raising=False)


class TestDetectRcloneConfigWithStatus:
    """Tests for _detect_rclone_config_with_status method."""

    def test_detect_config_found_and_readable(self, rclone_backend, mock_env_sudo_user):
        """Test detection when config exists at user path and is readable."""
        user_config_path = "/home/testuser/.config/rclone/rclone.conf"

        with mock.patch("pathlib.Path.exists") as mock_exists:
            # Mock config exists and is readable
            mock_exists.return_value = True

            result = rclone_backend._detect_rclone_config_with_status()

            # Assertions
            assert result.status == ConfigStatus.FOUND
            assert result.path == user_config_path
            assert user_config_path in result.checked_paths
            assert len(result.checked_paths) == 1

    def test_detect_config_permission_denied(self, rclone_backend, mock_env_sudo_user):
        """Test detection when config exists but PermissionError on access."""
        user_config_path = "/home/testuser/.config/rclone/rclone.conf"

        with mock.patch("pathlib.Path.exists") as mock_exists:
            # Mock PermissionError when checking if config exists
            mock_exists.side_effect = PermissionError("Permission denied")

            result = rclone_backend._detect_rclone_config_with_status()

            # Assertions - this is the core bug fix validation!
            assert result.status == ConfigStatus.PERMISSION_DENIED
            assert result.path == user_config_path
            assert user_config_path in result.checked_paths
            assert len(result.checked_paths) == 1

    def test_detect_config_not_found(self, rclone_backend, mock_env_sudo_user):
        """Test detection when no config at any location."""
        user_config_path = "/home/testuser/.config/rclone/rclone.conf"
        root_config_path = "/root/.config/rclone/rclone.conf"

        with mock.patch("pathlib.Path.exists") as mock_exists:
            # Mock config does not exist at any location
            mock_exists.return_value = False

            result = rclone_backend._detect_rclone_config_with_status()

            # Assertions
            assert result.status == ConfigStatus.NOT_FOUND
            assert result.path is None
            assert user_config_path in result.checked_paths
            assert root_config_path in result.checked_paths
            assert len(result.checked_paths) == 2

    def test_detect_config_no_sudo_user(self, rclone_backend, mock_env_no_sudo_user):
        """Test detection when SUDO_USER env not set, root config exists."""
        root_config_path = "/root/.config/rclone/rclone.conf"

        with mock.patch("pathlib.Path.exists") as mock_exists:
            # Mock root config exists and is readable
            mock_exists.return_value = True

            result = rclone_backend._detect_rclone_config_with_status()

            # Assertions - should skip user config check and go straight to root
            assert result.status == ConfigStatus.FOUND
            assert result.path == root_config_path
            assert root_config_path in result.checked_paths
            assert len(result.checked_paths) == 1

    def test_detect_config_home_dir_missing(self, rclone_backend, mock_env_sudo_user):
        """Test detection when SUDO_USER set but home dir doesn't exist."""
        user_config_path = "/home/testuser/.config/rclone/rclone.conf"
        root_config_path = "/root/.config/rclone/rclone.conf"

        def mock_exists_side_effect(self):
            """Mock exists() to return False for user, True for root."""
            if str(self) == user_config_path:
                return False
            elif str(self) == root_config_path:
                return True
            return False

        with mock.patch("pathlib.Path.exists", mock_exists_side_effect):
            result = rclone_backend._detect_rclone_config_with_status()

            # Assertions - should gracefully skip user config and find root config
            assert result.status == ConfigStatus.FOUND
            assert result.path == root_config_path
            assert user_config_path in result.checked_paths
            assert root_config_path in result.checked_paths
            assert len(result.checked_paths) == 2


class TestConfigureMethod:
    """Tests for configure method with status-aware detection."""

    def test_configure_shows_permission_warning(self, rclone_backend, mock_env_sudo_user):
        """Test that configure shows warning with workarounds for PERMISSION_DENIED."""
        user_config_path = "/home/testuser/.config/rclone/rclone.conf"

        with (
            mock.patch("shutil.which") as mock_which,
            mock.patch.object(rclone_backend, "_detect_rclone_config_with_status") as mock_detect,
            mock.patch("typer.confirm") as mock_confirm,
        ):

            # Mock rclone is installed
            mock_which.return_value = "/usr/bin/rclone"

            # Mock detection returns PERMISSION_DENIED
            mock_detect.return_value = ConfigDetectionResult(
                path=user_config_path,
                status=ConfigStatus.PERMISSION_DENIED,
                checked_paths=[user_config_path],
            )

            # Mock user declines to proceed without existing config
            mock_confirm.return_value = False

            # Should raise SystemExit when user declines
            with pytest.raises(SystemExit) as exc_info:
                rclone_backend.configure()

            assert exc_info.value.code == 1
            # Verify confirm was called (permission warning flow was triggered)
            mock_confirm.assert_called_once()

    def test_configure_offers_create_when_not_found(self, rclone_backend, mock_env_sudo_user):
        """Test that configure offers to create config when NOT_FOUND."""
        user_config_path = "/home/testuser/.config/rclone/rclone.conf"
        root_config_path = "/root/.config/rclone/rclone.conf"

        with (
            mock.patch("shutil.which") as mock_which,
            mock.patch.object(rclone_backend, "_detect_rclone_config_with_status") as mock_detect,
            mock.patch("typer.confirm") as mock_confirm,
        ):

            # Mock rclone is installed
            mock_which.return_value = "/usr/bin/rclone"

            # Mock detection returns NOT_FOUND
            mock_detect.return_value = ConfigDetectionResult(
                path=None,
                status=ConfigStatus.NOT_FOUND,
                checked_paths=[user_config_path, root_config_path],
            )

            # Mock user declines to create new config
            mock_confirm.return_value = False

            # Should raise SystemExit when user declines to create config
            with pytest.raises(SystemExit) as exc_info:
                rclone_backend.configure()

            assert exc_info.value.code == 1
            # Verify confirm was called (offer to create flow was triggered)
            mock_confirm.assert_called_once()


class TestDependencyChecking:
    """Tests for dependency checking with REQUIRED_TOOLS."""

    def test_required_tools_defined(self, rclone_backend):
        """Test that REQUIRED_TOOLS is properly defined."""
        assert hasattr(rclone_backend, 'REQUIRED_TOOLS')
        assert rclone_backend.REQUIRED_TOOLS == ["rclone"]

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_all_present(self, mock_missing, rclone_backend):
        """Test check_dependencies when all tools are present."""
        mock_missing.return_value = []

        result = rclone_backend.check_dependencies()

        assert result == []
        mock_missing.assert_called_once_with(["rclone"])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_rclone_missing(self, mock_missing, rclone_backend):
        """Test check_dependencies when rclone is missing."""
        mock_missing.return_value = ["rclone"]

        result = rclone_backend.check_dependencies()

        assert result == ["rclone"]
        mock_missing.assert_called_once_with(["rclone"])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_all_installed(self, mock_check_all, rclone_backend):
        """Test get_dependency_status when all tools are installed."""
        mock_check_all.return_value = {
            "rclone": ToolInfo(
                name="rclone",
                installed=True,
                path="/usr/bin/rclone",
                version="1.65.0"
            )
        }

        result = rclone_backend.get_dependency_status()

        assert "rclone" in result
        assert result["rclone"].installed is True
        assert result["rclone"].version == "1.65.0"
        mock_check_all.assert_called_once_with(["rclone"])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_missing(self, mock_check_all, rclone_backend):
        """Test get_dependency_status when rclone is missing."""
        mock_check_all.return_value = {
            "rclone": ToolInfo(
                name="rclone",
                installed=False,
                path=None,
                version=None
            )
        }

        result = rclone_backend.get_dependency_status()

        assert "rclone" in result
        assert result["rclone"].installed is False
        assert result["rclone"].path is None
        mock_check_all.assert_called_once_with(["rclone"])
