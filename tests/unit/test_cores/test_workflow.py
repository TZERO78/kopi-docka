"""
End-to-end workflow tests for backup and restore operations.

Tests the complete backup/restore workflows with mocked dependencies to verify
that all steps execute in the correct order and error handling works properly.
"""

import pytest
from datetime import datetime
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch, Mock, MagicMock, call
from concurrent.futures import TimeoutError as FuturesTimeoutError

from kopi_docka.cores.backup_manager import BackupManager
from kopi_docka.types import BackupUnit, ContainerInfo, VolumeInfo
from kopi_docka.helpers.constants import (
    BACKUP_SCOPE_MINIMAL,
    BACKUP_SCOPE_STANDARD,
    BACKUP_SCOPE_FULL,
)


def make_mock_config(tmp_path) -> Mock:
    """Create a mock Config object for workflow testing."""
    config = Mock()
    config.parallel_workers = 2
    config.getint.return_value = 30  # Default timeout
    config.getlist.return_value = []  # No exclude patterns
    config.getboolean.return_value = False  # No DR bundle by default
    config.backup_base_path = tmp_path / "kopi-docka-test"
    return config


def make_backup_manager(tmp_path) -> BackupManager:
    """Create a BackupManager with mocked dependencies."""
    manager = BackupManager.__new__(BackupManager)
    manager.config = make_mock_config(tmp_path)
    manager.repo = Mock()
    manager.repo.create_snapshot.return_value = "snap123"
    manager.policy_manager = Mock()
    manager.hooks_manager = Mock()
    manager.hooks_manager.execute_pre_backup.return_value = True
    manager.hooks_manager.execute_post_backup.return_value = True
    manager.hooks_manager.get_executed_hooks.return_value = []
    manager.max_workers = 2
    manager.stop_timeout = 30
    manager.start_timeout = 60
    manager.exclude_patterns = []
    return manager


# =============================================================================
# Backup Workflow Tests
# =============================================================================


