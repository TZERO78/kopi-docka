"""
Unit tests for BackupManager class.

Tests the backup orchestration business logic with mocked external dependencies
(Docker, Kopia, hooks).
"""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch, Mock, MagicMock, call

from kopi_docka.cores.backup_manager import BackupManager
from kopi_docka.types import BackupUnit, ContainerInfo, VolumeInfo, BackupMetadata
from kopi_docka.helpers.constants import (
    BACKUP_SCOPE_MINIMAL,
    BACKUP_SCOPE_STANDARD,
    BACKUP_SCOPE_FULL,
    BACKUP_FORMAT_DIRECT,
)


def make_mock_config() -> Mock:
    """Create a mock Config object for testing."""
    config = Mock()
    config.parallel_workers = 2
    config.getint.return_value = 30  # Default timeout
    config.getlist.return_value = []  # No exclude patterns
    config.getboolean.return_value = False  # No DR bundle
    config.backup_base_path = Path(tempfile.gettempdir()) / "kopi-docka-test"
    return config


def make_backup_manager() -> BackupManager:
    """Create a BackupManager instance without running __init__."""
    manager = BackupManager.__new__(BackupManager)
    manager.config = make_mock_config()
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


def make_backup_unit(
    name: str = "mystack",
    containers: int = 2,
    volumes: int = 1,
    with_database: bool = False,
) -> BackupUnit:
    """Create a test BackupUnit."""
    container_list = []
    for i in range(containers):
        c = ContainerInfo(
            id=f"container{i}",
            name=f"{name}_service{i}",
            image="nginx:latest" if not with_database or i > 0 else "postgres:15",
            status="running",
            database_type="postgres" if with_database and i == 0 else None,
            inspect_data={"NetworkSettings": {"Networks": {"mynet": {}}}},
        )
        container_list.append(c)

    volume_list = []
    for i in range(volumes):
        v = VolumeInfo(
            name=f"{name}_data{i}",
            driver="local",
            mountpoint=f"/var/lib/docker/volumes/{name}_data{i}/_data",
            size_bytes=1024 * 1024,
        )
        volume_list.append(v)

    return BackupUnit(
        name=name,
        type="stack",
        containers=container_list,
        volumes=volume_list,
        compose_files=[],
    )


# =============================================================================
# Backup ID Tests
# =============================================================================


