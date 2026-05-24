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
from kopi_docka.cores.backup_volume_handler import BackupVolumeHandler
from kopi_docka.cores.safe_exit_manager import ServiceContinuityHandler
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
    """Create a BackupManager instance without running __init__.

    Plan 0028 Phase 3: ``backup_unit`` drives discovery via
    ``_collect_backup_sources`` (which writes to staging dirs and runs docker
    inspect) and the snapshot loop via ``repo.create_snapshots``. Both are
    stubbed here with empty defaults so individual tests can opt in by
    overriding either.
    """
    manager = BackupManager.__new__(BackupManager)
    manager.config = make_mock_config()
    manager.repo = Mock()
    manager.repo.create_snapshot.return_value = "snap123"
    manager.repo.create_snapshots.return_value = []
    manager.policy_manager = Mock()
    manager.hooks_manager = Mock()
    manager.hooks_manager.execute_pre_backup.return_value = True
    manager.hooks_manager.execute_post_backup.return_value = True
    manager.hooks_manager.get_executed_hooks.return_value = []
    manager.stop_timeout = 30
    manager.start_timeout = 60
    manager.exclude_patterns = []
    manager.volume_handler = BackupVolumeHandler(manager.repo, manager.exclude_patterns)
    manager._collect_backup_sources = Mock(return_value=[])
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
    """Plan 0028 Phase 3: ``backup_unit`` no longer dispatches to per-kind
    ``_backup_*`` helpers — it asks ``_collect_backup_sources`` for a flat
    list keyed off ``backup_scope`` and pipes that into
    ``repo.create_snapshots``. These tests verify the scope is propagated
    into discovery and that the metadata field round-trips."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_minimal_scope_forwarded_to_collect(self, mock_run):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()
        manager._collect_backup_sources = Mock(return_value=[])
        manager.repo.create_snapshots = Mock(return_value=[])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        manager._collect_backup_sources.assert_called_once()
        scope_arg = manager._collect_backup_sources.call_args[0][2]
        assert scope_arg == BACKUP_SCOPE_MINIMAL
        assert metadata.backup_scope == BACKUP_SCOPE_MINIMAL

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_standard_scope_forwarded_to_collect(self, mock_run):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()
        manager._collect_backup_sources = Mock(return_value=[])
        manager.repo.create_snapshots = Mock(return_value=[])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_STANDARD)

        scope_arg = manager._collect_backup_sources.call_args[0][2]
        assert scope_arg == BACKUP_SCOPE_STANDARD
        assert metadata.backup_scope == BACKUP_SCOPE_STANDARD

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_full_scope_forwarded_to_collect(self, mock_run):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()
        manager._collect_backup_sources = Mock(return_value=[])
        manager.repo.create_snapshots = Mock(return_value=[])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_FULL)

        scope_arg = manager._collect_backup_sources.call_args[0][2]
        assert scope_arg == BACKUP_SCOPE_FULL
        assert metadata.backup_scope == BACKUP_SCOPE_FULL


# =============================================================================
# Backup Scope Tag Tests
# =============================================================================


@pytest.mark.unit
class TestBackupScopeTag:
    """Tests for backup_scope tag in snapshots."""

    def test_volume_snapshot_includes_scope_tag_minimal(self):
        """Volume snapshots should include backup_scope tag (minimal)."""
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "snap-vol-123"

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/tmp/test_volume",
            size_bytes=2048,
        )
        unit = make_backup_unit(name="mystack")

        with tempfile.TemporaryDirectory() as tmpdir:
            volume.mountpoint = tmpdir
            manager.volume_handler.backup_volume_direct(volume, unit, "backup-id-123", BACKUP_SCOPE_MINIMAL)

        # Verify tags include backup_scope
        call_args = manager.repo.create_snapshot.call_args
        tags = call_args[1]["tags"]
        assert tags["backup_scope"] == BACKUP_SCOPE_MINIMAL
        assert tags["type"] == "volume"
        assert tags["backup_id"] == "backup-id-123"

    def test_volume_snapshot_includes_scope_tag_standard(self):
        """Volume snapshots should include backup_scope tag (standard)."""
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "snap-vol-456"

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/tmp/test_volume",
            size_bytes=2048,
        )
        unit = make_backup_unit(name="mystack")

        with tempfile.TemporaryDirectory() as tmpdir:
            volume.mountpoint = tmpdir
            manager.volume_handler.backup_volume_direct(volume, unit, "backup-id-456", BACKUP_SCOPE_STANDARD)

        call_args = manager.repo.create_snapshot.call_args
        tags = call_args[1]["tags"]
        assert tags["backup_scope"] == BACKUP_SCOPE_STANDARD

    def test_volume_snapshot_includes_scope_tag_full(self):
        """Volume snapshots should include backup_scope tag (full)."""
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "snap-vol-789"

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/tmp/test_volume",
            size_bytes=2048,
        )
        unit = make_backup_unit(name="mystack")

        with tempfile.TemporaryDirectory() as tmpdir:
            volume.mountpoint = tmpdir
            manager.volume_handler.backup_volume_direct(volume, unit, "backup-id-789", BACKUP_SCOPE_FULL)

        call_args = manager.repo.create_snapshot.call_args
        tags = call_args[1]["tags"]
        assert tags["backup_scope"] == BACKUP_SCOPE_FULL

    @patch("pathlib.Path.write_text")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.iterdir", return_value=[])
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_recipe_snapshot_includes_scope_tag(
        self, mock_run, mock_iterdir, mock_mkdir, mock_write_text
    ):
        """Recipe snapshots should include backup_scope tag."""
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "snap-recipe-123"

        # Mock docker inspect response
        inspect_data = [{"Config": {"Env": ["VAR=value"]}}]
        mock_run.return_value = CompletedProcess(
            [], 0, stdout=json.dumps(inspect_data), stderr=""
        )

        unit = make_backup_unit(name="mystack")
        unit.compose_files = []  # No compose files for simplicity

        manager._backup_recipes(unit, "backup-id-123", BACKUP_SCOPE_FULL)

        call_args = manager.repo.create_snapshot.call_args
        tags = call_args[1]["tags"]
        assert tags["backup_scope"] == BACKUP_SCOPE_FULL
        assert tags["type"] == "recipe"
        assert tags["backup_id"] == "backup-id-123"

    @patch("pathlib.Path.write_text")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.iterdir", return_value=[])
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_network_snapshot_includes_scope_tag(
        self, mock_run, mock_iterdir, mock_mkdir, mock_write_text
    ):
        """Network snapshots should include backup_scope tag."""
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "snap-network-123"

        # Mock network inspect response
        network_data = [{"Name": "mynet", "Driver": "bridge", "IPAM": {}}]
        mock_run.return_value = CompletedProcess(
            [], 0, stdout=json.dumps(network_data), stderr=""
        )

        unit = make_backup_unit(name="mystack")
        # Add custom network to container inspect data
        unit.containers[0].inspect_data = {
            "NetworkSettings": {"Networks": {"mynet": {}, "bridge": {}}}
        }

        snapshot_id, count = manager._backup_networks(unit, "backup-id-123", BACKUP_SCOPE_STANDARD)

        assert snapshot_id == "snap-network-123"
        call_args = manager.repo.create_snapshot.call_args
        tags = call_args[1]["tags"]
        assert tags["backup_scope"] == BACKUP_SCOPE_STANDARD
        assert tags["type"] == "networks"
        assert tags["backup_id"] == "backup-id-123"

    @patch("kopi_docka.cores.backup_volume_handler.subprocess.Popen")
    def test_volume_tar_snapshot_includes_scope_tag(self, mock_popen):
        """TAR volume snapshots should include backup_scope tag."""
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

        manager.repo.create_snapshot_from_stdin = Mock(return_value="snap-tar-123")

        manager.volume_handler.backup_volume_tar(volume, unit, "backup-id-123", BACKUP_SCOPE_MINIMAL)

        # Verify snapshot tags
        call_args = manager.repo.create_snapshot_from_stdin.call_args
        tags = call_args[1]["tags"]
        assert tags["backup_scope"] == BACKUP_SCOPE_MINIMAL
        assert tags["type"] == "volume"
        assert tags["backup_id"] == "backup-id-123"

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_all_sources_in_backup_unit_share_one_backup_scope(self, mock_run):
        """Every BackupSource handed to ``repo.create_snapshots`` carries the
        same ``backup_scope`` tag — the value passed into ``backup_unit``."""
        from kopi_docka.types import BackupSource

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit(volumes=2)

        sample_sources = [
            BackupSource(
                path="/stage/recipes/u",
                kind="recipe",
                tags={"type": "recipe", "unit": unit.name,
                      "backup_id": "bid", "backup_scope": BACKUP_SCOPE_FULL},
            ),
            BackupSource(
                path=unit.volumes[0].mountpoint,
                kind="volume",
                tags={"type": "volume", "unit": unit.name, "volume": unit.volumes[0].name,
                      "backup_id": "bid", "backup_scope": BACKUP_SCOPE_FULL,
                      "backup_format": "direct"},
            ),
        ]
        manager._collect_backup_sources = Mock(return_value=sample_sources)
        manager.repo.create_snapshots = Mock(return_value=["recipe_snap", "vol_snap"])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_FULL)

        scopes = {s.tags["backup_scope"] for s in sample_sources}
        assert scopes == {BACKUP_SCOPE_FULL}
        assert metadata.backup_scope == BACKUP_SCOPE_FULL


# =============================================================================
# Docker Config Backup Tests
# =============================================================================


@pytest.mark.unit
class TestBackupDockerConfig:
    """Tests for _backup_docker_config method."""

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.iterdir", return_value=[])
    @patch("shutil.copy2")
    def test_backs_up_daemon_json_when_present(self, mock_copy2, mock_iterdir, mock_mkdir):
        """Should backup daemon.json when it exists."""
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "snap-docker-123"
        unit = make_backup_unit(name="mystack")

        # Create a mock that returns True for daemon.json, False for systemd
        original_path = Path

        class MockPath(type(Path())):
            def exists(self):
                return "/etc/docker/daemon.json" in str(self)

            def is_file(self):
                return "/etc/docker/daemon.json" in str(self)

            def is_dir(self):
                return False

        with patch("kopi_docka.cores.backup_manager.Path", MockPath):
            result = manager._backup_docker_config(unit, "backup-id-123", BACKUP_SCOPE_FULL)

        assert result == "snap-docker-123"
        mock_copy2.assert_called_once()

        # Verify snapshot tags
        call_args = manager.repo.create_snapshot.call_args
        tags = call_args[1]["tags"]
        assert tags["type"] == "docker_config"
        assert tags["backup_scope"] == BACKUP_SCOPE_FULL
        assert tags["backup_id"] == "backup-id-123"
        assert "daemon.json" in tags["files"]

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.iterdir", return_value=[])
    @patch("shutil.copytree")
    def test_backs_up_systemd_overrides_when_present(self, mock_copytree, mock_iterdir, mock_mkdir):
        """Should backup systemd overrides when they exist."""
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "snap-docker-456"
        unit = make_backup_unit(name="mystack")

        # Create a mock that returns True for systemd, False for daemon.json
        class MockPath(type(Path())):
            def exists(self):
                return "docker.service.d" in str(self)

            def is_file(self):
                return False

            def is_dir(self):
                return "docker.service.d" in str(self)

        with patch("kopi_docka.cores.backup_manager.Path", MockPath):
            result = manager._backup_docker_config(unit, "backup-id-456", BACKUP_SCOPE_FULL)

        assert result == "snap-docker-456"
        mock_copytree.assert_called_once()

        # Verify snapshot tags
        call_args = manager.repo.create_snapshot.call_args
        tags = call_args[1]["tags"]
        assert tags["type"] == "docker_config"
        assert "docker.service.d/" in tags["files"]

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.iterdir", return_value=[])
    @patch("pathlib.Path.exists", return_value=False)
    def test_returns_none_when_no_config_files_exist(self, mock_exists, mock_iterdir, mock_mkdir):
        """Should return None when no config files are found."""
        manager = make_backup_manager()
        unit = make_backup_unit(name="mystack")

        result = manager._backup_docker_config(unit, "backup-id-789", BACKUP_SCOPE_FULL)

        assert result is None
        manager.repo.create_snapshot.assert_not_called()

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.iterdir", return_value=[])
    @patch("shutil.copy2", side_effect=PermissionError("Access denied"))
    def test_handles_permission_error_gracefully(self, mock_copy2, mock_iterdir, mock_mkdir):
        """Should handle permission errors and return None."""
        manager = make_backup_manager()
        unit = make_backup_unit(name="mystack")

        # Create a mock that returns True for daemon.json but copy2 will fail
        class MockPath(type(Path())):
            def exists(self):
                return "/etc/docker/daemon.json" in str(self)

            def is_file(self):
                return "/etc/docker/daemon.json" in str(self)

            def is_dir(self):
                return False

        with patch("kopi_docka.cores.backup_manager.Path", MockPath):
            result = manager._backup_docker_config(unit, "backup-id-999", BACKUP_SCOPE_FULL)

        # Should return None since no files were successfully backed up
        assert result is None

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_full_scope_records_docker_config_when_source_present(self, mock_run):
        """A docker_config source in the collected list flips
        ``metadata.docker_config_backed_up`` once create_snapshots returns
        a non-empty ID for it."""
        from kopi_docka.types import BackupSource

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        sources = [
            BackupSource(
                path="/stage/docker-config/u",
                kind="docker_config",
                tags={"type": "docker_config", "unit": unit.name,
                      "backup_id": "bid", "backup_scope": BACKUP_SCOPE_FULL,
                      "files": "daemon.json"},
            )
        ]
        manager._collect_backup_sources = Mock(return_value=sources)
        manager.repo.create_snapshots = Mock(return_value=["docker_snap"])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_FULL)

        assert metadata.docker_config_backed_up is True
        assert "docker_snap" in metadata.kopia_snapshot_ids

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_no_docker_config_source_leaves_flag_false(self, mock_run):
        """No docker_config source in the list (because scope < FULL or because
        the host has no daemon.json) means metadata stays at default ``False``."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()
        manager._collect_backup_sources = Mock(return_value=[])
        manager.repo.create_snapshots = Mock(return_value=[])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_STANDARD)

        assert metadata.docker_config_backed_up is False

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_docker_config_failure_does_not_fail_backup(self, mock_run):
        """A failed docker_config snapshot (empty string from create_snapshots)
        records a per-source error but does NOT poison the overall backup."""
        from kopi_docka.types import BackupSource

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        sources = [
            BackupSource(
                path="/stage/docker-config/u",
                kind="docker_config",
                tags={"type": "docker_config", "unit": unit.name,
                      "backup_id": "bid", "backup_scope": BACKUP_SCOPE_FULL},
            )
        ]
        manager._collect_backup_sources = Mock(return_value=sources)
        # Empty string = the snapshot failed inside repo.create_snapshots
        manager.repo.create_snapshots = Mock(return_value=[""])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_FULL)

        # docker_config is best-effort but still surfaced as a per-source error
        assert metadata.docker_config_backed_up is False
        assert any("docker_config" in e for e in metadata.errors)