@pytest.mark.unit
class TestBackupWorkflow:
    """End-to-end backup workflow tests with mocked dependencies."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_complete_backup_flow_success(self, mock_run, backup_unit_factory, tmp_path):
        """Full backup flow: hooks → stop → backup → start → metadata."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(name="teststack", containers=2, volumes=2)

        # Track call order
        call_order = []

        # Mock hooks
        manager.hooks_manager.execute_pre_backup.side_effect = lambda x: (
            call_order.append("pre_hook"),
            True,
        )[1]
        manager.hooks_manager.execute_post_backup.side_effect = lambda x: (
            call_order.append("post_hook"),
            True,
        )[1]

        # Mock container operations
        def track_stop(containers, service_handler):
            call_order.append("stop")

        def track_start(containers, service_handler):
            call_order.append("start")

        # Mock volume backup
        def track_backup(*args):
            call_order.append("backup")
            return "snap123"

        with patch.object(manager, "_stop_containers", side_effect=track_stop):
            with patch.object(manager, "_start_containers", side_effect=track_start):
                with patch.object(manager, "_backup_volume", side_effect=track_backup):
                    with patch.object(manager, "_save_metadata"):
                        with patch.object(manager, "_ensure_policies"):
                            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Verify execution order
        assert call_order == [
            "pre_hook",
            "stop",
            "backup",
            "backup",  # 2 volumes
            "start",
            "post_hook",
        ]

        # Verify metadata
        assert metadata.success is True
        assert metadata.unit_name == "teststack"
        assert metadata.backup_id is not None
        assert metadata.volumes_backed_up == 2
        assert len(metadata.errors) == 0
        assert metadata.backup_scope == BACKUP_SCOPE_MINIMAL

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_pre_hook_failure_aborts(self, mock_run, backup_unit_factory, tmp_path):
        """Backup aborts if pre-backup hook fails."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        manager.hooks_manager.execute_pre_backup.return_value = False
        unit = backup_unit_factory()

        with patch.object(manager, "_stop_containers") as mock_stop:
            with patch.object(manager, "_backup_volume") as mock_backup:
                with patch.object(manager, "_start_containers") as mock_start:
                    with patch.object(manager, "_ensure_policies"):
                        metadata = manager.backup_unit(unit)

        # Verify backup was aborted (stop and backup not called)
        mock_stop.assert_not_called()
        mock_backup.assert_not_called()
        # Note: _start_containers IS called because it's in finally block (safety feature)
        mock_start.assert_called_once()

        # Verify metadata shows failure
        assert metadata.success is False
        assert any("Pre-backup hook failed" in e for e in metadata.errors)
        assert metadata.volumes_backed_up == 0

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_container_stop_failure(self, mock_run, backup_unit_factory, tmp_path):
        """Handles container stop failures gracefully."""
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(containers=2)

        # Make run_command fail for docker stop
        from kopi_docka.helpers.ui_utils import SubprocessError

        mock_run.side_effect = SubprocessError("docker stop failed", "", "Container not found")

        start_called = False

        def track_start(containers, service_handler):
            nonlocal start_called
            start_called = True

        with patch.object(manager, "_start_containers", side_effect=track_start):
            with patch.object(manager, "_backup_volume", return_value="snap123"):
                with patch.object(manager, "_save_metadata"):
                    with patch.object(manager, "_ensure_policies"):
                        metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Containers should still be started even if stop failed
        assert start_called is True
        # Backup should continue (stop failure is logged but not fatal)
        assert metadata.volumes_backed_up == 1

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_volume_backup_partial_failure(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        """Continues with other volumes if one fails."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(volumes=3)

        call_count = [0]

        def partial_failure(*args):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Volume 2 backup failed")
            return f"snap{call_count[0]}"

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_backup_volume", side_effect=partial_failure):
                    with patch.object(manager, "_save_metadata"):
                        with patch.object(manager, "_ensure_policies"):
                            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # 2 volumes succeeded, 1 failed
        assert metadata.volumes_backed_up == 2
        assert len(metadata.errors) == 1
        assert any("Volume 2 backup failed" in e for e in metadata.errors)
        # Overall success is False because there were errors
        assert metadata.success is False

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_container_start_failure(self, mock_run, backup_unit_factory, tmp_path):
        """Reports but doesn't fail if container restart fails."""
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(containers=2)

        # Make docker start command fail (run_command will fail)
        from kopi_docka.helpers.ui_utils import SubprocessError

        def run_cmd_side_effect(cmd, *args, **kwargs):
            if "start" in cmd:
                raise SubprocessError("docker start failed", "", "Error starting")
            return CompletedProcess([], 0, stdout="", stderr="")

        mock_run.side_effect = run_cmd_side_effect

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_backup_volume", return_value="snap123"):
                with patch.object(manager, "_save_metadata"):
                    with patch.object(manager, "_ensure_policies"):
                        # Should not raise, error is caught in _start_containers
                        metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Backup itself succeeded
        assert metadata.volumes_backed_up == 1
        # Start failure is logged but doesn't affect metadata.success if backup succeeded
        assert metadata.success is True  # No errors added to metadata

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_id_consistent_across_snapshots(self, mock_run, backup_unit_factory, tmp_path):
        """All snapshots in one backup share same backup_id."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(volumes=3)

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_save_metadata"):
                    with patch.object(manager, "_ensure_policies"):
                        metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Extract backup_id from all snapshot calls
        backup_ids = set()
        for call_args in manager.repo.create_snapshot.call_args_list:
            if len(call_args[0]) > 1:
                tags = call_args[0][1]
            else:
                tags = call_args[1].get("tags", {})
            if "backup_id" in tags:
                backup_ids.add(tags["backup_id"])

        # All snapshots should have the same backup_id
        if backup_ids:  # If any snapshots were created
            assert len(backup_ids) == 1
            # Should match the metadata backup_id
            assert metadata.backup_id in backup_ids

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_with_empty_unit(self, mock_run, tmp_path):
        """Handles unit with no containers/volumes."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)

        # Create empty unit
        unit = BackupUnit(
            name="empty-unit",
            type="standalone",
            containers=[],
            volumes=[],
            compose_files=[],
        )

        with patch.object(manager, "_save_metadata"):
            with patch.object(manager, "_ensure_policies"):
                metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should complete successfully
        assert metadata.success is True
        assert metadata.volumes_backed_up == 0
        assert len(metadata.errors) == 0

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_scope_minimal_skips_networks(self, mock_run, backup_unit_factory, tmp_path):
        """Minimal scope only backs up volumes."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory()

        with patch.object(manager, "_backup_recipes") as mock_recipes:
            with patch.object(manager, "_backup_networks") as mock_networks:
                with patch.object(manager, "_stop_containers"):
                    with patch.object(manager, "_start_containers"):
                        with patch.object(manager, "_backup_volume", return_value="snap123"):
                            with patch.object(manager, "_save_metadata"):
                                with patch.object(manager, "_ensure_policies"):
                                    metadata = manager.backup_unit(
                                        unit, backup_scope=BACKUP_SCOPE_MINIMAL
                                    )

        # Recipes and networks should not be backed up
        mock_recipes.assert_not_called()
        mock_networks.assert_not_called()
        assert metadata.backup_scope == BACKUP_SCOPE_MINIMAL

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_scope_full_includes_all(self, mock_run, backup_unit_factory, tmp_path):
        """Full scope includes recipes, networks, volumes."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory()

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap") as mock_recipes:
            with patch.object(
                manager, "_backup_networks", return_value=("net_snap", 2)
            ) as mock_networks:
                with patch.object(manager, "_stop_containers"):
                    with patch.object(manager, "_start_containers"):
                        with patch.object(manager, "_backup_volume", return_value="vol_snap"):
                            with patch.object(manager, "_save_metadata"):
                                with patch.object(manager, "_ensure_policies"):
                                    metadata = manager.backup_unit(
                                        unit, backup_scope=BACKUP_SCOPE_FULL
                                    )

        # All backup types should be called
        mock_recipes.assert_called_once()
        mock_networks.assert_called_once()
        assert metadata.backup_scope == BACKUP_SCOPE_FULL

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_post_hook_failure(self, mock_run, backup_unit_factory, tmp_path):
        """Post-hook failure adds error but doesn't prevent backup completion."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        manager.hooks_manager.execute_post_backup.return_value = False
        unit = backup_unit_factory()

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_backup_volume", return_value="snap123"):
                    with patch.object(manager, "_save_metadata"):
                        with patch.object(manager, "_ensure_policies"):
                            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Backup completed but with error
        assert metadata.volumes_backed_up == 1
        assert any("Post-backup hook failed" in e for e in metadata.errors)
        assert metadata.success is False  # Errors present

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_exception_still_restarts_containers(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        """Containers are restarted even if backup raises exception."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(containers=2)

        start_called = False

        def track_start(containers, service_handler):
            nonlocal start_called
            start_called = True

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_backup_volume", side_effect=Exception("Catastrophic")):
                with patch.object(manager, "_start_containers", side_effect=track_start):
                    with patch.object(manager, "_save_metadata"):
                        with patch.object(manager, "_ensure_policies"):
                            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Containers must be restarted (finally block)
        assert start_called is True
        assert metadata.success is False
        assert len(metadata.errors) > 0

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_metadata_saved(self, mock_run, backup_unit_factory, tmp_path):
        """Metadata is saved after backup completion."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory()

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_backup_volume", return_value="snap123"):
                    with patch.object(manager, "_save_metadata") as mock_save:
                        with patch.object(manager, "_ensure_policies"):
                            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # _save_metadata should be called with the metadata object
        mock_save.assert_called_once()
        saved_metadata = mock_save.call_args[0][0]
        assert saved_metadata.unit_name == unit.name
        assert saved_metadata.backup_id == metadata.backup_id

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_hooks_executed_tracked(self, mock_run, backup_unit_factory, tmp_path):
        """Executed hooks are tracked in metadata."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        manager.hooks_manager.get_executed_hooks.return_value = [
            "pre-backup: /scripts/pre.sh",
            "post-backup: /scripts/post.sh",
        ]
        unit = backup_unit_factory()

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_backup_volume", return_value="snap123"):
                    with patch.object(manager, "_save_metadata"):
                        with patch.object(manager, "_ensure_policies"):
                            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.hooks_executed == [
            "pre-backup: /scripts/pre.sh",
            "post-backup: /scripts/post.sh",
        ]

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_parallel_volume_backup(self, mock_run, backup_unit_factory, tmp_path):
        """Multiple volumes are backed up in parallel."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        manager.max_workers = 2
        unit = backup_unit_factory(volumes=4)

        backup_calls = []

        def track_backup(volume, unit, backup_id, backup_scope):
            backup_calls.append(volume.name)
            return f"snap_{volume.name}"

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_backup_volume", side_effect=track_backup):
                    with patch.object(manager, "_save_metadata"):
                        with patch.object(manager, "_ensure_policies"):
                            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # All 4 volumes should be backed up
        assert len(backup_calls) == 4
        assert metadata.volumes_backed_up == 4
        assert metadata.success is True

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_dr_bundle_update_on_success(self, mock_run, backup_unit_factory, tmp_path):
        """DR bundle is updated after successful backup if configured."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory()

        # Mock DR manager at the source module location
        mock_dr_manager = Mock()

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_backup_volume", return_value="snap123"):
                    with patch.object(manager, "_save_metadata"):
                        with patch.object(manager, "_ensure_policies"):
                            with patch(
                                "kopi_docka.cores.disaster_recovery_manager.DisasterRecoveryManager",
                                return_value=mock_dr_manager,
                            ):
                                metadata = manager.backup_unit(
                                    unit,
                                    backup_scope=BACKUP_SCOPE_MINIMAL,
                                    update_recovery_bundle=True,
                                )

        # DR bundle should be created
        mock_dr_manager.create_recovery_bundle.assert_called_once()

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_flow_dr_bundle_skipped_on_failure(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        """DR bundle is NOT updated if backup failed."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory()

        # Force backup failure
        manager.hooks_manager.execute_pre_backup.return_value = False

        mock_dr_manager = Mock()

        with patch.object(manager, "_ensure_policies"):
            with patch.object(manager, "_start_containers"):
                with patch(
                    "kopi_docka.cores.disaster_recovery_manager.DisasterRecoveryManager",
                    return_value=mock_dr_manager,
                ):
                    metadata = manager.backup_unit(
                        unit,
                        backup_scope=BACKUP_SCOPE_MINIMAL,
                        update_recovery_bundle=True,
                    )

        # DR bundle should NOT be created (backup failed)
        mock_dr_manager.create_recovery_bundle.assert_not_called()
        assert metadata.success is False