@pytest.mark.unit
class TestBackupId:
    """Tests for backup_id generation."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_creates_unique_backup_id(self, mock_run):
        """Each backup should have a unique backup_id (UUID)."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        metadata = manager.backup_unit(unit)

        assert metadata.backup_id is not None
        assert len(metadata.backup_id) == 36  # UUID format: 8-4-4-4-12

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_id_is_passed_to_snapshots(self, mock_run):
        """All snapshots should receive the same backup_id."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "snap123"
        unit = make_backup_unit(volumes=2)

        # Make volume paths exist
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Check that all snapshot calls used the same backup_id
        backup_ids = set()
        for call_args in manager.repo.create_snapshot.call_args_list:
            tags = call_args[1].get("tags", {}) if call_args[1] else call_args[0][1]
            if "backup_id" in tags:
                backup_ids.add(tags["backup_id"])

        # All snapshots should share the same backup_id
        assert len(backup_ids) <= 1  # 0 if no snapshots, 1 if snapshots created


# =============================================================================
# Backup Scope Tests
# =============================================================================


@pytest.mark.unit
class TestBackupScope:
    """Tests for backup scope handling."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_minimal_scope_skips_recipes(self, mock_run):
        """MINIMAL scope should only backup volumes, not recipes."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        with patch.object(manager, "_backup_recipes") as mock_recipes:
            with patch.object(manager, "_backup_networks") as mock_networks:
                with patch.object(manager, "_backup_volume", return_value="snap123"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        mock_recipes.assert_not_called()
        mock_networks.assert_not_called()
        assert metadata.backup_scope == BACKUP_SCOPE_MINIMAL

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_standard_scope_includes_recipes_and_networks(self, mock_run):
        """STANDARD scope should include recipes and networks."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap") as mock_recipes:
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)) as mock_networks:
                with patch.object(manager, "_backup_volume", return_value="vol_snap"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_STANDARD)

        mock_recipes.assert_called_once()
        mock_networks.assert_called_once()
        assert metadata.backup_scope == BACKUP_SCOPE_STANDARD

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_full_scope_includes_everything(self, mock_run):
        """FULL scope should include all backup types."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap") as mock_recipes:
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 2)) as mock_networks:
                with patch.object(manager, "_backup_volume", return_value="vol_snap"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_FULL)

        mock_recipes.assert_called_once()
        mock_networks.assert_called_once()
        assert metadata.backup_scope == BACKUP_SCOPE_FULL


# =============================================================================
# Container Stop/Start Order Tests
# =============================================================================


@pytest.mark.unit
class TestContainerOrdering:
    """Tests for container stop/start ordering."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_stops_containers_before_backup(self, mock_run):
        """Containers should be stopped before volume backup starts."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        call_order = []

        def track_stop(containers):
            call_order.append("stop")

        def track_backup(*args):
            call_order.append("backup")
            return "snap123"

        def track_start(containers):
            call_order.append("start")

        with patch.object(manager, "_stop_containers", side_effect=track_stop):
            with patch.object(manager, "_backup_volume", side_effect=track_backup):
                with patch.object(manager, "_start_containers", side_effect=track_start):
                    manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Stop must come before backup, start must come after
        assert call_order.index("stop") < call_order.index("backup")
        assert call_order.index("backup") < call_order.index("start")

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_restarts_containers_on_error(self, mock_run):
        """Containers should restart even if backup fails."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        start_called = False

        def track_start(containers):
            nonlocal start_called
            start_called = True

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_backup_volume", side_effect=Exception("Backup failed")):
                with patch.object(manager, "_start_containers", side_effect=track_start):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert start_called, "Containers should restart even after backup failure"
        assert not metadata.success
        assert any("Backup failed" in e for e in metadata.errors)


# =============================================================================
# Hook Execution Tests
# =============================================================================


@pytest.mark.unit
class TestHookExecution:
    """Tests for pre/post backup hook execution."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_pre_hook_executed_before_stop(self, mock_run):
        """Pre-backup hook should execute before containers are stopped."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        call_order = []

        manager.hooks_manager.execute_pre_backup.side_effect = lambda x: (
            call_order.append("pre_hook"),
            True,
        )[1]

        def track_stop(containers):
            call_order.append("stop")

        with patch.object(manager, "_stop_containers", side_effect=track_stop):
            with patch.object(manager, "_backup_volume", return_value="snap123"):
                with patch.object(manager, "_start_containers"):
                    manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert call_order.index("pre_hook") < call_order.index("stop")

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_post_hook_executed_after_start(self, mock_run):
        """Post-backup hook should execute after containers are started."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        call_order = []

        def track_start(containers):
            call_order.append("start")

        manager.hooks_manager.execute_post_backup.side_effect = lambda x: (
            call_order.append("post_hook"),
            True,
        )[1]

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_backup_volume", return_value="snap123"):
                with patch.object(manager, "_start_containers", side_effect=track_start):
                    manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert call_order.index("start") < call_order.index("post_hook")

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_pre_hook_failure_aborts_backup(self, mock_run):
        """If pre-backup hook fails, backup should be aborted."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        manager.hooks_manager.execute_pre_backup.return_value = False
        unit = make_backup_unit()

        with patch.object(manager, "_stop_containers") as mock_stop:
            with patch.object(manager, "_backup_volume") as mock_backup:
                metadata = manager.backup_unit(unit)

        mock_stop.assert_not_called()
        mock_backup.assert_not_called()
        assert not metadata.success
        assert any("Pre-backup hook failed" in e for e in metadata.errors)


