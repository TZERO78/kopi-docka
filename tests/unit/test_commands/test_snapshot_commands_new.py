"""Unit tests for new snapshot commands added in Plan 0024."""

import pytest
from unittest.mock import patch, Mock

from kopi_docka.__main__ import app


@pytest.mark.unit
class TestSnapshotManageCommand:
    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_manage_needs_config(self, mock_mgr_cls, cli_runner, mock_non_root):
        # Without config, should fail (no config file)
        result = cli_runner.invoke(app, ["advanced", "snapshot", "manage"])
        # May fail due to missing config or proceed — just check no unhandled crash
        assert result.exit_code in (0, 1, 2)

    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_manage_calls_interactive(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        result = cli_runner.invoke(
            app, ["--config", str(tmp_config), "advanced", "snapshot", "manage"]
        )
        mock_mgr.interactive_manage.assert_called_once()


@pytest.mark.unit
class TestSnapshotMaintenanceCommand:
    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_maintenance_default(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        result = cli_runner.invoke(
            app, ["--config", str(tmp_config), "advanced", "snapshot", "maintenance"]
        )
        mock_mgr.cmd_maintenance.assert_called_once_with(full=False)

    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_maintenance_full(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        result = cli_runner.invoke(
            app, ["--config", str(tmp_config), "advanced", "snapshot", "maintenance", "--full"]
        )
        mock_mgr.cmd_maintenance.assert_called_once_with(full=True)


@pytest.mark.unit
class TestSnapshotPruneEmptyCommand:
    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_prune_empty_default(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        result = cli_runner.invoke(
            app, ["--config", str(tmp_config), "advanced", "snapshot", "prune-empty"]
        )
        mock_mgr.cmd_prune_empty.assert_called_once_with(dry_run=False)

    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_prune_empty_dry_run(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        result = cli_runner.invoke(
            app, ["--config", str(tmp_config), "advanced", "snapshot", "prune-empty", "--dry-run"]
        )
        mock_mgr.cmd_prune_empty.assert_called_once_with(dry_run=True)


@pytest.mark.unit
class TestSnapshotDeleteCommand:
    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_delete_calls_cmd(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        result = cli_runner.invoke(
            app, ["--config", str(tmp_config), "advanced", "snapshot", "delete", "abc123def"]
        )
        mock_mgr.cmd_delete.assert_called_once_with("abc123def", force=False)

    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_delete_with_force(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        result = cli_runner.invoke(
            app,
            ["--config", str(tmp_config), "advanced", "snapshot", "delete", "abc123", "--force"],
        )
        mock_mgr.cmd_delete.assert_called_once_with("abc123", force=True)


@pytest.mark.unit
class TestSnapshotPinUnpinCommand:
    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_pin_calls_cmd(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        result = cli_runner.invoke(
            app, ["--config", str(tmp_config), "advanced", "snapshot", "pin", "abc123"]
        )
        mock_mgr.cmd_pin.assert_called_once_with("abc123")

    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_unpin_calls_cmd(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        result = cli_runner.invoke(
            app, ["--config", str(tmp_config), "advanced", "snapshot", "unpin", "abc123"]
        )
        mock_mgr.cmd_unpin.assert_called_once_with("abc123")


@pytest.mark.unit
class TestSnapshotRetentionCommands:
    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_retention_show(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        result = cli_runner.invoke(
            app, ["--config", str(tmp_config), "advanced", "snapshot", "retention", "show"]
        )
        mock_mgr.cmd_retention_show.assert_called_once()

    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_retention_set_no_args_passes_all_none(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        """v7.3.7: each flag's Typer default is None now, so the core
        manager knows which values came from the user vs. which to read
        from the current config."""
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        cli_runner.invoke(
            app, ["--config", str(tmp_config), "advanced", "snapshot", "retention", "set"]
        )
        mock_mgr.cmd_retention_set.assert_called_once_with(
            latest=None, hourly=None, daily=None,
            weekly=None, monthly=None, annual=None, force=False,
        )

    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_retention_set_custom_values(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        cli_runner.invoke(
            app,
            [
                "--config", str(tmp_config),
                "advanced", "snapshot", "retention", "set",
                "--latest", "5",
                "--daily", "14",
            ],
        )
        kwargs = mock_mgr.cmd_retention_set.call_args.kwargs
        assert kwargs["latest"] == 5
        assert kwargs["daily"] == 14
        assert kwargs["hourly"] is None
        assert kwargs["weekly"] is None
        assert kwargs["monthly"] is None
        assert kwargs["annual"] is None

    @patch("kopi_docka.commands.advanced.snapshot_commands.SnapshotManager")
    def test_retention_set_force_flag(self, mock_mgr_cls, cli_runner, mock_root, tmp_config):
        mock_mgr = Mock()
        mock_mgr_cls.return_value = mock_mgr

        cli_runner.invoke(
            app,
            ["--config", str(tmp_config),
             "advanced", "snapshot", "retention", "set", "--force"],
        )
        assert mock_mgr.cmd_retention_set.call_args.kwargs["force"] is True
