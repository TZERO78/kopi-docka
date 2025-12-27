"""
Unit tests for backup commands (list, backup, restore).

Tests the backup_commands.py module with mocked Docker and Kopia operations.
"""

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from kopi_docka.__main__ import app


@pytest.mark.unit
class TestListCommand:
    """Tests for list command."""

    def test_list_requires_root(self, cli_runner, mock_non_root):
        """list command requires root privileges."""
        result = cli_runner.invoke(app, ["list"])

        assert result.exit_code == 13  # EACCES
        output = result.stdout + result.stderr
        assert "Root-Rechte" in output or "benötigt Root" in output

    @patch("kopi_docka.commands.backup_commands.DockerDiscovery")
    def test_list_units_only(
        self, mock_discovery_class, cli_runner, mock_root, tmp_config, mock_backup_unit
    ):
        """list --units shows discovered backup units."""
        mock_discovery = mock_discovery_class.return_value
        mock_discovery.discover_backup_units.return_value = [mock_backup_unit]

        result = cli_runner.invoke(app, ["list", "--units", "--config", str(tmp_config)])

        assert result.exit_code == 0
        assert "Discovering Docker backup units" in result.stdout
        assert "test-unit" in result.stdout

    @patch("kopi_docka.commands.backup_commands.KopiaRepository")
    def test_list_snapshots_only(
        self, mock_repo_class, cli_runner, mock_root, tmp_config, sample_snapshots
    ):
        """list --snapshots shows repository snapshots."""
        mock_repo = mock_repo_class.return_value
        mock_repo.list_snapshots.return_value = sample_snapshots

        result = cli_runner.invoke(
            app, ["list", "--no-units", "--snapshots", "--config", str(tmp_config)]
        )

        assert result.exit_code == 0
        assert "Listing snapshots" in result.stdout
        assert "snap1" in result.stdout

    @patch("kopi_docka.commands.backup_commands.DockerDiscovery")
    def test_list_handles_discovery_error(
        self, mock_discovery_class, cli_runner, mock_root, tmp_config
    ):
        """list handles Docker discovery errors gracefully."""
        mock_discovery = mock_discovery_class.return_value
        mock_discovery.discover_backup_units.side_effect = Exception("Docker not available")

        result = cli_runner.invoke(app, ["list", "--config", str(tmp_config)])

        assert result.exit_code == 1
        assert "Discovery failed" in result.stdout