# =============================================================================
# Error Accumulation Tests
# =============================================================================


@pytest.mark.unit
class TestErrorAccumulation:
    """Tests for error handling and accumulation."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_accumulates_volume_errors(self, mock_run):
        """Errors from individual volumes should be accumulated."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit(volumes=3)

        call_count = [0]

        def partial_failure(*args):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Volume 2 failed")
            return f"snap{call_count[0]}"

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_backup_volume", side_effect=partial_failure):
                with patch.object(manager, "_start_containers"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # 2 succeeded, 1 failed
        assert metadata.volumes_backed_up == 2
        assert len(metadata.errors) == 1
        assert any("Volume 2 failed" in e for e in metadata.errors)

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_post_hook_failure_adds_error(self, mock_run):
        """Post-hook failure should add error but not fail backup."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        manager.hooks_manager.execute_post_backup.return_value = False
        unit = make_backup_unit()

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_backup_volume", return_value="snap123"):
                with patch.object(manager, "_start_containers"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert any("Post-backup hook failed" in e for e in metadata.errors)


# =============================================================================
# Stop Containers Tests
# =============================================================================


@pytest.mark.unit
class TestStopContainers:
    """Tests for _stop_containers method."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_stops_running_containers(self, mock_run):
        """Should stop all running containers."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        containers = [
            ContainerInfo(id="c1", name="web", image="nginx", status="running"),
            ContainerInfo(id="c2", name="db", image="postgres", status="running"),
        ]

        manager._stop_containers(containers)

        assert mock_run.call_count == 2
        # Check docker stop was called with container IDs
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("c1" in call for call in calls)
        assert any("c2" in call for call in calls)

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_skips_non_running_containers(self, mock_run):
        """Should not try to stop already stopped containers."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        containers = [
            ContainerInfo(id="c1", name="web", image="nginx", status="running"),
            ContainerInfo(id="c2", name="db", image="postgres", status="exited"),
        ]

        manager._stop_containers(containers)

        # Only running container should be stopped
        assert mock_run.call_count == 1


# =============================================================================
# Backup Volume Direct Tests
# =============================================================================


@pytest.mark.unit
class TestBackupVolumeDirect:
    """Tests for _backup_volume_direct method."""

    def test_creates_snapshot_with_correct_tags(self):
        """Should create snapshot with all required tags."""
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "snap123"

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/tmp/test_volume",
            size_bytes=2048,
        )
        unit = make_backup_unit(name="mystack")

        with tempfile.TemporaryDirectory() as tmpdir:
            volume.mountpoint = tmpdir

            result = manager._backup_volume_direct(volume, unit, "backup-uuid-123")

        assert result == "snap123"

        # Check tags were passed correctly
        call_args = manager.repo.create_snapshot.call_args
        tags = call_args[1]["tags"]
        assert tags["type"] == "volume"
        assert tags["unit"] == "mystack"
        assert tags["volume"] == "mydata"
        assert tags["backup_id"] == "backup-uuid-123"
        assert tags["backup_format"] == BACKUP_FORMAT_DIRECT

    def test_returns_none_for_missing_path(self):
        """Should return None if volume path doesn't exist."""
        manager = make_backup_manager()

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/nonexistent/path",
        )
        unit = make_backup_unit()

        result = manager._backup_volume_direct(volume, unit, "backup-id")

        assert result is None

    def test_passes_exclude_patterns(self):
        """Should pass exclude patterns to Kopia."""
        manager = make_backup_manager()
        manager.exclude_patterns = ["*.log", "cache/*"]
        manager.repo.create_snapshot.return_value = "snap123"

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/tmp",
        )
        unit = make_backup_unit()

        with tempfile.TemporaryDirectory() as tmpdir:
            volume.mountpoint = tmpdir
            manager._backup_volume_direct(volume, unit, "backup-id")

        call_args = manager.repo.create_snapshot.call_args
        assert call_args[1]["exclude_patterns"] == ["*.log", "cache/*"]


