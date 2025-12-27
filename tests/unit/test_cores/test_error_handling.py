"""
Unit tests for error handling in backup/restore operations.

Tests edge cases, failure scenarios, and error recovery paths.
"""

import json
import pytest
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch, Mock, MagicMock

from kopi_docka.types import BackupUnit, ContainerInfo, VolumeInfo, BackupMetadata
from kopi_docka.helpers.constants import BACKUP_SCOPE_MINIMAL


def make_mock_config() -> Mock:
    """Create a mock Config object for testing."""
    config = Mock()
    config.parallel_workers = 2
    config.getint.return_value = 30
    config.getlist.return_value = []
    config.getboolean.return_value = False
    config.backup_base_path = Path(tempfile.gettempdir()) / "kopi-docka-test"
    return config


def make_container(
    id: str = "container1",
    name: str = "web",
    status: str = "running",
) -> ContainerInfo:
    """Create a test container."""
    return ContainerInfo(
        id=id,
        name=name,
        image="nginx:latest",
        status=status,
        inspect_data={"NetworkSettings": {"Networks": {}}},
    )


def make_volume(name: str = "data", mountpoint: str = "/tmp/vol") -> VolumeInfo:
    """Create a test volume."""
    return VolumeInfo(
        name=name,
        driver="local",
        mountpoint=mountpoint,
        size_bytes=1024,
    )


def make_unit(containers: int = 1, volumes: int = 1) -> BackupUnit:
    """Create a test backup unit."""
    return BackupUnit(
        name="testunit",
        type="stack",
        containers=[make_container(id=f"c{i}", name=f"svc{i}") for i in range(containers)],
        volumes=[make_volume(name=f"vol{i}", mountpoint=f"/tmp/vol{i}") for i in range(volumes)],
    )


# =============================================================================
# Container Stop Timeout Tests
# =============================================================================


@pytest.mark.unit
class TestContainerStopTimeout:
    """Tests for container stop timeout handling."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_stop_timeout_continues_with_backup(self, mock_run):
        """Timeout during stop should not prevent backup attempt."""
        from kopi_docka.cores.backup_manager import BackupManager
        from kopi_docka.helpers.ui_utils import SubprocessError

        # First call (stop) times out, second call (start) succeeds
        mock_run.side_effect = [
            SubprocessError(["docker", "stop"], 1, stderr="timeout"),
            CompletedProcess([], 0, stdout="", stderr=""),  # start
        ]

        manager = BackupManager.__new__(BackupManager)
        manager.config = make_mock_config()
        manager.repo = Mock()
        manager.repo.create_snapshot.return_value = "snap123"
        manager.policy_manager = Mock()
        manager.hooks_manager = Mock()
        manager.hooks_manager.execute_pre_backup.return_value = True
        manager.hooks_manager.execute_post_backup.return_value = True
        manager.hooks_manager.get_executed_hooks.return_value = []
        manager.max_workers = 1
        manager.stop_timeout = 30
        manager.start_timeout = 60
        manager.exclude_patterns = []

        unit = make_unit(containers=1, volumes=1)

        with patch.object(manager, "_backup_volume", return_value="snap123"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Backup should still have been attempted
        assert metadata is not None

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_container_restarts_even_after_stop_failure(self, mock_run):
        """Container start should be attempted even if stop failed."""
        from kopi_docka.cores.backup_manager import BackupManager
        from kopi_docka.helpers.ui_utils import SubprocessError

        calls = []

        def track_calls(cmd, *args, **kwargs):
            calls.append(cmd[0:2])
            if "stop" in cmd:
                raise SubprocessError(cmd, 1, stderr="stop failed")
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        mock_run.side_effect = track_calls

        manager = BackupManager.__new__(BackupManager)
        manager.config = make_mock_config()
        manager.repo = Mock()
        manager.policy_manager = Mock()
        manager.hooks_manager = Mock()
        manager.hooks_manager.execute_pre_backup.return_value = True
        manager.hooks_manager.execute_post_backup.return_value = True
        manager.hooks_manager.get_executed_hooks.return_value = []
        manager.max_workers = 1
        manager.stop_timeout = 30
        manager.start_timeout = 60
        manager.exclude_patterns = []

        unit = make_unit(containers=1, volumes=0)

        with patch.object(manager, "_backup_volume"):
            manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Verify start was called even though stop failed
        start_calls = [c for c in calls if "start" in str(c)]
        assert len(start_calls) > 0, "Container start should be attempted after stop failure"


# =============================================================================
# Partial Volume Failure Tests
# =============================================================================


@pytest.mark.unit
class TestPartialVolumeFailure:
    """Tests for handling partial volume backup failures."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_continues_after_single_volume_failure(self, mock_run):
        """Should continue backing up other volumes after one fails."""
        from kopi_docka.cores.backup_manager import BackupManager

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")

        manager = BackupManager.__new__(BackupManager)
        manager.config = make_mock_config()
        manager.repo = Mock()
        manager.policy_manager = Mock()
        manager.hooks_manager = Mock()
        manager.hooks_manager.execute_pre_backup.return_value = True
        manager.hooks_manager.execute_post_backup.return_value = True
        manager.hooks_manager.get_executed_hooks.return_value = []
        manager.max_workers = 1
        manager.stop_timeout = 30
        manager.start_timeout = 60
        manager.exclude_patterns = []

        unit = make_unit(containers=1, volumes=3)

        call_count = [0]

        def volume_backup(*args):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Volume 2 backup failed")
            return f"snap{call_count[0]}"

        with patch.object(manager, "_backup_volume", side_effect=volume_backup):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should have tried all 3 volumes
        assert call_count[0] == 3
        # 2 should have succeeded
        assert metadata.volumes_backed_up == 2
        # 1 error should be recorded
        assert len(metadata.errors) >= 1


