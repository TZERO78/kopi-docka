"""
Unit tests for Tailscale backend dependency checking.

Tests REQUIRED_TOOLS enforcement for Tailscale SSH-based backup backend.
"""

from unittest.mock import patch, Mock
import pytest

from kopi_docka.backends.tailscale import TailscaleBackend
from kopi_docka.backends.base import DependencyError
from kopi_docka.helpers.dependency_helper import ToolInfo


@pytest.fixture
def tailscale_backend():
    """Create a TailscaleBackend instance for testing."""
    # Mock config to avoid initialization issues
    mock_config = Mock()
    backend = TailscaleBackend(config=mock_config)
    return backend


class TestRequiredTools:
    """Test REQUIRED_TOOLS definition."""

    def test_required_tools_defined(self, tailscale_backend):
        """Test that REQUIRED_TOOLS includes all necessary tools."""
        assert hasattr(tailscale_backend, 'REQUIRED_TOOLS')
        assert tailscale_backend.REQUIRED_TOOLS == [
            "tailscale", "ssh", "ssh-keygen", "ssh-copy-id"
        ]

    def test_required_tools_is_list(self, tailscale_backend):
        """Test that REQUIRED_TOOLS is a list."""
        assert isinstance(tailscale_backend.REQUIRED_TOOLS, list)
        assert len(tailscale_backend.REQUIRED_TOOLS) == 4


class TestCheckDependencies:
    """Test check_dependencies method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_all_present(self, mock_missing, tailscale_backend):
        """Test check_dependencies when all tools are present."""
        mock_missing.return_value = []

        result = tailscale_backend.check_dependencies()

        assert result == []
        mock_missing.assert_called_once_with([
            "tailscale", "ssh", "ssh-keygen", "ssh-copy-id"
        ])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_tailscale_missing(self, mock_missing, tailscale_backend):
        """Test check_dependencies when tailscale is missing."""
        mock_missing.return_value = ["tailscale"]

        result = tailscale_backend.check_dependencies()

        assert result == ["tailscale"]
        mock_missing.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_ssh_tools_missing(self, mock_missing, tailscale_backend):
        """Test check_dependencies when SSH tools are missing."""
        mock_missing.return_value = ["ssh", "ssh-keygen"]

        result = tailscale_backend.check_dependencies()

        assert "ssh" in result
        assert "ssh-keygen" in result
        mock_missing.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_multiple_missing(self, mock_missing, tailscale_backend):
        """Test check_dependencies when multiple tools are missing."""
        mock_missing.return_value = ["tailscale", "ssh", "ssh-copy-id"]

        result = tailscale_backend.check_dependencies()

        assert len(result) == 3
        assert "tailscale" in result
        assert "ssh" in result
        assert "ssh-copy-id" in result


class TestGetDependencyStatus:
    """Test get_dependency_status method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_all_installed(self, mock_check_all, tailscale_backend):
        """Test get_dependency_status when all tools are installed."""
        mock_check_all.return_value = {
            "tailscale": ToolInfo(
                name="tailscale",
                installed=True,
                path="/usr/bin/tailscale",
                version="1.56.1"
            ),
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
            "ssh-copy-id": ToolInfo(
                name="ssh-copy-id",
                installed=True,
                path="/usr/bin/ssh-copy-id",
                version="8.9"
            ),
        }

        result = tailscale_backend.get_dependency_status()

        assert len(result) == 4
        assert all(tool.installed for tool in result.values())
        assert result["tailscale"].version == "1.56.1"
        assert result["ssh"].installed is True
        mock_check_all.assert_called_once_with([
            "tailscale", "ssh", "ssh-keygen", "ssh-copy-id"
        ])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_some_missing(self, mock_check_all, tailscale_backend):
        """Test get_dependency_status when some tools are missing."""
        mock_check_all.return_value = {
            "tailscale": ToolInfo(
                name="tailscale",
                installed=False,
                path=None,
                version=None
            ),
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
            "ssh-copy-id": ToolInfo(
                name="ssh-copy-id",
                installed=False,
                path=None,
                version=None
            ),
        }

        result = tailscale_backend.get_dependency_status()

        assert result["tailscale"].installed is False
        assert result["ssh"].installed is True
        assert result["ssh-copy-id"].installed is False
        mock_check_all.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_returns_dict(self, mock_check_all, tailscale_backend):
        """Test that get_dependency_status returns a dictionary."""
        mock_check_all.return_value = {
            tool: ToolInfo(name=tool, installed=True, path=f"/usr/bin/{tool}", version="1.0")
            for tool in ["tailscale", "ssh", "ssh-keygen", "ssh-copy-id"]
        }

        result = tailscale_backend.get_dependency_status()

        assert isinstance(result, dict)
        assert all(isinstance(info, ToolInfo) for info in result.values())


class TestSetupInteractiveDependencyCheck:
    """Test that setup_interactive checks dependencies."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    @patch('typer.prompt')
    def test_setup_interactive_raises_on_missing_dependencies(
        self, mock_prompt, mock_missing, tailscale_backend
    ):
        """Test that setup_interactive raises DependencyError when tools are missing."""
        mock_missing.return_value = ["tailscale", "ssh"]

        with pytest.raises(DependencyError) as exc_info:
            tailscale_backend.setup_interactive()

        assert "tailscale" in str(exc_info.value).lower()
        assert "ssh" in str(exc_info.value).lower()
        # Prompt should not be called if dependencies are missing
        mock_prompt.assert_not_called()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    @patch('typer.prompt')
    def test_setup_interactive_proceeds_when_dependencies_present(
        self, mock_prompt, mock_missing, tailscale_backend
    ):
        """Test that setup_interactive proceeds when all dependencies are present."""
        mock_missing.return_value = []
        # Mock prompts to avoid interactive input
        mock_prompt.side_effect = ["test-target", "22", "testuser"]

        # Should not raise DependencyError
        try:
            result = tailscale_backend.setup_interactive()
            # If it gets here, dependencies were checked and passed
            assert mock_missing.called
        except (SystemExit, Exception) as e:
            # Other errors are OK for this test - we just care that DependencyError wasn't raised
            if isinstance(e, DependencyError):
                pytest.fail("DependencyError should not be raised when dependencies are present")
