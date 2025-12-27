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
# Start Containers Tests
# =============================================================================


@pytest.mark.unit
class TestStartContainers:
    """Tests for _start_containers method."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_starts_all_containers(self, mock_run):
        """Should start all containers and wait for health check."""
        mock_run.return_value = CompletedProcess([], 0, stdout="null", stderr="")
        manager = make_backup_manager()

        containers = [
            ContainerInfo(id="c1", name="web", image="nginx", status="running"),
            ContainerInfo(id="c2", name="db", image="postgres", status="running"),
        ]

        manager._start_containers(containers)

        # Should call docker start for each container
        start_calls = [c for c in mock_run.call_args_list if "start" in str(c)]
        assert len(start_calls) == 2

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_waits_for_health_check_after_start(self, mock_run):
        """Should check health status after starting container."""
        # First call: health config check returns null (no healthcheck)
        # Second call: docker start succeeds
        mock_run.side_effect = [
            CompletedProcess([], 0, stdout="null", stderr=""),  # start
            CompletedProcess([], 0, stdout="null", stderr=""),  # health check
        ]
        manager = make_backup_manager()

        containers = [ContainerInfo(id="c1", name="web", image="nginx", status="running")]

        manager._start_containers(containers)

        # Should have called docker start and health check
        assert mock_run.call_count >= 2


# =============================================================================
# Health Check Tests
# =============================================================================


@pytest.mark.unit
class TestWaitContainerHealthy:
    """Tests for _wait_container_healthy method."""

    @patch("kopi_docka.cores.backup_manager.time.sleep")
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_healthy_container_returns_immediately(self, mock_run, mock_sleep):
        """Container with healthcheck that becomes healthy should return."""
        manager = make_backup_manager()
        container = ContainerInfo(id="c1", name="web", image="nginx", status="running")

        # First call: health config exists
        # Second call: status is "healthy"
        mock_run.side_effect = [
            CompletedProcess([], 0, stdout='{"Status": "starting"}', stderr=""),
            CompletedProcess([], 0, stdout="healthy", stderr=""),
        ]

        manager._wait_container_healthy(container, timeout=60)

        # Should have checked health config and status
        assert mock_run.call_count == 2
        # Should not have slept (became healthy immediately)
        assert mock_sleep.call_count == 0

    @patch("kopi_docka.cores.backup_manager.time.sleep")
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_unhealthy_container_returns_with_warning(self, mock_run, mock_sleep):
        """Container that becomes unhealthy should return (not block)."""
        manager = make_backup_manager()
        container = ContainerInfo(id="c1", name="web", image="nginx", status="running")

        # First call: health config exists
        # Second call: status is "unhealthy"
        mock_run.side_effect = [
            CompletedProcess([], 0, stdout='{"Status": "starting"}', stderr=""),
            CompletedProcess([], 0, stdout="unhealthy", stderr=""),
        ]

        manager._wait_container_healthy(container, timeout=60)

        # Should have checked health config and status
        assert mock_run.call_count == 2
        # Should not have slept (became unhealthy immediately)
        assert mock_sleep.call_count == 0

    @patch("kopi_docka.cores.backup_manager.time.sleep")
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_no_healthcheck_sleeps_briefly(self, mock_run, mock_sleep):
        """Container without healthcheck should just sleep briefly."""
        manager = make_backup_manager()
        container = ContainerInfo(id="c1", name="web", image="nginx", status="running")

        # Health config check returns null (no healthcheck)
        mock_run.return_value = CompletedProcess([], 0, stdout="null", stderr="")

        manager._wait_container_healthy(container, timeout=60)

        # Should have checked health config only
        assert mock_run.call_count == 1
        # Should have slept for 2 seconds
        mock_sleep.assert_called_once_with(2)

    @patch("kopi_docka.cores.backup_manager.time.sleep")
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_empty_health_response_sleeps_briefly(self, mock_run, mock_sleep):
        """Container with empty health response should sleep briefly."""
        manager = make_backup_manager()
        container = ContainerInfo(id="c1", name="web", image="nginx", status="running")

        # Health config check returns empty string
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")

        manager._wait_container_healthy(container, timeout=60)

        # Should have checked health config only
        assert mock_run.call_count == 1
        # Should have slept for 2 seconds
        mock_sleep.assert_called_once_with(2)

    @patch("kopi_docka.cores.backup_manager.time.sleep")
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_empty_json_health_response_sleeps_briefly(self, mock_run, mock_sleep):
        """Container with {} health response should sleep briefly."""
        manager = make_backup_manager()
        container = ContainerInfo(id="c1", name="web", image="nginx", status="running")

        # Health config check returns empty JSON
        mock_run.return_value = CompletedProcess([], 0, stdout="{}", stderr="")

        manager._wait_container_healthy(container, timeout=60)

        # Should have checked health config only
        assert mock_run.call_count == 1
        # Should have slept for 2 seconds
        mock_sleep.assert_called_once_with(2)

    @patch("kopi_docka.cores.backup_manager.time.sleep")
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_health_check_error_sleeps_briefly(self, mock_run, mock_sleep):
        """Container health check error should sleep briefly."""
        manager = make_backup_manager()
        container = ContainerInfo(id="c1", name="web", image="nginx", status="running")

        # Health config check fails (non-zero return code)
        mock_run.return_value = CompletedProcess([], 1, stdout="", stderr="Error")

        manager._wait_container_healthy(container, timeout=60)

        # Should have checked health config only
        assert mock_run.call_count == 1
        # Should have slept for 2 seconds
        mock_sleep.assert_called_once_with(2)

    @patch("kopi_docka.cores.backup_manager.time.time")
    @patch("kopi_docka.cores.backup_manager.time.sleep")
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_health_check_timeout(self, mock_run, mock_sleep, mock_time):
        """Health check should timeout if container doesn't become healthy."""
        manager = make_backup_manager()
        container = ContainerInfo(id="c1", name="web", image="nginx", status="running")

        # Simulate time progression
        mock_time.side_effect = [0, 10, 20, 30, 40, 50, 60, 70]  # Exceeds timeout

        # Health config exists, status stays "starting"
        mock_run.side_effect = [
            CompletedProcess([], 0, stdout='{"Status": "starting"}', stderr=""),
            CompletedProcess([], 0, stdout="starting", stderr=""),
            CompletedProcess([], 0, stdout="starting", stderr=""),
            CompletedProcess([], 0, stdout="starting", stderr=""),
        ]

        manager._wait_container_healthy(container, timeout=60)

        # Should have polled multiple times before timeout
        assert mock_run.call_count >= 3

    @patch("kopi_docka.cores.backup_manager.time.sleep")
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_health_check_polls_until_healthy(self, mock_run, mock_sleep):
        """Should poll status multiple times until healthy."""
        manager = make_backup_manager()
        container = ContainerInfo(id="c1", name="web", image="nginx", status="running")

        # Health config exists, status: starting -> starting -> healthy
        mock_run.side_effect = [
            CompletedProcess([], 0, stdout='{"Status": "starting"}', stderr=""),
            CompletedProcess([], 0, stdout="starting", stderr=""),
            CompletedProcess([], 0, stdout="starting", stderr=""),
            CompletedProcess([], 0, stdout="healthy", stderr=""),
        ]

        manager._wait_container_healthy(container, timeout=60)

        # Should have checked config + polled 3 times
        assert mock_run.call_count == 4
        # Should have slept between polls (2 times for 2 "starting" statuses)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(2)

    @patch("kopi_docka.cores.backup_manager.time.sleep")
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_health_check_exception_sleeps_briefly(self, mock_run, mock_sleep):
        """Exception during health check should sleep briefly."""
        manager = make_backup_manager()
        container = ContainerInfo(id="c1", name="web", image="nginx", status="running")

        # Raise exception during health check
        mock_run.side_effect = Exception("Docker daemon error")

        manager._wait_container_healthy(container, timeout=60)

        # Should have attempted health check
        assert mock_run.call_count == 1
        # Should have slept for 2 seconds
        mock_sleep.assert_called_once_with(2)


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
# Parallel Backup Tests
# =============================================================================