@pytest.mark.unit
class TestBackupCommand:
    """Tests for backup command."""

    def test_backup_requires_root(self, cli_runner, mock_non_root):
        """backup command requires root privileges."""
        result = cli_runner.invoke(app, ["backup"])

        assert result.exit_code == 13
        output = result.stdout + result.stderr
        assert "Root-Rechte" in output or "benötigt Root" in output

    @patch("kopi_docka.commands.backup_commands.DockerDiscovery")
    @patch("kopi_docka.commands.backup_commands.BackupManager")
    @patch("kopi_docka.commands.backup_commands.KopiaRepository")
    def test_backup_all_units(
        self,
        mock_repo_class,
        mock_manager_class,
        mock_discovery_class,
        cli_runner,
        mock_root,
        tmp_config,
        mock_backup_unit,
    ):
        """backup processes all discovered units."""
        # Setup mocks
        mock_discovery = mock_discovery_class.return_value
        mock_discovery.discover_backup_units.return_value = [mock_backup_unit]

        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True

        mock_manager = mock_manager_class.return_value
        mock_meta = MagicMock(
            success=True,
            duration_seconds=10.5,
            kopia_snapshot_ids=["snap123"],
            errors=None,
            error_message=None,
        )
        mock_manager.backup_unit.return_value = mock_meta

        # Execute
        result = cli_runner.invoke(app, ["backup", "--config", str(tmp_config)])

        # Verify
        assert result.exit_code == 0
        assert "Backing up unit" in result.stdout
        assert "test-unit" in result.stdout
        assert "completed" in result.stdout
        mock_manager.backup_unit.assert_called_once()

    @patch("kopi_docka.commands.backup_commands.DockerDiscovery")
    @patch("kopi_docka.commands.backup_commands.BackupManager")
    @patch("kopi_docka.commands.backup_commands.KopiaRepository")
    def test_backup_specific_unit(
        self,
        mock_repo_class,
        mock_manager_class,
        mock_discovery_class,
        cli_runner,
        mock_root,
        tmp_config,
        mock_backup_unit,
    ):
        """backup --unit NAME processes only specified unit."""
        mock_discovery = mock_discovery_class.return_value
        mock_discovery.discover_backup_units.return_value = [mock_backup_unit]

        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True

        mock_manager = mock_manager_class.return_value
        mock_meta = MagicMock(success=True, duration_seconds=5)
        mock_manager.backup_unit.return_value = mock_meta

        result = cli_runner.invoke(
            app, ["backup", "--unit", "test-unit", "--config", str(tmp_config)]
        )

        assert result.exit_code == 0
        mock_manager.backup_unit.assert_called_once()

    @patch("kopi_docka.commands.backup_commands.DockerDiscovery")
    @patch("kopi_docka.commands.backup_commands.DryRunReport")
    @patch("kopi_docka.commands.backup_commands.KopiaRepository")
    def test_backup_dry_run(
        self,
        mock_repo_class,
        mock_report_class,
        mock_discovery_class,
        cli_runner,
        mock_root,
        tmp_config,
        mock_backup_unit,
    ):
        """backup --dry-run simulates without actual backup."""
        mock_discovery = mock_discovery_class.return_value
        mock_discovery.discover_backup_units.return_value = [mock_backup_unit]

        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True

        mock_report = mock_report_class.return_value

        result = cli_runner.invoke(app, ["backup", "--dry-run", "--config", str(tmp_config)])

        assert result.exit_code == 0
        mock_report.generate.assert_called_once()

    @patch("kopi_docka.commands.backup_commands.DockerDiscovery")
    @patch("kopi_docka.commands.backup_commands.BackupManager")
    @patch("kopi_docka.commands.backup_commands.KopiaRepository")
    def test_backup_handles_errors(
        self,
        mock_repo_class,
        mock_manager_class,
        mock_discovery_class,
        cli_runner,
        mock_root,
        tmp_config,
        mock_backup_unit,
    ):
        """backup shows errors from BackupManager."""
        mock_discovery = mock_discovery_class.return_value
        mock_discovery.discover_backup_units.return_value = [mock_backup_unit]

        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True

        mock_manager = mock_manager_class.return_value
        mock_meta = MagicMock(
            success=False,
            duration_seconds=2,
            error_message="Backup failed",
            errors=["Container stop failed"],
        )
        mock_manager.backup_unit.return_value = mock_meta

        result = cli_runner.invoke(app, ["backup", "--config", str(tmp_config)])

        assert result.exit_code == 1
        assert "failed" in result.stdout


@pytest.mark.unit
class TestRestoreCommand:
    """Tests for restore command."""

    def test_restore_requires_root(self, cli_runner, mock_non_root):
        """restore command requires root privileges."""
        result = cli_runner.invoke(app, ["restore"])

        assert result.exit_code == 13
        output = result.stdout + result.stderr
        assert "Root-Rechte" in output or "benötigt Root" in output

    @patch("kopi_docka.commands.backup_commands.RestoreManager")
    @patch("kopi_docka.commands.backup_commands.KopiaRepository")
    def test_restore_interactive(
        self, mock_repo_class, mock_restore_class, cli_runner, mock_root, tmp_config
    ):
        """restore launches interactive wizard."""
        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True

        mock_restore = mock_restore_class.return_value

        result = cli_runner.invoke(app, ["restore", "--config", str(tmp_config)])

        assert result.exit_code == 0
        mock_restore.interactive_restore.assert_called_once()

    @patch("kopi_docka.commands.backup_commands.RestoreManager")
    @patch("kopi_docka.commands.backup_commands.KopiaRepository")
    def test_restore_handles_errors(
        self, mock_repo_class, mock_restore_class, cli_runner, mock_root, tmp_config
    ):
        """restore handles errors gracefully."""
        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True

        mock_restore = mock_restore_class.return_value
        mock_restore.interactive_restore.side_effect = Exception("Restore error")

        result = cli_runner.invoke(app, ["restore", "--config", str(tmp_config)])

        assert result.exit_code == 1
        assert "Restore failed" in result.stdout
