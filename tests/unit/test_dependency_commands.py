"""
Unit tests for dependency commands (check, install-deps, show-deps).

Tests the dependency_commands.py module with mocked DependencyManager.
"""

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from kopi_docka.__main__ import app


@pytest.mark.unit
class TestCheckCommand:
    """Tests for check command."""

    def test_check_no_root_needed(self, cli_runner, mock_non_root):
        """check is a SAFE_COMMAND and works without root."""
        with patch("kopi_docka.commands.dependency_commands.DependencyManager") as mock_deps:
            mock_deps.return_value.print_status = MagicMock()

            result = cli_runner.invoke(app, ["check"])

            # Should work, not exit with 13
            assert result.exit_code != 13

    @patch("kopi_docka.commands.dependency_commands.DependencyManager")
    def test_check_shows_status(self, mock_deps_class, cli_runner, mock_non_root):
        """check shows dependency status."""
        mock_deps = mock_deps_class.return_value

        result = cli_runner.invoke(app, ["check"])

        assert result.exit_code == 0
        mock_deps.print_status.assert_called_once_with(verbose=False)

    @patch("kopi_docka.commands.dependency_commands.DependencyManager")
    def test_check_verbose(self, mock_deps_class, cli_runner, mock_non_root):
        """check --verbose shows detailed information."""
        mock_deps = mock_deps_class.return_value

        result = cli_runner.invoke(app, ["check", "--verbose"])

        assert result.exit_code == 0
        mock_deps.print_status.assert_called_once_with(verbose=True)

    @patch("kopi_docka.commands.dependency_commands.KopiaRepository")
    @patch("kopi_docka.commands.dependency_commands.DependencyManager")
    def test_check_with_config(
        self, mock_deps_class, mock_repo_class, cli_runner, mock_non_root, tmp_config
    ):
        """check with valid config checks repository."""
        mock_deps = mock_deps_class.return_value
        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True
        mock_repo.profile_name = "test-profile"
        mock_repo.repo_path = "/tmp/test-repo"

        result = cli_runner.invoke(app, ["check", "--config", str(tmp_config)])

        assert result.exit_code == 0
        assert "Kopia repository is connected" in result.stdout

    @patch("kopi_docka.commands.dependency_commands.DependencyManager")
    def test_check_no_config(self, mock_deps_class, cli_runner, mock_non_root):
        """check without config shows repository not connected message."""
        mock_deps = mock_deps_class.return_value

        result = cli_runner.invoke(app, ["check"])

        assert result.exit_code == 0
        # When there's no config in context, it shows this message
        assert "No configuration found" in result.stdout or "repository not connected" in result.stdout