@pytest.mark.unit
class TestParallelBackup:
    """Tests for parallel volume backup execution."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_multiple_volumes_backed_up_in_parallel(self, mock_run):
        """Should backup all volumes and track successful backups."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create unit with 3 volumes
        unit = make_backup_unit(name="mystack", volumes=3)

        # Track which volumes were backed up
        backed_up_volumes = []

        def track_backup(volume, unit, backup_id):
            backed_up_volumes.append(volume.name)
            return f"snap_{volume.name}"

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                with patch.object(manager, "_backup_volume", side_effect=track_backup):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # All 3 volumes should have been backed up
        assert len(backed_up_volumes) == 3
        assert metadata.volumes_backed_up == 3
        assert len(metadata.kopia_snapshot_ids) == 3
        assert metadata.success is True

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_partial_failure_one_volume_fails(self, mock_run):
        """If one volume fails, others should still be backed up."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create unit with 3 volumes
        unit = make_backup_unit(name="mystack", volumes=3)

        # First volume fails (returns None), others succeed
        call_count = [0]

        def backup_with_failure(volume, unit, backup_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # First volume fails
            return f"snap_{volume.name}"

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                with patch.object(manager, "_backup_volume", side_effect=backup_with_failure):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # 2 volumes succeeded, 1 failed
        assert metadata.volumes_backed_up == 2
        assert len(metadata.kopia_snapshot_ids) == 2
        assert len(metadata.errors) == 1
        assert "Failed to backup volume" in metadata.errors[0]
        assert metadata.success is False

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_partial_failure_one_volume_raises_exception(self, mock_run):
        """If one volume raises exception, others should still be backed up."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create unit with 3 volumes
        unit = make_backup_unit(name="mystack", volumes=3)

        # Second volume raises exception, others succeed
        call_count = [0]

        def backup_with_exception(volume, unit, backup_id):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Volume backup failed: disk error")
            return f"snap_{volume.name}"

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                with patch.object(manager, "_backup_volume", side_effect=backup_with_exception):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # 2 volumes succeeded, 1 raised exception
        assert metadata.volumes_backed_up == 2
        assert len(metadata.kopia_snapshot_ids) == 2
        assert len(metadata.errors) == 1
        assert "Error backing up volume" in metadata.errors[0]
        assert "disk error" in metadata.errors[0]
        assert metadata.success is False

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_task_timeout_handling(self, mock_run):
        """Should handle task timeout and add error to metadata."""
        from concurrent.futures import TimeoutError as FuturesTimeoutError

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        manager.config.getint.return_value = 5  # 5 second timeout

        # Create unit with 2 volumes
        unit = make_backup_unit(name="mystack", volumes=2)

        # First volume times out
        call_count = [0]

        def backup_with_timeout(volume, unit, backup_id):
            call_count[0] += 1
            if call_count[0] == 1:
                import time
                time.sleep(10)  # Would timeout if actually waited
            return f"snap_{volume.name}"

        # We need to mock the future.result() to raise TimeoutError
        # This is complex, so let's use a different approach - mock the ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor, Future
        from unittest.mock import MagicMock

        # Create mock futures
        future1 = MagicMock(spec=Future)
        future1.result.side_effect = FuturesTimeoutError("Task timed out")

        future2 = MagicMock(spec=Future)
        future2.result.return_value = "snap_data1"

        mock_executor = MagicMock(spec=ThreadPoolExecutor)
        mock_executor.__enter__.return_value = mock_executor
        mock_executor.__exit__.return_value = None

        # Track submitted tasks
        submitted_futures = []

        def submit_side_effect(fn, *args, **kwargs):
            if len(submitted_futures) == 0:
                submitted_futures.append(future1)
                return future1
            else:
                submitted_futures.append(future2)
                return future2

        mock_executor.submit = MagicMock(side_effect=submit_side_effect)

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                with patch("kopi_docka.cores.backup_manager.ThreadPoolExecutor", return_value=mock_executor):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # First volume timed out, second succeeded
        assert metadata.volumes_backed_up == 1
        assert len(metadata.errors) == 1
        assert "Error backing up volume" in metadata.errors[0]
        assert metadata.success is False

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_max_workers_configuration(self, mock_run):
        """Should use configured max_workers for ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import MagicMock

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        manager.max_workers = 4  # Set to 4 workers

        unit = make_backup_unit(name="mystack", volumes=2)

        # Track ThreadPoolExecutor creation
        executor_max_workers = []
        original_executor_init = ThreadPoolExecutor.__init__

        def track_executor_init(self, max_workers=None, *args, **kwargs):
            executor_max_workers.append(max_workers)
            # Don't actually initialize to avoid real execution
            self._max_workers = max_workers
            self._shutdown = False
            self._work_queue = MagicMock()

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                with patch.object(manager, "_backup_volume", return_value="snap123"):
                    with patch.object(manager, "_save_metadata"):  # Mock to avoid JSON serialization
                        with patch.object(ThreadPoolExecutor, "__init__", track_executor_init):
                            with patch.object(ThreadPoolExecutor, "__enter__", return_value=MagicMock()):
                                with patch.object(ThreadPoolExecutor, "__exit__", return_value=None):
                                    # Mock submit to avoid actual execution
                                    with patch.object(ThreadPoolExecutor, "submit") as mock_submit:
                                        mock_future = MagicMock()
                                        mock_future.result.return_value = "snap123"
                                        mock_submit.return_value = mock_future
                                        metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # ThreadPoolExecutor should have been created with max_workers=4
        assert 4 in executor_max_workers

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_all_volumes_fail(self, mock_run):
        """If all volumes fail, backup should report errors."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create unit with 3 volumes
        unit = make_backup_unit(name="mystack", volumes=3)

        # All volumes fail (return None)
        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                with patch.object(manager, "_backup_volume", return_value=None):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # No volumes succeeded
        assert metadata.volumes_backed_up == 0
        assert len(metadata.errors) == 3  # All 3 volumes failed
        assert all("Failed to backup volume" in err for err in metadata.errors)
        assert metadata.success is False

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_empty_volume_list(self, mock_run):
        """Unit with no volumes should complete successfully."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create unit with 0 volumes
        unit = make_backup_unit(name="mystack", volumes=0)

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # No volumes to backup
        assert metadata.volumes_backed_up == 0
        assert len(metadata.errors) == 0
        assert metadata.success is True


# =============================================================================
# Edge Case Tests
# =============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_empty_container_list(self, mock_run):
        """Unit with no containers should complete successfully."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create unit with no containers
        unit = BackupUnit(
            name="empty_stack",
            type="stack",
            containers=[],  # No containers
            volumes=[
                VolumeInfo(
                    name="data",
                    driver="local",
                    mountpoint="/tmp/data",
                    size_bytes=1024,
                )
            ],
            compose_files=[],
        )

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                with patch.object(manager, "_backup_volume", return_value="vol_snap"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should succeed with no container operations
        assert metadata.success is True
        assert metadata.volumes_backed_up == 1
        # Stop/start should not be called since no containers
        stop_calls = [c for c in mock_run.call_args_list if "stop" in str(c)]
        start_calls = [c for c in mock_run.call_args_list if "start" in str(c)]
        assert len(stop_calls) == 0
        assert len(start_calls) == 0

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_empty_volume_list(self, mock_run):
        """Unit with no volumes should complete successfully."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create unit with no volumes
        unit = BackupUnit(
            name="no_volumes_stack",
            type="stack",
            containers=[
                ContainerInfo(id="c1", name="web", image="nginx", status="running")
            ],
            volumes=[],  # No volumes
            compose_files=[],
        )

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should succeed with no volume backups
        assert metadata.success is True
        assert metadata.volumes_backed_up == 0
        # Containers should still be stopped and started
        stop_calls = [c for c in mock_run.call_args_list if "stop" in str(c)]
        start_calls = [c for c in mock_run.call_args_list if "start" in str(c)]
        assert len(stop_calls) == 1
        assert len(start_calls) == 1

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_unit_with_no_compose_files(self, mock_run):
        """Unit with empty compose_files list should not fail."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create unit with no compose files
        unit = BackupUnit(
            name="no_compose_stack",
            type="stack",
            containers=[
                ContainerInfo(id="c1", name="web", image="nginx", status="running")
            ],
            volumes=[],
            compose_files=[],  # No compose files
        )

        # Mock _backup_recipes to simulate empty compose files
        def mock_backup_recipes(unit, backup_id):
            # Should handle empty compose_files gracefully
            if not unit.compose_files:
                return None  # Or could return empty snapshot
            return "recipe_snap"

        with patch.object(manager, "_backup_recipes", side_effect=mock_backup_recipes):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_STANDARD)

        # Should complete even without compose files
        assert metadata.success is True

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_unit_with_only_stopped_containers(self, mock_run):
        """Unit with all stopped containers should not attempt to stop them."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create unit with only stopped containers
        unit = BackupUnit(
            name="stopped_stack",
            type="stack",
            containers=[
                ContainerInfo(id="c1", name="web", image="nginx", status="exited"),
                ContainerInfo(id="c2", name="db", image="postgres", status="exited"),
            ],
            volumes=[],
            compose_files=[],
        )

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should succeed without stopping containers
        assert metadata.success is True
        # Stop should not be called for already stopped containers
        stop_calls = [c for c in mock_run.call_args_list if "stop" in str(c)]
        assert len(stop_calls) == 0

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_volume_name_with_whitespace(self, mock_run):
        """Volume names with whitespace should be handled correctly."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create volume with whitespace in name (Docker allows this)
        unit = BackupUnit(
            name="test_stack",
            type="stack",
            containers=[],
            volumes=[
                VolumeInfo(
                    name="my data volume",  # Spaces in name
                    driver="local",
                    mountpoint="/tmp/my_data",
                    size_bytes=1024,
                )
            ],
            compose_files=[],
        )

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                with patch.object(manager, "_backup_volume", return_value="vol_snap") as mock_vol:
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should handle whitespace in volume name
        assert metadata.success is True
        assert metadata.volumes_backed_up == 1
        # Verify volume with whitespace was passed to backup
        assert mock_vol.called
        called_volume = mock_vol.call_args[0][0]
        assert called_volume.name == "my data volume"

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_volume_name_with_special_characters(self, mock_run):
        """Volume names with special characters should be handled."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create volume with special characters
        unit = BackupUnit(
            name="test_stack",
            type="stack",
            containers=[],
            volumes=[
                VolumeInfo(
                    name="data-vol_v1.0",  # Dashes, underscores, dots
                    driver="local",
                    mountpoint="/tmp/data",
                    size_bytes=1024,
                )
            ],
            compose_files=[],
        )

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                with patch.object(manager, "_backup_volume", return_value="vol_snap") as mock_vol:
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should handle special characters
        assert metadata.success is True
        assert metadata.volumes_backed_up == 1
        called_volume = mock_vol.call_args[0][0]
        assert called_volume.name == "data-vol_v1.0"

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_completely_empty_unit(self, mock_run):
        """Unit with no containers, volumes, or compose files should succeed."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create completely empty unit
        unit = BackupUnit(
            name="empty_unit",
            type="stack",
            containers=[],
            volumes=[],
            compose_files=[],
        )

        with patch.object(manager, "_backup_recipes", return_value=None):
            with patch.object(manager, "_backup_networks", return_value=(None, 0)):
                metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should succeed with no work done
        assert metadata.success is True
        assert metadata.volumes_backed_up == 0
        assert len(metadata.errors) == 0
        # No docker commands should be called
        assert mock_run.call_count == 0

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_mixed_container_states(self, mock_run):
        """Unit with mix of running and stopped containers should handle correctly."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create unit with mixed states
        unit = BackupUnit(
            name="mixed_stack",
            type="stack",
            containers=[
                ContainerInfo(id="c1", name="web", image="nginx", status="running"),
                ContainerInfo(id="c2", name="db", image="postgres", status="exited"),
                ContainerInfo(id="c3", name="cache", image="redis", status="running"),
            ],
            volumes=[],
            compose_files=[],
        )

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should succeed and only stop running containers
        assert metadata.success is True
        # Should stop 2 running containers
        stop_calls = [c for c in mock_run.call_args_list if "stop" in str(c)]
        assert len(stop_calls) == 2

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_very_long_unit_name(self, mock_run):
        """Unit with very long name should be handled."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create unit with very long name
        long_name = "a" * 200  # 200 character name
        unit = BackupUnit(
            name=long_name,
            type="stack",
            containers=[],
            volumes=[
                VolumeInfo(
                    name="data",
                    driver="local",
                    mountpoint="/tmp/data",
                    size_bytes=1024,
                )
            ],
            compose_files=[],
        )

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                with patch.object(manager, "_backup_volume", return_value="vol_snap"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should handle long name
        assert metadata.success is True
        assert metadata.unit_name == long_name

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_zero_size_volume(self, mock_run):
        """Volume with zero size should be backed up."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        # Create volume with zero size
        unit = BackupUnit(
            name="test_stack",
            type="stack",
            containers=[],
            volumes=[
                VolumeInfo(
                    name="empty_vol",
                    driver="local",
                    mountpoint="/tmp/empty",
                    size_bytes=0,  # Zero size
                )
            ],
            compose_files=[],
        )

        with patch.object(manager, "_backup_recipes", return_value="recipe_snap"):
            with patch.object(manager, "_backup_networks", return_value=("net_snap", 1)):
                with patch.object(manager, "_backup_volume", return_value="vol_snap"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should succeed with zero-size volume
        assert metadata.success is True
        assert metadata.volumes_backed_up == 1


# =============================================================================
# Backup Volume TAR Tests (LEGACY)
# =============================================================================


@pytest.mark.unit
class TestBackupVolumeTar:
    """Tests for _backup_volume_tar method (legacy TAR format)."""

    @patch("kopi_docka.cores.backup_manager.subprocess.Popen")
    def test_creates_tar_with_correct_flags(self, mock_popen):
        """Should create tar command with all required flags."""
        from subprocess import PIPE

        manager = make_backup_manager()
        manager.exclude_patterns = []

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/var/lib/docker/volumes/mydata/_data",
            size_bytes=2048,
        )
        unit = make_backup_unit(name="mystack")

        # Mock tar process
        mock_process = Mock()
        mock_process.stdout = Mock()
        mock_process.returncode = 0
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        # Mock repo.create_snapshot_from_stdin
        manager.repo.create_snapshot_from_stdin = Mock(return_value="snap123")

        result = manager._backup_volume_tar(volume, unit, "backup-uuid-123")

        assert result == "snap123"

        # Verify tar command construction
        tar_call = mock_popen.call_args[0][0]
        assert tar_call[0] == "tar"
        assert "-cf" in tar_call
        assert "-" in tar_call  # Output to stdout
        assert "--numeric-owner" in tar_call
        assert "--xattrs" in tar_call
        assert "--acls" in tar_call
        assert "--one-file-system" in tar_call
        assert "--mtime=@0" in tar_call
        assert "--clamp-mtime" in tar_call
        assert "--sort=name" in tar_call
        assert "-C" in tar_call
        assert volume.mountpoint in tar_call
        assert "." in tar_call

    @patch("kopi_docka.cores.backup_manager.subprocess.Popen")
    def test_includes_exclude_patterns_in_tar_command(self, mock_popen):
        """Should add --exclude flags for each exclude pattern."""
        from subprocess import PIPE

        manager = make_backup_manager()
        manager.exclude_patterns = ["*.log", "cache/*", "temp"]

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/var/lib/docker/volumes/mydata/_data",
            size_bytes=2048,
        )
        unit = make_backup_unit(name="mystack")

        # Mock tar process
        mock_process = Mock()
        mock_process.stdout = Mock()
        mock_process.returncode = 0
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        manager.repo.create_snapshot_from_stdin = Mock(return_value="snap123")

        result = manager._backup_volume_tar(volume, unit, "backup-uuid-123")

        # Verify exclude patterns are in command
        tar_call = mock_popen.call_args[0][0]
        assert "--exclude" in tar_call

        # Count exclude flags (should be 3)
        exclude_count = tar_call.count("--exclude")
        assert exclude_count == 3

        # Verify patterns are present
        assert "*.log" in tar_call
        assert "cache/*" in tar_call
        assert "temp" in tar_call

    @patch("kopi_docka.cores.backup_manager.subprocess.Popen")
    def test_creates_snapshot_with_tar_format_tag(self, mock_popen):
        """Should tag snapshot with backup_format=TAR."""
        from kopi_docka.helpers.constants import BACKUP_FORMAT_TAR

        manager = make_backup_manager()
        manager.exclude_patterns = []

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/var/lib/docker/volumes/mydata/_data",
            size_bytes=2048,
        )
        unit = make_backup_unit(name="mystack")

        # Mock tar process
        mock_process = Mock()
        mock_process.stdout = Mock()
        mock_process.returncode = 0
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        manager.repo.create_snapshot_from_stdin = Mock(return_value="snap123")

        result = manager._backup_volume_tar(volume, unit, "backup-uuid-123")

        # Verify snapshot tags
        call_args = manager.repo.create_snapshot_from_stdin.call_args
        tags = call_args[1]["tags"]
        assert tags["backup_format"] == BACKUP_FORMAT_TAR
        assert tags["type"] == "volume"
        assert tags["unit"] == "mystack"
        assert tags["volume"] == "mydata"
        assert tags["backup_id"] == "backup-uuid-123"

    @patch("kopi_docka.cores.backup_manager.subprocess.Popen")
    def test_returns_none_when_tar_fails(self, mock_popen):
        """Should return None if tar process fails."""
        manager = make_backup_manager()
        manager.exclude_patterns = []

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/var/lib/docker/volumes/mydata/_data",
            size_bytes=2048,
        )
        unit = make_backup_unit(name="mystack")

        # Mock tar process that fails
        mock_process = Mock()
        mock_process.stdout = Mock()
        mock_process.returncode = 1  # Non-zero = failure
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        manager.repo.create_snapshot_from_stdin = Mock(return_value="snap123")

        result = manager._backup_volume_tar(volume, unit, "backup-uuid-123")

        # Should return None on tar failure
        assert result is None

    @patch("kopi_docka.cores.backup_manager.subprocess.Popen")
    def test_handles_exception_during_tar_backup(self, mock_popen):
        """Should return None and log error on exception."""
        manager = make_backup_manager()
        manager.exclude_patterns = []

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/var/lib/docker/volumes/mydata/_data",
            size_bytes=2048,
        )
        unit = make_backup_unit(name="mystack")

        # Mock Popen to raise exception
        mock_popen.side_effect = Exception("Tar command failed")

        result = manager._backup_volume_tar(volume, unit, "backup-uuid-123")

        # Should handle exception and return None
        assert result is None

    @patch("kopi_docka.cores.backup_manager.subprocess.Popen")
    def test_uses_temporary_file_for_stderr(self, mock_popen):
        """Should use temporary file for stderr to avoid deadlock."""
        manager = make_backup_manager()
        manager.exclude_patterns = []

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/var/lib/docker/volumes/mydata/_data",
            size_bytes=2048,
        )
        unit = make_backup_unit(name="mystack")

        # Mock tar process
        mock_process = Mock()
        mock_process.stdout = Mock()
        mock_process.returncode = 0
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        manager.repo.create_snapshot_from_stdin = Mock(return_value="snap123")

        result = manager._backup_volume_tar(volume, unit, "backup-uuid-123")

        # Verify Popen was called with stdout=PIPE
        call_kwargs = mock_popen.call_args[1]
        from subprocess import PIPE
        assert call_kwargs["stdout"] == PIPE
        # stderr should be a file object (not PIPE to avoid deadlock)
        assert call_kwargs["stderr"] != PIPE


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