# =============================================================================
# Kopia Connection Failure Tests
# =============================================================================


@pytest.mark.unit
class TestKopiaConnectionFailure:
    """Tests for handling Kopia connection failures."""

    def test_is_connected_returns_false_when_kopia_missing(self):
        """is_connected should return False when Kopia binary is not found."""
        from kopi_docka.cores.repository_manager import KopiaRepository

        repo = KopiaRepository.__new__(KopiaRepository)
        repo.config = Mock()
        repo.config.get_password.return_value = "test"
        repo.config.kopia_cache_directory = None
        repo.kopia_params = "filesystem --path /backup"
        repo.profile_name = "test"

        with patch("shutil.which", return_value=None):  # Kopia not found
            result = repo.is_connected()

        assert result is False

    def test_is_connected_returns_false_on_nonzero_exit(self):
        """is_connected should return False when kopia status returns non-zero."""
        from kopi_docka.cores.repository_manager import KopiaRepository

        repo = KopiaRepository.__new__(KopiaRepository)
        repo.config = Mock()
        repo.config.get_password.return_value = "test"
        repo.config.kopia_cache_directory = None
        repo.kopia_params = "filesystem --path /backup"
        repo.profile_name = "test"

        with patch("shutil.which", return_value="/usr/bin/kopia"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = CompletedProcess([], 1, stdout="", stderr="not connected")

                result = repo.is_connected()

        assert result is False

    def test_create_snapshot_raises_on_failure(self):
        """create_snapshot should raise RuntimeError on failure."""
        from kopi_docka.cores.repository_manager import KopiaRepository

        repo = KopiaRepository.__new__(KopiaRepository)
        repo.config = Mock()
        repo.config.get_password.return_value = "test"
        repo.config.kopia_cache_directory = None
        repo.kopia_params = "filesystem --path /backup"
        repo.profile_name = "test"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess(
                [], 1, stdout="", stderr="repository not connected"
            )

            with pytest.raises(RuntimeError, match="repository not connected"):
                repo.create_snapshot("/path/to/backup")


# =============================================================================
# Invalid Input Handling Tests
# =============================================================================


@pytest.mark.unit
class TestInvalidInputHandling:
    """Tests for handling invalid inputs gracefully."""

    def test_empty_container_list_handled(self):
        """Should handle empty container list without error."""
        from kopi_docka.cores.backup_manager import BackupManager

        manager = BackupManager.__new__(BackupManager)
        manager.stop_timeout = 30

        with patch("kopi_docka.cores.backup_manager.run_command") as mock_run:
            # Should not call docker stop for empty list
            manager._stop_containers([])

            mock_run.assert_not_called()

    def test_empty_snapshot_path_rejected(self):
        """Should reject empty path for snapshot."""
        from kopi_docka.cores.repository_manager import KopiaRepository

        repo = KopiaRepository.__new__(KopiaRepository)
        repo.config = Mock()
        repo.kopia_params = "filesystem --path /backup"
        repo.profile_name = "test"

        with pytest.raises(ValueError, match="path cannot be empty"):
            repo.create_snapshot("")

    def test_whitespace_only_path_rejected(self):
        """Should reject whitespace-only path for snapshot."""
        from kopi_docka.cores.repository_manager import KopiaRepository

        repo = KopiaRepository.__new__(KopiaRepository)
        repo.config = Mock()
        repo.kopia_params = "filesystem --path /backup"
        repo.profile_name = "test"

        with pytest.raises(ValueError, match="path cannot be empty"):
            repo.create_snapshot("   ")


# =============================================================================
# Docker Discovery Error Handling Tests
# =============================================================================


@pytest.mark.unit
class TestDockerDiscoveryErrors:
    """Tests for Docker discovery error handling."""

    @patch("kopi_docka.cores.docker_discovery.run_command")
    def test_handles_container_inspect_failure(self, mock_run):
        """Should skip containers that fail to inspect."""
        from kopi_docka.cores.docker_discovery import DockerDiscovery

        # First call returns container IDs, second fails, third succeeds
        mock_run.side_effect = [
            CompletedProcess([], 0, stdout="c1\nc2\n", stderr=""),
            Exception("Container not found"),  # c1 inspect fails
            CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    [
                        {
                            "Id": "c2",
                            "Name": "/web",
                            "Config": {"Image": "nginx", "Labels": {}, "Env": []},
                            "State": {"Status": "running"},
                            "Mounts": [],
                        }
                    ]
                ),
                stderr="",
            ),
        ]

        discovery = DockerDiscovery.__new__(DockerDiscovery)
        discovery.docker_socket = "/var/run/docker.sock"

        containers = discovery._discover_containers()

        # Should have skipped c1 and returned c2
        assert len(containers) == 1
        assert containers[0].name == "web"

    @patch("kopi_docka.cores.docker_discovery.run_command")
    def test_returns_empty_on_no_containers(self, mock_run):
        """Should return empty list when no containers are running."""
        from kopi_docka.cores.docker_discovery import DockerDiscovery

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")

        discovery = DockerDiscovery.__new__(DockerDiscovery)
        discovery.docker_socket = "/var/run/docker.sock"

        containers = discovery._discover_containers()

        assert containers == []


