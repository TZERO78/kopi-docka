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
        """check without config shows message."""
        mock_deps = mock_deps_class.return_value

        result = cli_runner.invoke(app, ["check"])

        assert result.exit_code == 0
        assert "No configuration found" in result.stdout


@pytest.mark.unit
class TestInstallDepsCommand:
    """Tests for install-deps command."""

    def test_install_requires_root(self, cli_runner, mock_non_root):
        """install-deps requires root privileges."""
        result = cli_runner.invoke(app, ["install-deps", "--dry-run"])

        assert result.exit_code == 13
        output = result.stdout + result.stderr
        assert "Root-Rechte" in output or "benötigt Root" in output

    @patch("kopi_docka.commands.dependency_commands.DependencyManager")
    def test_install_dry_run(self, mock_deps_class, cli_runner, mock_root):
        """install-deps --dry-run shows what would be installed."""
        mock_deps = mock_deps_class.return_value
        mock_deps.get_missing.return_value = ["docker", "kopia"]
        mock_deps.install_missing = MagicMock()

        result = cli_runner.invoke(app, ["install-deps", "--dry-run"])

        assert result.exit_code == 0
        mock_deps.install_missing.assert_called_once_with(dry_run=True)

    @patch("kopi_docka.commands.dependency_commands.DependencyManager")
    def test_install_installs_missing(self, mock_deps_class, cli_runner, mock_root):
        """install-deps installs missing dependencies."""
        mock_deps = mock_deps_class.return_value
        mock_deps.get_missing.return_value = ["kopia"]
        mock_deps.auto_install.return_value = True

        result = cli_runner.invoke(app, ["install-deps", "--force"])

        assert result.exit_code == 0
        assert "Installed" in result.stdout
        mock_deps.auto_install.assert_called_once_with(force=True)

    @patch("kopi_docka.commands.dependency_commands.DependencyManager")
    def test_install_all_present(self, mock_deps_class, cli_runner, mock_root):
        """install-deps when all dependencies present."""
        mock_deps = mock_deps_class.return_value
        mock_deps.get_missing.return_value = []

        result = cli_runner.invoke(app, ["install-deps"])

        assert result.exit_code == 0
        assert "already installed" in result.stdout

    @patch("kopi_docka.commands.dependency_commands.DependencyManager")
    def test_install_failure(self, mock_deps_class, cli_runner, mock_root):
        """install-deps handles installation failure."""
        mock_deps = mock_deps_class.return_value
        mock_deps.get_missing.return_value = ["kopia"]
        mock_deps.auto_install.return_value = False

        result = cli_runner.invoke(app, ["install-deps", "--force"])

        assert result.exit_code == 1


@pytest.mark.unit
class TestShowDepsCommand:
    """Tests for show-deps command."""

    def test_show_deps_no_root(self, cli_runner, mock_non_root):
        """show-deps is a SAFE_COMMAND and works without root."""
        with patch("kopi_docka.commands.dependency_commands.DependencyManager") as mock_deps:
            mock_deps.return_value.print_install_guide = MagicMock()

            result = cli_runner.invoke(app, ["show-deps"])

            # Should work, not exit with 13
            assert result.exit_code != 13

    @patch("kopi_docka.commands.dependency_commands.DependencyManager")
    def test_show_deps_output(self, mock_deps_class, cli_runner, mock_non_root):
        """show-deps displays installation guide."""
        mock_deps = mock_deps_class.return_value

        result = cli_runner.invoke(app, ["show-deps"])

        assert result.exit_code == 0
        mock_deps.print_install_guide.assert_called_once()