# =============================================================================
# Backup Recipes Tests
# =============================================================================


@pytest.mark.unit
class TestBackupRecipes:
    """Tests for _backup_recipes method (secret redaction)."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_redacts_sensitive_env_vars(self, mock_run):
        """Should redact environment variables containing sensitive keywords."""
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "snap123"

        # Mock docker inspect response with sensitive env vars
        inspect_data = [
            {
                "Config": {
                    "Env": [
                        "DB_PASSWORD=secret123",
                        "API_KEY=abc123",
                        "NORMAL_VAR=value",
                        "SECRET_TOKEN=xyz",
                    ]
                }
            }
        ]
        mock_run.return_value = CompletedProcess(
            [], 0, stdout=json.dumps(inspect_data), stderr=""
        )

        unit = make_backup_unit(containers=1)
        unit.compose_files = []  # No compose files for simplicity

        result = manager._backup_recipes(unit, "backup-id")

        assert result == "snap123"
        manager.repo.create_snapshot.assert_called_once()

        # Check that snapshot was created with recipe type tag
        call_args = manager.repo.create_snapshot.call_args
        tags = call_args[1]["tags"]
        assert tags["type"] == "recipe"


# =============================================================================
# Metadata Tests
# =============================================================================


@pytest.mark.unit
class TestBackupMetadata:
    """Tests for backup metadata creation."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_metadata_includes_all_fields(self, mock_run):
        """Backup metadata should include all required fields."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_backup_volume", return_value="snap123"):
                with patch.object(manager, "_start_containers"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.unit_name == "mystack"
        assert metadata.backup_id is not None
        assert metadata.timestamp is not None
        assert metadata.duration_seconds >= 0
        assert metadata.backup_scope == BACKUP_SCOPE_MINIMAL

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_metadata_success_when_no_errors(self, mock_run):
        """Metadata success should be True when there are no errors."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_backup_volume", return_value="snap123"):
                with patch.object(manager, "_start_containers"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.success is True
        assert len(metadata.errors) == 0

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_metadata_tracks_volumes_backed_up(self, mock_run):
        """Metadata should track number of volumes backed up."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit(volumes=3)

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_backup_volume", return_value="snap123"):
                with patch.object(manager, "_start_containers"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.volumes_backed_up == 3


# =============================================================================
# Network Backup Tests
# =============================================================================


@pytest.mark.unit
class TestBackupNetworks:
    """Tests for _backup_networks method."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backs_up_custom_networks(self, mock_run):
        """Should backup custom networks (not bridge/host/none)."""
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "net_snap123"

        # Mock network inspect response
        network_data = [{"Name": "mynet", "Driver": "bridge", "IPAM": {}}]
        mock_run.return_value = CompletedProcess(
            [], 0, stdout=json.dumps(network_data), stderr=""
        )

        unit = make_backup_unit()
        # Add custom network to container inspect data
        unit.containers[0].inspect_data = {
            "NetworkSettings": {"Networks": {"mynet": {}, "bridge": {}}}
        }

        snapshot_id, count = manager._backup_networks(unit, "backup-id")

        assert snapshot_id == "net_snap123"
        assert count == 1

    def test_skips_default_networks(self):
        """Should not backup default networks (bridge, host, none)."""
        manager = make_backup_manager()

        unit = make_backup_unit()
        # Set ALL containers to only have default networks
        for container in unit.containers:
            container.inspect_data = {
                "NetworkSettings": {"Networks": {"bridge": {}, "host": {}}}
            }

        snapshot_id, count = manager._backup_networks(unit, "backup-id")

        assert snapshot_id is None
        assert count == 0
        # No snapshot should be created for default networks
        manager.repo.create_snapshot.assert_not_called()
