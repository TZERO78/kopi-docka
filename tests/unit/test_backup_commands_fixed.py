"""
Unit tests for backup commands - FIXED VERSION with direct function calls.

This version uses direct function calls instead of cli_runner.invoke()
to avoid Typer context initialization issues.
"""

import pytest
import typer
from unittest.mock import patch, MagicMock
from kopi_docka.__main__ import app
from kopi_docka.commands.backup_commands import cmd_list, cmd_backup, cmd_restore


@pytest.mark.unit
class TestListCommand:
    """Tests for list command."""

    def test_list_requires_root(self, cli_runner, mock_non_root):
        """list command requires root privileges (CLI test)."""
        result = cli_runner.invoke(app, ["list"])

        assert result.exit_code == 13
        output = result.stdout + result.stderr
        assert "Root-Rechte" in output or "benötigt Root" in output

    @patch("kopi_docka.commands.backup_commands.DockerDiscovery")
    def test_list_units_only(
        self, mock_discovery_class, capsys, mock_root, mock_ctx, mock_backup_unit
    ):
        """list --units shows discovered backup units (direct function test)."""
        mock_discovery = mock_discovery_class.return_value
        mock_discovery.discover_backup_units.return_value = [mock_backup_unit]

        # Direct function call
        cmd_list(mock_ctx, units=True, snapshots=False)

        captured = capsys.readouterr()
        assert "Discovering Docker backup units" in captured.out
        assert "test-unit" in captured.out


@pytest.mark.unit
class TestBackupCommand:
    """Tests for backup command."""

    def test_backup_requires_root(self, cli_runner, mock_non_root):
        """backup command requires root privileges (CLI test)."""
        result = cli_runner.invoke(app, ["backup"])

        assert result.exit_code == 13
        output = result.stdout + result.stderr
        assert "Root-Rechte" in output or "benötigt Root" in output

    @patch("kopi_docka.cores.dependency_manager.DependencyManager")
    @patch("kopi_docka.commands.backup_commands.DockerDiscovery")
    @patch("kopi_docka.commands.backup_commands.BackupManager")
    @patch("kopi_docka.commands.backup_commands.KopiaRepository")
    def test_backup_all_units(
        self,
        mock_repo_class,
        mock_manager_class,
        mock_discovery_class,
        mock_dep_manager_class,
        capsys,
        mock_root,
        mock_ctx,
        mock_backup_unit,
    ):
        """backup processes all discovered units (direct function test)."""
        # Mock DependencyManager to bypass hard gate check
        mock_dep_manager = mock_dep_manager_class.return_value
        mock_dep_manager.check_hard_gate.return_value = None

        # Setup mocks
        mock_discovery = mock_discovery_class.return_value
        mock_discovery.discover_backup_units.return_value = [mock_backup_unit]

        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True
        mock_ctx.obj["repository"] = mock_repo

        mock_manager = mock_manager_class.return_value
        mock_meta = MagicMock(
            success=True,
            duration_seconds=10.5,
            kopia_snapshot_ids=["snap123"],
            errors=None,
            error_message=None,
        )
        mock_manager.backup_unit.return_value = mock_meta

        # Direct function call
        cmd_backup(mock_ctx, unit=None, dry_run=False, update_recovery_bundle=None)

        captured = capsys.readouterr()
        assert "Backing up unit" in captured.out
        assert "test-unit" in captured.out
        assert "completed" in captured.out
        mock_manager.backup_unit.assert_called_once()


@pytest.mark.unit
class TestRestoreCommand:
    """Tests for restore command."""

    def test_restore_requires_root(self, cli_runner, mock_non_root):
        """restore command requires root privileges (CLI test)."""
        result = cli_runner.invoke(app, ["restore"])

        assert result.exit_code == 13
        output = result.stdout + result.stderr
        assert "Root-Rechte" in output or "benötigt Root" in output

    @patch("kopi_docka.cores.dependency_manager.DependencyManager")
    @patch("kopi_docka.commands.backup_commands.RestoreManager")
    @patch("kopi_docka.commands.backup_commands.KopiaRepository")
    def test_restore_interactive(
        self, mock_repo_class, mock_restore_class, mock_dep_manager_class, mock_root, mock_ctx
    ):
        """restore launches interactive wizard (direct function test)."""
        # Mock DependencyManager to bypass hard gate check
        mock_dep_manager = mock_dep_manager_class.return_value
        mock_dep_manager.check_hard_gate.return_value = None

        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True
        mock_ctx.obj["repository"] = mock_repo

        mock_restore = mock_restore_class.return_value

        # Direct function call
        cmd_restore(mock_ctx)

        mock_restore.interactive_restore.assert_called_once()