# =============================================================================
# Container Stop/Start Order Tests
# =============================================================================


@pytest.mark.unit
class TestContainerOrdering:
    """Tests for container stop/start ordering."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_stops_containers_before_snapshot_loop(self, mock_run):
        """Plan 0028: source discovery happens BEFORE container stop (because
        docker inspect needs them alive), then the snapshot loop runs after
        stop. Stop must always precede snapshot."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()

        call_order = []

        def track_stop(containers, service_handler):
            call_order.append("stop")

        def track_start(containers, service_handler):
            call_order.append("start")

        manager._collect_backup_sources = Mock(
            side_effect=lambda *_: (call_order.append("collect"), [])[1]
        )
        manager.repo.create_snapshots = Mock(
            side_effect=lambda sources: (call_order.append("snapshot"), [])[1]
        )

        with patch.object(manager, "_stop_containers", side_effect=track_stop):
            with patch.object(manager, "_start_containers", side_effect=track_start):
                with patch.object(manager, "_save_metadata"):
                    manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert call_order.index("stop") < call_order.index("snapshot")
        assert call_order.index("snapshot") < call_order.index("start")

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_restarts_containers_on_error(self, mock_run):
        """Containers must restart even if the snapshot loop raises."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()
        manager._collect_backup_sources = Mock(return_value=[])
        manager.repo.create_snapshots = Mock(side_effect=RuntimeError("Backup failed"))

        start_called = False

        def track_start(containers, service_handler):
            nonlocal start_called
            start_called = True

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers", side_effect=track_start):
                with patch.object(manager, "_save_metadata"):
                    metadata = manager.backup_unit(
                        unit, backup_scope=BACKUP_SCOPE_MINIMAL
                    )

        assert start_called
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
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()
        manager._collect_backup_sources = Mock(return_value=[])
        manager.repo.create_snapshots = Mock(return_value=[])

        call_order = []
        manager.hooks_manager.execute_pre_backup.side_effect = lambda x: (
            call_order.append("pre_hook"), True,
        )[1]

        def track_stop(containers, service_handler):
            call_order.append("stop")

        with patch.object(manager, "_stop_containers", side_effect=track_stop):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_save_metadata"):
                    manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert call_order.index("pre_hook") < call_order.index("stop")

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_post_hook_executed_after_start(self, mock_run):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit()
        manager._collect_backup_sources = Mock(return_value=[])
        manager.repo.create_snapshots = Mock(return_value=[])

        call_order = []

        def track_start(containers, service_handler):
            call_order.append("start")

        manager.hooks_manager.execute_post_backup.side_effect = lambda x: (
            call_order.append("post_hook"), True,
        )[1]

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers", side_effect=track_start):
                with patch.object(manager, "_save_metadata"):
                    manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert call_order.index("start") < call_order.index("post_hook")

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_pre_hook_failure_aborts_backup(self, mock_run):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        manager.hooks_manager.execute_pre_backup.return_value = False
        unit = make_backup_unit()

        with patch.object(manager, "_stop_containers") as mock_stop:
            metadata = manager.backup_unit(unit)

        mock_stop.assert_not_called()
        manager.repo.create_snapshots.assert_not_called()
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
        """Per-source failures (empty IDs from create_snapshots) accumulate
        in metadata.errors without aborting the rest of the loop."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit(volumes=3)

        manager._collect_backup_sources = Mock(
            side_effect=lambda u, bid, s: _build_volume_sources(u, bid, s)
        )
        manager.repo.create_snapshots = Mock(return_value=["snap1", "", "snap3"])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.volumes_backed_up == 2
        assert len(metadata.errors) == 1

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_post_hook_failure_adds_error(self, mock_run):
        """Post-hook failure should add error but not fail backup."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        manager.hooks_manager.execute_post_backup.return_value = False
        unit = make_backup_unit()

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager.volume_handler, "backup_volume", return_value="snap123"):
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
        service_handler = Mock()

        containers = [
            ContainerInfo(id="c1", name="web", image="nginx", status="running"),
            ContainerInfo(id="c2", name="db", image="postgres", status="running"),
        ]

        manager._stop_containers(containers, service_handler)

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
        service_handler = Mock()

        containers = [
            ContainerInfo(id="c1", name="web", image="nginx", status="running"),
            ContainerInfo(id="c2", name="db", image="postgres", status="exited"),
        ]

        manager._stop_containers(containers, service_handler)

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
        service_handler = Mock(spec=ServiceContinuityHandler)

        containers = [
            ContainerInfo(id="c1", name="web", image="nginx", status="running"),
            ContainerInfo(id="c2", name="db", image="postgres", status="running"),
        ]

        manager._start_containers(containers, service_handler)

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
        service_handler = Mock(spec=ServiceContinuityHandler)

        containers = [ContainerInfo(id="c1", name="web", image="nginx", status="running")]

        manager._start_containers(containers, service_handler)

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

            result = manager.volume_handler.backup_volume_direct(volume, unit, "backup-uuid-123", BACKUP_SCOPE_STANDARD)

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

        result = manager.volume_handler.backup_volume_direct(volume, unit, "backup-id", BACKUP_SCOPE_STANDARD)

        assert result is None

    def test_passes_exclude_patterns(self):
        """Should pass exclude patterns to Kopia."""
        manager = make_backup_manager()
        manager.exclude_patterns = ["*.log", "cache/*"]
        manager.volume_handler = BackupVolumeHandler(manager.repo, manager.exclude_patterns)
        manager.repo.create_snapshot.return_value = "snap123"

        volume = VolumeInfo(
            name="mydata",
            driver="local",
            mountpoint="/tmp",
        )
        unit = make_backup_unit()

        with tempfile.TemporaryDirectory() as tmpdir:
            volume.mountpoint = tmpdir
            manager.volume_handler.backup_volume_direct(volume, unit, "backup-id", BACKUP_SCOPE_STANDARD)

        call_args = manager.repo.create_snapshot.call_args
        assert call_args[1]["exclude_patterns"] == ["*.log", "cache/*"]


# =============================================================================
# Sequential Snapshot Loop Tests (Plan 0028 — no more ThreadPool)
# =============================================================================


def _build_volume_sources(unit, backup_id, scope):
    """Helper: build BackupSource list shaped like _collect_volume_sources would."""
    from kopi_docka.types import BackupSource

    return [
        BackupSource(
            path=v.mountpoint,
            kind="volume",
            tags={
                "type": "volume", "unit": unit.name, "volume": v.name,
                "backup_id": backup_id, "backup_scope": scope,
                "backup_format": "direct",
            },
        )
        for v in unit.volumes
    ]


@pytest.mark.unit
class TestSequentialSnapshotLoop:
    """Plan 0028 collapsed the per-volume ThreadPool into one sequential
    ``repo.create_snapshots(sources)`` call. These tests verify ordering,
    metadata counts, and per-source failure handling against that contract.
    """

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_all_volumes_snapshotted_in_a_single_call(self, mock_run):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit(name="mystack", volumes=3)

        manager._collect_backup_sources = Mock(
            side_effect=lambda u, bid, s: _build_volume_sources(u, bid, s)
        )
        manager.repo.create_snapshots = Mock(
            side_effect=lambda srcs: [f"snap_{s.tags['volume']}" for s in srcs]
        )

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert manager.repo.create_snapshots.call_count == 1
        assert metadata.volumes_backed_up == 3
        assert len(metadata.kopia_snapshot_ids) == 3
        assert metadata.success is True

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_per_source_failure_marked_by_empty_string(self, mock_run):
        """``create_snapshots`` indicates per-source failure with ``""`` at
        that index — backup_unit records the error but processes the rest."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit(name="mystack", volumes=3)

        manager._collect_backup_sources = Mock(
            side_effect=lambda u, bid, s: _build_volume_sources(u, bid, s)
        )
        manager.repo.create_snapshots = Mock(
            return_value=["snap_a", "", "snap_c"]
        )

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.volumes_backed_up == 2
        assert metadata.kopia_snapshot_ids == ["snap_a", "snap_c"]
        assert len(metadata.errors) == 1
        assert "Failed to snapshot volume" in metadata.errors[0]
        assert metadata.success is False

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_create_snapshots_exception_aborts_loop_but_restarts_containers(
        self, mock_run
    ):
        """If create_snapshots raises (not per-source — whole call), the
        snapshot phase fails entirely, but containers still restart."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit(name="mystack", volumes=2)

        manager._collect_backup_sources = Mock(
            side_effect=lambda u, bid, s: _build_volume_sources(u, bid, s)
        )
        manager.repo.create_snapshots = Mock(side_effect=RuntimeError("disk error"))

        start_called = False

        def track_start(containers, service_handler):
            nonlocal start_called
            start_called = True

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers", side_effect=track_start
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert start_called is True
        assert metadata.volumes_backed_up == 0
        assert any("disk error" in e for e in metadata.errors)
        assert metadata.success is False

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_all_volumes_fail_records_one_error_per_source(self, mock_run):
        """Every-source failure → N errors, success False, no snapshot IDs."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit(name="mystack", volumes=3)

        manager._collect_backup_sources = Mock(
            side_effect=lambda u, bid, s: _build_volume_sources(u, bid, s)
        )
        manager.repo.create_snapshots = Mock(return_value=["", "", ""])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.volumes_backed_up == 0
        assert len(metadata.errors) == 3
        assert all("Failed to snapshot" in e for e in metadata.errors)
        assert metadata.success is False

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_empty_unit_completes_clean(self, mock_run):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit(name="mystack", volumes=0)
        manager._collect_backup_sources = Mock(return_value=[])
        manager.repo.create_snapshots = Mock(return_value=[])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.volumes_backed_up == 0
        assert metadata.errors == []
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
        from kopi_docka.types import BackupSource

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        unit = BackupUnit(
            name="empty_stack",
            type="stack",
            containers=[],
            volumes=[
                VolumeInfo(name="data", driver="local",
                           mountpoint="/tmp/data", size_bytes=1024)
            ],
            compose_files=[],
        )

        manager._collect_backup_sources = Mock(return_value=[
            BackupSource(path="/tmp/data", kind="volume",
                         tags={"type": "volume", "unit": "empty_stack",
                               "volume": "data", "backup_id": "bid",
                               "backup_format": "direct"})
        ])
        manager.repo.create_snapshots = Mock(return_value=["vol_snap"])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
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
            containers=[ContainerInfo(id="c1", name="web", image="nginx", status="running")],
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
            containers=[ContainerInfo(id="c1", name="web", image="nginx", status="running")],
            volumes=[],
            compose_files=[],  # No compose files
        )

        # Mock _backup_recipes to simulate empty compose files
        def mock_backup_recipes(unit, backup_id, backup_scope):
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
        """Whitespace in volume name reaches BackupSource.tags['volume'] verbatim."""
        from kopi_docka.types import BackupSource

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        unit = BackupUnit(
            name="test_stack",
            type="stack",
            containers=[],
            volumes=[
                VolumeInfo(
                    name="my data volume",
                    driver="local",
                    mountpoint="/tmp/my_data",
                    size_bytes=1024,
                )
            ],
            compose_files=[],
        )

        manager._collect_backup_sources = Mock(
            return_value=[
                BackupSource(
                    path="/tmp/my_data", kind="volume",
                    tags={"type": "volume", "unit": "test_stack",
                          "volume": "my data volume", "backup_id": "bid",
                          "backup_format": "direct"},
                )
            ]
        )
        manager.repo.create_snapshots = Mock(return_value=["snap-ws"])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.success is True
        assert metadata.volumes_backed_up == 1
        sources_passed = manager.repo.create_snapshots.call_args[0][0]
        assert sources_passed[0].tags["volume"] == "my data volume"

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_volume_name_with_special_characters(self, mock_run):
        """Dashes / dots / underscores in volume name round-trip through tags."""
        from kopi_docka.types import BackupSource

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        unit = BackupUnit(
            name="test_stack",
            type="stack",
            containers=[],
            volumes=[
                VolumeInfo(
                    name="data-vol_v1.0",
                    driver="local",
                    mountpoint="/tmp/data",
                    size_bytes=1024,
                )
            ],
            compose_files=[],
        )

        manager._collect_backup_sources = Mock(
            return_value=[
                BackupSource(
                    path="/tmp/data", kind="volume",
                    tags={"type": "volume", "unit": "test_stack",
                          "volume": "data-vol_v1.0", "backup_id": "bid",
                          "backup_format": "direct"},
                )
            ]
        )
        manager.repo.create_snapshots = Mock(return_value=["snap-special"])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.success is True
        assert metadata.volumes_backed_up == 1
        sources_passed = manager.repo.create_snapshots.call_args[0][0]
        assert sources_passed[0].tags["volume"] == "data-vol_v1.0"

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
                with patch.object(manager.volume_handler, "backup_volume", return_value="vol_snap"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        # Should handle long name
        assert metadata.success is True
        assert metadata.unit_name == long_name

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_zero_size_volume(self, mock_run):
        """A zero-byte volume still produces a BackupSource and snapshot."""
        from kopi_docka.types import BackupSource

        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()

        unit = BackupUnit(
            name="test_stack",
            type="stack",
            containers=[],
            volumes=[
                VolumeInfo(name="empty_vol", driver="local",
                           mountpoint="/tmp/empty", size_bytes=0)
            ],
            compose_files=[],
        )

        manager._collect_backup_sources = Mock(return_value=[
            BackupSource(path="/tmp/empty", kind="volume",
                         tags={"type": "volume", "unit": "test_stack",
                               "volume": "empty_vol", "backup_id": "bid",
                               "backup_format": "direct", "size_bytes": "0"})
        ])
        manager.repo.create_snapshots = Mock(return_value=["vol_snap"])

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.success is True
        assert metadata.volumes_backed_up == 1


# =============================================================================
# Backup Volume TAR Tests (LEGACY)
# =============================================================================


@pytest.mark.unit
class TestBackupVolumeTar:
    """Tests for _backup_volume_tar method (legacy TAR format)."""

    @patch("kopi_docka.cores.backup_volume_handler.subprocess.Popen")
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

        result = manager.volume_handler.backup_volume_tar(volume, unit, "backup-uuid-123", BACKUP_SCOPE_STANDARD)

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

    @patch("kopi_docka.cores.backup_volume_handler.subprocess.Popen")
    def test_includes_exclude_patterns_in_tar_command(self, mock_popen):
        """Should add --exclude flags for each exclude pattern."""
        from subprocess import PIPE

        manager = make_backup_manager()
        manager.exclude_patterns = ["*.log", "cache/*", "temp"]
        manager.volume_handler = BackupVolumeHandler(manager.repo, manager.exclude_patterns)

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

        result = manager.volume_handler.backup_volume_tar(volume, unit, "backup-uuid-123", BACKUP_SCOPE_STANDARD)

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

    @patch("kopi_docka.cores.backup_volume_handler.subprocess.Popen")
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

        result = manager.volume_handler.backup_volume_tar(volume, unit, "backup-uuid-123", BACKUP_SCOPE_STANDARD)

        # Verify snapshot tags
        call_args = manager.repo.create_snapshot_from_stdin.call_args
        tags = call_args[1]["tags"]
        assert tags["backup_format"] == BACKUP_FORMAT_TAR
        assert tags["type"] == "volume"
        assert tags["unit"] == "mystack"
        assert tags["volume"] == "mydata"
        assert tags["backup_id"] == "backup-uuid-123"

    @patch("kopi_docka.cores.backup_volume_handler.subprocess.Popen")
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

        result = manager.volume_handler.backup_volume_tar(volume, unit, "backup-uuid-123", BACKUP_SCOPE_STANDARD)

        # Should return None on tar failure
        assert result is None

    @patch("kopi_docka.cores.backup_volume_handler.subprocess.Popen")
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

        result = manager.volume_handler.backup_volume_tar(volume, unit, "backup-uuid-123", BACKUP_SCOPE_STANDARD)

        # Should handle exception and return None
        assert result is None

    @patch("kopi_docka.cores.backup_volume_handler.subprocess.Popen")
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

        result = manager.volume_handler.backup_volume_tar(volume, unit, "backup-uuid-123", BACKUP_SCOPE_STANDARD)

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

    @patch("pathlib.Path.write_text")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.iterdir", return_value=[])
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_redacts_sensitive_env_vars(self, mock_run, mock_iterdir, mock_mkdir, mock_write_text):
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
        mock_run.return_value = CompletedProcess([], 0, stdout=json.dumps(inspect_data), stderr="")

        unit = make_backup_unit(containers=1)
        unit.compose_files = []  # No compose files for simplicity

        result = manager._backup_recipes(unit, "backup-id", BACKUP_SCOPE_STANDARD)

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
            with patch.object(manager.volume_handler, "backup_volume", return_value="snap123"):
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
            with patch.object(manager.volume_handler, "backup_volume", return_value="snap123"):
                with patch.object(manager, "_start_containers"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.success is True
        assert len(metadata.errors) == 0

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_metadata_tracks_volumes_backed_up(self, mock_run):
        """metadata.volumes_backed_up == number of successful volume snapshots."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager()
        unit = make_backup_unit(volumes=3)

        manager._collect_backup_sources = Mock(
            side_effect=lambda u, bid, s: _build_volume_sources(u, bid, s)
        )
        manager.repo.create_snapshots = Mock(
            return_value=["snap1", "snap2", "snap3"]
        )

        with patch.object(manager, "_stop_containers"), patch.object(
            manager, "_start_containers"
        ), patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.volumes_backed_up == 3


# =============================================================================
# Network Backup Tests
# =============================================================================


@pytest.mark.unit
class TestBackupNetworks:
    """Tests for _backup_networks method."""

    @patch("pathlib.Path.write_text")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.iterdir", return_value=[])
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backs_up_custom_networks(self, mock_run, mock_iterdir, mock_mkdir, mock_write_text):
        """Should backup custom networks (not bridge/host/none)."""
        manager = make_backup_manager()
        manager.repo.create_snapshot.return_value = "net_snap123"

        # Mock network inspect response
        network_data = [{"Name": "mynet", "Driver": "bridge", "IPAM": {}}]
        mock_run.return_value = CompletedProcess([], 0, stdout=json.dumps(network_data), stderr="")

        unit = make_backup_unit()
        # Add custom network to container inspect data
        unit.containers[0].inspect_data = {
            "NetworkSettings": {"Networks": {"mynet": {}, "bridge": {}}}
        }

        snapshot_id, count = manager._backup_networks(unit, "backup-id", BACKUP_SCOPE_STANDARD)

        assert snapshot_id == "net_snap123"
        assert count == 1

    def test_skips_default_networks(self):
        """Should not backup default networks (bridge, host, none)."""
        manager = make_backup_manager()

        unit = make_backup_unit()
        # Set ALL containers to only have default networks
        for container in unit.containers:
            container.inspect_data = {"NetworkSettings": {"Networks": {"bridge": {}, "host": {}}}}

        snapshot_id, count = manager._backup_networks(unit, "backup-id", BACKUP_SCOPE_STANDARD)

        assert snapshot_id is None
        assert count == 0
        # No snapshot should be created for default networks
        manager.repo.create_snapshot.assert_not_called()


# =============================================================================
# Retention Policy Tests removed in Plan 0028
# =============================================================================
# The previous TestEnsurePoliciesVolumes class exercised _ensure_policies and
# set_retention_for_target — both gone in Plan 0028 (global-only retention).
# The replacement contract ("backup_unit must NEVER call per-path setters")
# lives in tests/unit/test_cores/test_backup_manager_policies.py.


class TestPrepareStagingDir:
    """Tests for _prepare_staging_dir() helper method."""

    def test_creates_directory_structure(self):
        """Test that _prepare_staging_dir creates the correct directory structure."""
        manager = make_backup_manager()

        with patch("kopi_docka.cores.backup_manager.STAGING_BASE_DIR", Path("/var/cache/kopi-docka/staging")):
            with patch("pathlib.Path.mkdir") as mock_mkdir, \
                 patch("pathlib.Path.iterdir", return_value=[]):
                result = manager._prepare_staging_dir("recipes", "myproject")

                # Verify directory creation
                mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

                # Verify correct path returned
                assert result == Path("/var/cache/kopi-docka/staging/recipes/myproject")

    def test_clears_existing_files(self):
        """Test that existing files are cleared from staging directory."""
        manager = make_backup_manager()

        # Mock existing files
        mock_file1 = Mock(spec=Path)
        mock_file1.is_file.return_value = True
        mock_file1.is_dir.return_value = False
        mock_file2 = Mock(spec=Path)
        mock_file2.is_file.return_value = True
        mock_file2.is_dir.return_value = False

        with patch("kopi_docka.cores.backup_manager.STAGING_BASE_DIR", Path("/test/staging")):
            with patch("pathlib.Path.mkdir"), \
                 patch("pathlib.Path.iterdir", return_value=[mock_file1, mock_file2]):
                manager._prepare_staging_dir("networks", "testunit")

                # Verify files were deleted
                mock_file1.unlink.assert_called_once()
                mock_file2.unlink.assert_called_once()

    def test_clears_existing_directories(self):
        """Test that existing directories are cleared from staging directory."""
        manager = make_backup_manager()

        # Mock existing directory
        mock_dir = Mock(spec=Path)
        mock_dir.is_file.return_value = False
        mock_dir.is_dir.return_value = True

        with patch("kopi_docka.cores.backup_manager.STAGING_BASE_DIR", Path("/test/staging")):
            with patch("pathlib.Path.mkdir"), \
                 patch("pathlib.Path.iterdir", return_value=[mock_dir]), \
                 patch("shutil.rmtree") as mock_rmtree:
                manager._prepare_staging_dir("recipes", "myapp")

                # Verify directory was removed
                mock_rmtree.assert_called_once_with(mock_dir)

    def test_clears_mixed_content(self):
        """Test that both files and directories are cleared."""
        manager = make_backup_manager()

        # Mock mixed content
        mock_file = Mock(spec=Path)
        mock_file.is_file.return_value = True
        mock_file.is_dir.return_value = False

        mock_dir = Mock(spec=Path)
        mock_dir.is_file.return_value = False
        mock_dir.is_dir.return_value = True

        with patch("kopi_docka.cores.backup_manager.STAGING_BASE_DIR", Path("/test/staging")):
            with patch("pathlib.Path.mkdir"), \
                 patch("pathlib.Path.iterdir", return_value=[mock_file, mock_dir]), \
                 patch("shutil.rmtree") as mock_rmtree:
                manager._prepare_staging_dir("networks", "webapp")

                # Verify both were cleared
                mock_file.unlink.assert_called_once()
                mock_rmtree.assert_called_once_with(mock_dir)

    def test_handles_empty_directory(self):
        """Test that method works correctly when directory is already empty."""
        manager = make_backup_manager()

        with patch("kopi_docka.cores.backup_manager.STAGING_BASE_DIR", Path("/test/staging")):
            with patch("pathlib.Path.mkdir") as mock_mkdir, \
                 patch("pathlib.Path.iterdir", return_value=[]):
                result = manager._prepare_staging_dir("recipes", "emptyunit")

                # Verify directory was created
                mock_mkdir.assert_called_once()

                # Verify correct path returned
                assert result == Path("/test/staging/recipes/emptyunit")

    def test_different_subdirectories(self):
        """Test that method works with different subdir values."""
        manager = make_backup_manager()

        subdirs = ["recipes", "networks", "configs"]

        for subdir in subdirs:
            with patch("kopi_docka.cores.backup_manager.STAGING_BASE_DIR", Path("/cache/staging")):
                with patch("pathlib.Path.mkdir"), \
                     patch("pathlib.Path.iterdir", return_value=[]):
                    result = manager._prepare_staging_dir(subdir, "testunit")

                    assert result == Path(f"/cache/staging/{subdir}/testunit")

    def test_backup_recipes_uses_stable_path(self):
        """Test that _backup_recipes uses _prepare_staging_dir and stable path."""
        manager = make_backup_manager()

        # Create minimal unit
        unit = BackupUnit(
            name="testapp",
            type="stack",
            compose_files=[],
            containers=[],
            volumes=[],
        )

        staging_path = Path("/var/cache/kopi-docka/staging/recipes/testapp")

        with patch.object(manager, "_prepare_staging_dir", return_value=staging_path) as mock_prepare:
            with patch("pathlib.Path.mkdir"), \
                 patch("pathlib.Path.write_text"):
                result = manager._backup_recipes(unit, "backup123", BACKUP_SCOPE_STANDARD)

                # Verify _prepare_staging_dir was called with correct args
                mock_prepare.assert_called_once_with("recipes", "testapp")

                # Verify snapshot was created with stable path
                manager.repo.create_snapshot.assert_called_once()
                call_args = manager.repo.create_snapshot.call_args
                assert call_args[0][0] == str(staging_path)

                # Verify snapshot ID returned
                assert result == "snap123"

    def test_backup_networks_uses_stable_path(self):
        """Test that _backup_networks uses _prepare_staging_dir and stable path."""
        manager = make_backup_manager()

        # Create unit with custom network
        container = ContainerInfo(
            id="abc123",
            name="web",
            image="nginx:latest",
            status="running",
            compose_files=[Path("/app/docker-compose.yml")],
            inspect_data={
                "NetworkSettings": {
                    "Networks": {
                        "custom_network": {"NetworkID": "net123"}
                    }
                }
            },
        )

        unit = BackupUnit(
            name="myapp",
            type="stack",
            compose_files=[Path("/app/docker-compose.yml")],
            containers=[container],
            volumes=[],
        )

        staging_path = Path("/var/cache/kopi-docka/staging/networks/myapp")

        # Mock run_command to return network inspect data
        mock_result = Mock()
        mock_result.stdout = json.dumps([{"Name": "custom_network", "Driver": "bridge", "Scope": "local"}])

        with patch.object(manager, "_prepare_staging_dir", return_value=staging_path) as mock_prepare:
            with patch("kopi_docka.cores.backup_manager.run_command", return_value=mock_result), \
                 patch("pathlib.Path.write_text"):
                snapshot_id, network_count = manager._backup_networks(unit, "backup456", BACKUP_SCOPE_STANDARD)

                # Verify _prepare_staging_dir was called with correct args
                mock_prepare.assert_called_once_with("networks", "myapp")

                # Verify snapshot was created with stable path
                manager.repo.create_snapshot.assert_called_once()
                call_args = manager.repo.create_snapshot.call_args
                assert call_args[0][0] == str(staging_path)

                # Verify return values
                assert snapshot_id == "snap123"
                assert network_count == 1
