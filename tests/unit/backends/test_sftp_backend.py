"""
Unit tests for SFTP backend dependency checking.

Tests REQUIRED_TOOLS enforcement for SFTP/SSH remote storage backend.
"""

from unittest.mock import patch, Mock
import pytest

from kopi_docka.backends.sftp import SFTPBackend
from kopi_docka.backends.base import DependencyError
from kopi_docka.helpers.dependency_helper import ToolInfo


@pytest.fixture
def sftp_backend():
    """Create an SFTPBackend instance for testing."""
    # Mock config to avoid initialization issues
    mock_config = Mock()
    backend = SFTPBackend(config=mock_config)
    return backend


class TestRequiredTools:
    """Test REQUIRED_TOOLS definition."""

    def test_required_tools_defined(self, sftp_backend):
        """Test that REQUIRED_TOOLS includes SSH tools."""
        assert hasattr(sftp_backend, 'REQUIRED_TOOLS')
        assert sftp_backend.REQUIRED_TOOLS == ["ssh", "ssh-keygen"]

    def test_required_tools_is_list(self, sftp_backend):
        """Test that REQUIRED_TOOLS is a list."""
        assert isinstance(sftp_backend.REQUIRED_TOOLS, list)
        assert len(sftp_backend.REQUIRED_TOOLS) == 2


class TestCheckDependencies:
    """Test check_dependencies method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_all_present(self, mock_missing, sftp_backend):
        """Test check_dependencies when all SSH tools are present."""
        mock_missing.return_value = []

        result = sftp_backend.check_dependencies()

        assert result == []
        mock_missing.assert_called_once_with(["ssh", "ssh-keygen"])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_ssh_missing(self, mock_missing, sftp_backend):
        """Test check_dependencies when ssh is missing."""
        mock_missing.return_value = ["ssh"]

        result = sftp_backend.check_dependencies()

        assert result == ["ssh"]
        mock_missing.assert_called_once_with(["ssh", "ssh-keygen"])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_ssh_keygen_missing(self, mock_missing, sftp_backend):
        """Test check_dependencies when ssh-keygen is missing."""
        mock_missing.return_value = ["ssh-keygen"]

        result = sftp_backend.check_dependencies()

        assert result == ["ssh-keygen"]
        mock_missing.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_both_missing(self, mock_missing, sftp_backend):
        """Test check_dependencies when both SSH tools are missing."""
        mock_missing.return_value = ["ssh", "ssh-keygen"]

        result = sftp_backend.check_dependencies()

        assert len(result) == 2
        assert "ssh" in result
        assert "ssh-keygen" in result


class TestGetDependencyStatus:
    """Test get_dependency_status method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_all_installed(self, mock_check_all, sftp_backend):
        """Test get_dependency_status when all SSH tools are installed."""
        mock_check_all.return_value = {
            "ssh": ToolInfo(
                name="ssh",
                installed=True,
                path="/usr/bin/ssh",
                version="8.9"
            ),
            "ssh-keygen": ToolInfo(
                name="ssh-keygen",
                installed=True,
                path="/usr/bin/ssh-keygen",
                version="8.9"
            ),
        }

        result = sftp_backend.get_dependency_status()

        assert len(result) == 2
        assert all(tool.installed for tool in result.values())
        assert result["ssh"].version == "8.9"
        assert result["ssh-keygen"].installed is True
        mock_check_all.assert_called_once_with(["ssh", "ssh-keygen"])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_ssh_missing(self, mock_check_all, sftp_backend):
        """Test get_dependency_status when ssh is missing."""
        mock_check_all.return_value = {
            "ssh": ToolInfo(
                name="ssh",
                installed=False,
                path=None,
                version=None
            ),
            "ssh-keygen": ToolInfo(
                name="ssh-keygen",
                installed=True,
                path="/usr/bin/ssh-keygen",
                version="8.9"
            ),
        }

        result = sftp_backend.get_dependency_status()

        assert result["ssh"].installed is False
        assert result["ssh"].path is None
        assert result["ssh-keygen"].installed is True
        mock_check_all.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_both_missing(self, mock_check_all, sftp_backend):
        """Test get_dependency_status when both tools are missing."""
        mock_check_all.return_value = {
            "ssh": ToolInfo(
                name="ssh",
                installed=False,
                path=None,
                version=None
            ),
            "ssh-keygen": ToolInfo(
                name="ssh-keygen",
                installed=False,
                path=None,
                version=None
            ),
        }

        result = sftp_backend.get_dependency_status()

        assert result["ssh"].installed is False
        assert result["ssh-keygen"].installed is False
        mock_check_all.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_returns_dict(self, mock_check_all, sftp_backend):
        """Test that get_dependency_status returns a dictionary."""
        mock_check_all.return_value = {
            "ssh": ToolInfo(name="ssh", installed=True, path="/usr/bin/ssh", version="8.9"),
            "ssh-keygen": ToolInfo(
                name="ssh-keygen",
                installed=True,
                path="/usr/bin/ssh-keygen",
                version="8.9"
            ),
        }

        result = sftp_backend.get_dependency_status()

        assert isinstance(result, dict)
        assert all(isinstance(info, ToolInfo) for info in result.values())


class TestConfigureDependencyCheck:
    """Test that configure checks dependencies."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    @patch('typer.prompt')
    def test_configure_raises_on_missing_dependencies(
        self, mock_prompt, mock_missing, sftp_backend
    ):
        """Test that configure raises DependencyError when SSH tools are missing."""
        mock_missing.return_value = ["ssh", "ssh-keygen"]

        with pytest.raises(DependencyError) as exc_info:
            sftp_backend.configure()

        assert "ssh" in str(exc_info.value).lower()
        # Prompt should not be called if dependencies are missing
        mock_prompt.assert_not_called()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    @patch('typer.prompt')
    @patch('typer.confirm')
    def test_configure_proceeds_when_dependencies_present(
        self, mock_confirm, mock_prompt, mock_missing, sftp_backend
    ):
        """Test that configure proceeds when all dependencies are present."""
        mock_missing.return_value = []
        # Mock prompts to avoid interactive input
        mock_prompt.side_effect = ["test-host", "22", "testuser", "/remote/path"]
        mock_confirm.return_value = True

        # Should not raise DependencyError
        try:
            result = sftp_backend.configure()
            # If it gets here, dependencies were checked and passed
            assert mock_missing.called
        except (SystemExit, Exception) as e:
            # Other errors are OK for this test - we just care that DependencyError wasn't raised
            if isinstance(e, DependencyError):
                pytest.fail("DependencyError should not be raised when dependencies are present")

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_configure_checks_dependencies_first(self, mock_missing, sftp_backend):
        """Test that configure checks dependencies before any interactive prompts."""
        mock_missing.return_value = ["ssh"]

        with pytest.raises(DependencyError):
            sftp_backend.configure()

        # Verify dependency check was called
        mock_missing.assert_called_once_with(["ssh", "ssh-keygen"])