# =============================================================================
# Hook Failure Tests
# =============================================================================


@pytest.mark.unit
class TestHookFailures:
    """Tests for backup/restore hook failure handling."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_pre_hook_failure_prevents_container_stop(self, mock_run):
        """If pre-hook fails, containers should not be stopped."""
        from kopi_docka.cores.backup_manager import BackupManager

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")

        manager = BackupManager.__new__(BackupManager)
        manager.config = make_mock_config()
        manager.repo = Mock()
        manager.policy_manager = Mock()
        manager.hooks_manager = Mock()
        manager.hooks_manager.execute_pre_backup.return_value = False  # Hook fails
        manager.hooks_manager.execute_post_backup.return_value = True
        manager.hooks_manager.get_executed_hooks.return_value = []
        manager.max_workers = 1
        manager.stop_timeout = 30
        manager.start_timeout = 60
        manager.exclude_patterns = []

        unit = make_unit(containers=2, volumes=1)

        metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Docker stop should not have been called
        stop_calls = [c for c in mock_run.call_args_list if "stop" in str(c)]
        assert len(stop_calls) == 0

        # Backup should be marked as failed
        assert not metadata.success
        assert any("Pre-backup hook failed" in e for e in metadata.errors)


# =============================================================================
# Malformed Data Tests
# =============================================================================


@pytest.mark.unit
class TestMalformedData:
    """Tests for handling malformed data from external sources."""

    def test_handles_invalid_json_from_kopia(self):
        """Should handle invalid JSON output from Kopia gracefully."""
        from kopi_docka.cores.repository_manager import KopiaRepository

        repo = KopiaRepository.__new__(KopiaRepository)
        repo.config = Mock()
        repo.config.get_password.return_value = "test"
        repo.config.kopia_cache_directory = None
        repo.kopia_params = "filesystem --path /backup"
        repo.profile_name = "test"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess(
                [], 0, stdout="not valid json at all", stderr=""
            )

            snapshots = repo.list_snapshots()

        # Should return empty list, not crash
        assert snapshots == []

    def test_handles_missing_tags_in_snapshot(self):
        """Should handle snapshots with missing tags gracefully."""
        from kopi_docka.cores.repository_manager import KopiaRepository

        repo = KopiaRepository.__new__(KopiaRepository)
        repo.config = Mock()
        repo.config.get_password.return_value = "test"
        repo.config.kopia_cache_directory = None
        repo.kopia_params = "filesystem --path /backup"
        repo.profile_name = "test"

        # Snapshot without tags
        snapshots_json = [
            {
                "id": "snap1",
                "source": {"path": "/backup"},
                # No tags field
                "stats": {"totalSize": 1024},
            }
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess(
                [], 0, stdout=json.dumps(snapshots_json), stderr=""
            )

            snapshots = repo.list_snapshots()

        # Should return the snapshot with empty tags
        assert len(snapshots) == 1
        assert snapshots[0]["tags"] == {}
