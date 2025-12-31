"""
Unit tests for RestoreManager class.

Tests the restore orchestration business logic with mocked external dependencies.
"""

import subprocess
from subprocess import CompletedProcess
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from contextlib import contextmanager

import kopi_docka.cores.restore_manager as restore_manager
from kopi_docka.types import RestorePoint
from kopi_docka.helpers.constants import BACKUP_FORMAT_DIRECT, BACKUP_FORMAT_TAR


def make_manager() -> restore_manager.RestoreManager:
    """Create a RestoreManager instance without running __init__."""
    mgr = restore_manager.RestoreManager.__new__(restore_manager.RestoreManager)
    mgr.config = Mock()
    mgr.repo = Mock()
    mgr.hooks_manager = Mock()
    mgr.start_timeout = 60
    mgr.non_interactive = False
    mgr.force_recreate_networks = False
    mgr.skip_network_recreation = False
    return mgr


# =============================================================================
# Container Network Tests (existing tests)
# =============================================================================


def test_list_containers_on_network_parses_output(monkeypatch):
    rm = make_manager()

    sample_output = "abc123;web\nxyz789;db\n"

    def fake_run(cmd, description, timeout=None, check=True, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=sample_output, stderr="")

    monkeypatch.setattr(restore_manager, "run_command", fake_run)

    containers = rm._list_containers_on_network("mynet", include_stopped=True)

    assert containers == [("abc123", "web"), ("xyz789", "db")]


def test_stop_containers_stops_and_returns_ids(monkeypatch):
    rm = make_manager()

    captured = {}

    def fake_run(cmd, description, timeout=None, check=True, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(restore_manager, "run_command", fake_run)

    ids = rm._stop_containers([("abc123", "web"), ("xyz789", "db")], "mynet")

    assert ids == ["abc123", "xyz789"]
    assert captured["cmd"] == ["docker", "stop", "abc123", "xyz789"]


def test_stop_containers_handles_failure(monkeypatch):
    rm = make_manager()

    def fake_run(cmd, description, timeout=None, check=True, **kwargs):
        raise restore_manager.SubprocessError(cmd, 1, "boom")

    monkeypatch.setattr(restore_manager, "run_command", fake_run)

    ids = rm._stop_containers([("abc123", "web")], "mynet")

    assert ids == []


# =============================================================================
# Find Restore Points Tests
# =============================================================================


@pytest.mark.unit
class TestFindRestorePoints:
    """Tests for _find_restore_points method."""

    def test_groups_snapshots_by_backup_id(self):
        """Snapshots with same backup_id should be grouped into one RestorePoint."""
        rm = make_manager()

        # Mock snapshots with same backup_id
        rm.repo.list_snapshots.return_value = [
            {
                "id": "snap1",
                "tags": {
                    "unit": "mystack",
                    "backup_id": "uuid-123",
                    "type": "recipe",
                    "timestamp": "2025-01-15T10:00:00Z",
                },
            },
            {
                "id": "snap2",
                "tags": {
                    "unit": "mystack",
                    "backup_id": "uuid-123",
                    "type": "volume",
                    "timestamp": "2025-01-15T10:01:00Z",
                },
            },
            {
                "id": "snap3",
                "tags": {
                    "unit": "mystack",
                    "backup_id": "uuid-123",
                    "type": "volume",
                    "timestamp": "2025-01-15T10:02:00Z",
                },
            },
        ]

        points = rm._find_restore_points()

        assert len(points) == 1
        assert points[0].unit_name == "mystack"
        assert points[0].backup_id == "uuid-123"
        assert len(points[0].recipe_snapshots) == 1
        assert len(points[0].volume_snapshots) == 2

    def test_separates_different_backup_ids(self):
        """Snapshots with different backup_ids should be separate RestorePoints."""
        rm = make_manager()

        rm.repo.list_snapshots.return_value = [
            {
                "id": "snap1",
                "tags": {
                    "unit": "mystack",
                    "backup_id": "uuid-111",
                    "type": "volume",
                    "timestamp": "2025-01-15T10:00:00Z",
                },
            },
            {
                "id": "snap2",
                "tags": {
                    "unit": "mystack",
                    "backup_id": "uuid-222",
                    "type": "volume",
                    "timestamp": "2025-01-15T11:00:00Z",
                },
            },
        ]

        points = rm._find_restore_points()

        assert len(points) == 2
        backup_ids = {p.backup_id for p in points}
        assert backup_ids == {"uuid-111", "uuid-222"}

    def test_skips_snapshots_without_backup_id(self):
        """Snapshots without backup_id should be ignored."""
        rm = make_manager()

        rm.repo.list_snapshots.return_value = [
            {
                "id": "snap1",
                "tags": {
                    "unit": "mystack",
                    "backup_id": "uuid-123",
                    "type": "volume",
                    "timestamp": "2025-01-15T10:00:00Z",
                },
            },
            {
                "id": "snap2",
                "tags": {
                    "unit": "mystack",
                    # No backup_id!
                    "type": "volume",
                    "timestamp": "2025-01-15T11:00:00Z",
                },
            },
        ]

        points = rm._find_restore_points()

        assert len(points) == 1
        assert points[0].backup_id == "uuid-123"

    def test_sorts_by_timestamp_newest_first(self):
        """RestorePoints should be sorted by timestamp, newest first."""
        rm = make_manager()

        rm.repo.list_snapshots.return_value = [
            {
                "id": "snap1",
                "tags": {
                    "unit": "old_backup",
                    "backup_id": "uuid-old",
                    "type": "volume",
                    "timestamp": "2025-01-10T10:00:00Z",
                },
            },
            {
                "id": "snap2",
                "tags": {
                    "unit": "new_backup",
                    "backup_id": "uuid-new",
                    "type": "volume",
                    "timestamp": "2025-01-15T10:00:00Z",
                },
            },
        ]

        points = rm._find_restore_points()

        assert len(points) == 2
        assert points[0].unit_name == "new_backup"  # Newest first
        assert points[1].unit_name == "old_backup"

    def test_categorizes_snapshot_types(self):
        """Snapshots should be categorized by type (recipe, volume, networks)."""
        rm = make_manager()

        rm.repo.list_snapshots.return_value = [
            {
                "id": "snap1",
                "tags": {
                    "unit": "mystack",
                    "backup_id": "uuid-123",
                    "type": "recipe",
                    "timestamp": "2025-01-15T10:00:00Z",
                },
            },
            {
                "id": "snap2",
                "tags": {
                    "unit": "mystack",
                    "backup_id": "uuid-123",
                    "type": "volume",
                    "timestamp": "2025-01-15T10:01:00Z",
                },
            },
            {
                "id": "snap3",
                "tags": {
                    "unit": "mystack",
                    "backup_id": "uuid-123",
                    "type": "networks",
                    "timestamp": "2025-01-15T10:02:00Z",
                },
            },
        ]

        points = rm._find_restore_points()

        assert len(points) == 1
        assert len(points[0].recipe_snapshots) == 1
        assert len(points[0].volume_snapshots) == 1
        assert len(points[0].network_snapshots) == 1

    def test_handles_empty_snapshot_list(self):
        """Should return empty list when no snapshots exist."""
        rm = make_manager()
        rm.repo.list_snapshots.return_value = []

        points = rm._find_restore_points()

        assert points == []

    def test_handles_exception_gracefully(self):
        """Should return empty list on exception."""
        rm = make_manager()
        rm.repo.list_snapshots.side_effect = Exception("Connection failed")

        points = rm._find_restore_points()

        assert points == []


# =============================================================================
# Find Restore Points for Machine Tests
# =============================================================================


@pytest.mark.unit
class TestFindRestorePointsForMachine:
    """Tests for _find_restore_points_for_machine method."""

    def test_filters_by_hostname(self):
        """Should only include snapshots from the specified machine."""
        rm = make_manager()

        rm.repo.list_all_snapshots.return_value = [
            {
                "id": "snap1",
                "host": "server1",
                "tags": {
                    "unit": "app",
                    "backup_id": "uuid-1",
                    "type": "volume",
                    "timestamp": "2025-01-15T10:00:00Z",
                },
            },
            {
                "id": "snap2",
                "host": "server2",
                "tags": {
                    "unit": "app",
                    "backup_id": "uuid-2",
                    "type": "volume",
                    "timestamp": "2025-01-15T10:00:00Z",
                },
            },
            {
                "id": "snap3",
                "host": "server1",
                "tags": {
                    "unit": "db",
                    "backup_id": "uuid-3",
                    "type": "volume",
                    "timestamp": "2025-01-15T11:00:00Z",
                },
            },
        ]

        points = rm._find_restore_points_for_machine("server1")

        assert len(points) == 2
        unit_names = {p.unit_name for p in points}
        assert unit_names == {"app", "db"}

    def test_excludes_other_hosts(self):
        """Snapshots from other hosts should be excluded."""
        rm = make_manager()

        rm.repo.list_all_snapshots.return_value = [
            {
                "id": "snap1",
                "host": "other_server",
                "tags": {
                    "unit": "app",
                    "backup_id": "uuid-1",
                    "type": "volume",
                    "timestamp": "2025-01-15T10:00:00Z",
                },
            },
        ]

        points = rm._find_restore_points_for_machine("myserver")

        assert len(points) == 0


# =============================================================================
# Initialization Tests
# =============================================================================


@pytest.mark.unit
class TestRestoreManagerInit:
    """Tests for RestoreManager initialization."""

    def test_raises_on_conflicting_network_options(self):
        """Should raise if both force and skip network options are set."""
        config = Mock()
        config.getint.return_value = 60

        with patch.object(restore_manager.KopiaRepository, "__init__", return_value=None):
            with patch.object(restore_manager.HooksManager, "__init__", return_value=None):
                with pytest.raises(ValueError, match="Cannot force and skip"):
                    restore_manager.RestoreManager(
                        config,
                        force_recreate_networks=True,
                        skip_network_recreation=True,
                    )


# =============================================================================
# Timestamp Parsing Tests
# =============================================================================


@pytest.mark.unit
class TestTimestampParsing:
    """Tests for timestamp parsing in restore points."""

    def test_parses_iso_timestamp_with_z_suffix(self):
        """Should correctly parse ISO timestamps with Z suffix."""
        rm = make_manager()

        rm.repo.list_snapshots.return_value = [
            {
                "id": "snap1",
                "tags": {
                    "unit": "mystack",
                    "backup_id": "uuid-123",
                    "type": "volume",
                    "timestamp": "2025-01-15T10:30:45Z",
                },
            },
        ]

        points = rm._find_restore_points()

        assert len(points) == 1
        assert points[0].timestamp.year == 2025
        assert points[0].timestamp.month == 1
        assert points[0].timestamp.day == 15
        assert points[0].timestamp.hour == 10
        assert points[0].timestamp.minute == 30

    def test_handles_missing_timestamp(self):
        """Should use current time if timestamp is missing."""
        rm = make_manager()

        rm.repo.list_snapshots.return_value = [
            {
                "id": "snap1",
                "tags": {
                    "unit": "mystack",
                    "backup_id": "uuid-123",
                    "type": "volume",
                    # No timestamp
                },
            },
        ]

        points = rm._find_restore_points()

        assert len(points) == 1
        # Should have a valid timestamp (current time as fallback)
        assert points[0].timestamp is not None


# =============================================================================
# Backup Format Detection Tests
# =============================================================================


@pytest.mark.unit
class TestBackupFormatDetection:
    """Tests for _detect_backup_format method."""

    def test_detect_direct_format_from_tag(self):
        """Should detect DIRECT format from backup_format tag."""
        rm = make_manager()

        snapshot = {
            "id": "snap123",
            "tags": {"backup_format": BACKUP_FORMAT_DIRECT},
        }

        format = rm._detect_backup_format(snapshot)

        assert format == BACKUP_FORMAT_DIRECT

    def test_detect_tar_format_from_tag(self):
        """Should detect TAR format from backup_format tag."""
        rm = make_manager()

        snapshot = {
            "id": "snap123",
            "tags": {"backup_format": BACKUP_FORMAT_TAR},
        }

        format = rm._detect_backup_format(snapshot)

        assert format == BACKUP_FORMAT_TAR

    def test_legacy_snapshot_without_tag_defaults_to_tar(self):
        """Legacy snapshots without backup_format tag should default to TAR."""
        rm = make_manager()

        snapshot = {
            "id": "snap123",
            "tags": {"unit": "mystack", "type": "volume"},
            # No backup_format tag
        }

        format = rm._detect_backup_format(snapshot)

        assert format == BACKUP_FORMAT_TAR

    def test_empty_tags_defaults_to_tar(self):
        """Snapshot with empty tags should default to TAR."""
        rm = make_manager()

        snapshot = {"id": "snap123", "tags": {}}

        format = rm._detect_backup_format(snapshot)

        assert format == BACKUP_FORMAT_TAR


# =============================================================================
# Volume Restore Dispatcher Tests
# =============================================================================


@pytest.mark.unit
class TestVolumeRestoreDispatcher:
    """Tests for _execute_volume_restore dispatcher method."""

    def test_routes_to_direct_restore_for_direct_format(self, monkeypatch):
        """Should route to _execute_volume_restore_direct for DIRECT format."""
        rm = make_manager()

        snapshot = {"id": "snap123", "tags": {"backup_format": BACKUP_FORMAT_DIRECT}}

        direct_called = False

        def mock_direct(*args):
            nonlocal direct_called
            direct_called = True
            return True

        monkeypatch.setattr(rm, "_execute_volume_restore_direct", mock_direct)
        monkeypatch.setattr(rm, "_execute_volume_restore_tar", Mock(return_value=True))

        result = rm._execute_volume_restore("vol1", "unit1", "snap123", "/config", snapshot)

        assert result is True
        assert direct_called is True

    def test_routes_to_tar_restore_for_tar_format(self, monkeypatch):
        """Should route to _execute_volume_restore_tar for TAR format."""
        rm = make_manager()

        snapshot = {"id": "snap123", "tags": {"backup_format": BACKUP_FORMAT_TAR}}

        tar_called = False

        def mock_tar(*args):
            nonlocal tar_called
            tar_called = True
            return True

        monkeypatch.setattr(rm, "_execute_volume_restore_tar", mock_tar)
        monkeypatch.setattr(rm, "_execute_volume_restore_direct", Mock(return_value=True))

        result = rm._execute_volume_restore("vol1", "unit1", "snap123", "/config", snapshot)

        assert result is True
        assert tar_called is True

    def test_defaults_to_tar_when_no_snapshot_provided(self, monkeypatch):
        """Should default to TAR format when snapshot is None."""
        rm = make_manager()

        tar_called = False

        def mock_tar(*args):
            nonlocal tar_called
            tar_called = True
            return True

        monkeypatch.setattr(rm, "_execute_volume_restore_tar", mock_tar)

        result = rm._execute_volume_restore("vol1", "unit1", "snap123", "/config", snapshot=None)

        assert tar_called is True


# =============================================================================
# Volume Restore DIRECT Format Tests
# =============================================================================


@pytest.mark.unit
class TestVolumeRestoreDirect:
    """Tests for _execute_volume_restore_direct method (DIRECT format only)."""

    def test_restore_direct_success(self, monkeypatch, tmp_path):
        """Direct format restore succeeds with all steps."""
        rm = make_manager()

        # Track commands executed
        commands = []

        def fake_run(cmd, description, timeout=None, check=True, show_output=False, **kwargs):
            commands.append(cmd)
            if cmd[0] == "docker" and "ps" in cmd:
                # Return container IDs
                return subprocess.CompletedProcess(cmd, 0, stdout="container1\n", stderr="")
            elif cmd[0] == "docker" and "inspect" in cmd:
                # Return volume mountpoint
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="/var/lib/docker/volumes/vol1/_data\n", stderr=""
                )
            elif cmd[0] == "rsync":
                # rsync success
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            else:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)

        # Mock cleanup_old_safety_backups
        monkeypatch.setattr(rm, "cleanup_old_safety_backups", Mock())

        result = rm._execute_volume_restore_direct("vol1", "unit1", "snap123", "/config")

        assert result is True

        # Verify steps were executed
        assert any("docker" in cmd and "stop" in cmd for cmd in commands)  # Stop containers
        assert any(
            "docker" in cmd and "run" in cmd and "alpine" in cmd for cmd in commands
        )  # Safety backup
        assert any("kopia" in cmd and "restore" in cmd for cmd in commands)  # Kopia restore
        assert any("rsync" in cmd for cmd in commands)  # Rsync to volume
        assert any("docker" in cmd and "start" in cmd for cmd in commands)  # Start containers

    def test_stop_containers_before_restore(self, monkeypatch):
        """Containers using the volume should be stopped."""
        rm = make_manager()

        stop_called = False
        stopped_ids = []

        def fake_run(cmd, description, timeout=None, check=True, show_output=False, **kwargs):
            nonlocal stop_called, stopped_ids
            if cmd[0] == "docker" and "ps" in cmd and "volume=" in str(cmd):
                return subprocess.CompletedProcess(cmd, 0, stdout="c1\nc2\n", stderr="")
            elif cmd[0] == "docker" and "stop" in cmd:
                stop_called = True
                stopped_ids = cmd[2:]
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif cmd[0] == "docker" and "inspect" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="/tmp/vol\n", stderr="")
            elif cmd[0] == "rsync":
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            else:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm, "cleanup_old_safety_backups", Mock())

        rm._execute_volume_restore_direct("vol1", "unit1", "snap123", "/config")

        assert stop_called is True
        assert "c1" in stopped_ids
        assert "c2" in stopped_ids

    def test_safety_backup_created(self, monkeypatch):
        """Safety backup of existing volume should be created."""
        rm = make_manager()

        safety_backup_created = False

        def fake_run(cmd, description, timeout=None, check=True, show_output=False, **kwargs):
            nonlocal safety_backup_created
            if cmd[0] == "docker" and "run" in cmd and "alpine" in cmd:
                safety_backup_created = True
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif cmd[0] == "docker" and "ps" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif cmd[0] == "docker" and "inspect" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="/tmp/vol\n", stderr="")
            elif cmd[0] == "rsync":
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            else:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm, "cleanup_old_safety_backups", Mock())

        rm._execute_volume_restore_direct("vol1", "unit1", "snap123", "/config")

        assert safety_backup_created is True

    def test_restart_containers_after_restore(self, monkeypatch):
        """Containers should be restarted after restore completes."""
        rm = make_manager()

        start_called = False
        started_ids = []

        def fake_run(cmd, description, timeout=None, check=True, show_output=False, **kwargs):
            nonlocal start_called, started_ids
            if cmd[0] == "docker" and "ps" in cmd:
                # Return containers
                return subprocess.CompletedProcess(cmd, 0, stdout="c1\nc2\n", stderr="")
            elif cmd[0] == "docker" and "start" in cmd:
                start_called = True
                started_ids = cmd[2:]
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif cmd[0] == "docker" and "inspect" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="/tmp/vol\n", stderr="")
            elif cmd[0] == "rsync":
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            else:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm, "cleanup_old_safety_backups", Mock())

        rm._execute_volume_restore_direct("vol1", "unit1", "snap123", "/config")

        assert start_called is True
        assert "c1" in started_ids
        assert "c2" in started_ids

    def test_rsync_fallback_to_cp_on_failure(self, monkeypatch):
        """Should fallback to cp if rsync fails."""
        rm = make_manager()

        cp_used = False

        def fake_run(cmd, description, timeout=None, check=True, show_output=False, **kwargs):
            nonlocal cp_used
            if cmd[0] == "rsync":
                # rsync fails
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="rsync error")
            elif cmd[0] == "cp":
                cp_used = True
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif cmd[0] == "docker" and "ps" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif cmd[0] == "docker" and "inspect" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="/tmp/vol\n", stderr="")
            else:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(restore_manager.subprocess, "run", Mock())
        monkeypatch.setattr(rm, "cleanup_old_safety_backups", Mock())

        rm._execute_volume_restore_direct("vol1", "unit1", "snap123", "/config")

        assert cp_used is True

    def test_handles_subprocess_error(self, monkeypatch):
        """Should return False on SubprocessError."""
        rm = make_manager()

        def fake_run(cmd, description, timeout=None, check=True, show_output=False, **kwargs):
            raise restore_manager.SubprocessError(cmd, 1, "Command failed")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)

        result = rm._execute_volume_restore_direct("vol1", "unit1", "snap123", "/config")

        assert result is False

    def test_handles_empty_volume_mountpoint(self, monkeypatch):
        """Should return False if volume mountpoint cannot be determined."""
        rm = make_manager()

        def fake_run(cmd, description, timeout=None, check=True, show_output=False, **kwargs):
            if cmd[0] == "docker" and "inspect" in cmd:
                # Empty mountpoint
                return subprocess.CompletedProcess(cmd, 0, stdout="\n", stderr="")
            elif cmd[0] == "docker" and "ps" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            else:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)

        result = rm._execute_volume_restore_direct("vol1", "unit1", "snap123", "/config")

        assert result is False

    def test_cleanup_old_backups_called(self, monkeypatch):
        """cleanup_old_safety_backups should be called after restore."""
        rm = make_manager()

        cleanup_called = False

        def mock_cleanup(keep_last=3):
            nonlocal cleanup_called
            cleanup_called = True

        def fake_run(cmd, description, timeout=None, check=True, show_output=False, **kwargs):
            if cmd[0] == "docker" and "ps" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif cmd[0] == "docker" and "inspect" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="/tmp/vol\n", stderr="")
            elif cmd[0] == "rsync":
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            else:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm, "cleanup_old_safety_backups", mock_cleanup)

        rm._execute_volume_restore_direct("vol1", "unit1", "snap123", "/config")

        assert cleanup_called is True

    def test_handles_no_containers_using_volume(self, monkeypatch):
        """Should handle case where no containers are using the volume."""
        rm = make_manager()

        def fake_run(cmd, description, timeout=None, check=True, show_output=False, **kwargs):
            if cmd[0] == "docker" and "ps" in cmd:
                # No containers
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif cmd[0] == "docker" and "inspect" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="/tmp/vol\n", stderr="")
            elif cmd[0] == "rsync":
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            else:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm, "cleanup_old_safety_backups", Mock())

        result = rm._execute_volume_restore_direct("vol1", "unit1", "snap123", "/config")

        assert result is True


# =============================================================================
# Network Recreation Conflict Tests
# =============================================================================


@pytest.mark.unit
class TestNetworkRecreationConflicts:
    """Tests for network recreation conflict handling during restore."""

    def test_skip_existing_network_when_flag_set(self, monkeypatch, tmp_path):
        """Should skip network recreation when skip_network_recreation flag is set."""
        rm = make_manager()
        rm.skip_network_recreation = True

        # Mock restore point with network snapshot
        rp = RestorePoint(
            unit_name="teststack",
            backup_id="uuid-123",
            timestamp=datetime.now(timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[{"id": "netsnap123", "tags": {}}],
        )

        networks_dir = tmp_path / "networks"
        networks_dir.mkdir()

        # Create networks.json
        networks_json = networks_dir / "networks.json"
        networks_json.write_text('[{"Name": "mynetwork", "Driver": "bridge"}]')

        network_removed = False

        def fake_run(cmd, description, timeout=None, **kwargs):
            nonlocal network_removed
            if "network" in cmd and "ls" in cmd:
                # Network already exists
                return subprocess.CompletedProcess(cmd, 0, stdout="mynetwork\n", stderr="")
            elif "network" in cmd and "rm" in cmd:
                network_removed = True
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm.repo, "restore_snapshot", Mock())

        count = rm._restore_networks(rp, tmp_path)

        # Network should not be removed/recreated
        assert network_removed is False
        assert count == 0

    def test_force_recreate_network_with_flag(self, monkeypatch, tmp_path):
        """Should force recreate network when force_recreate_networks flag is set."""
        rm = make_manager()
        rm.force_recreate_networks = True
        rm.non_interactive = False

        rp = RestorePoint(
            unit_name="teststack",
            backup_id="uuid-123",
            timestamp=datetime.now(timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[{"id": "netsnap123", "tags": {}}],
        )

        networks_dir = tmp_path / "networks"
        networks_dir.mkdir()
        networks_json = networks_dir / "networks.json"
        networks_json.write_text('[{"Name": "mynetwork", "Driver": "bridge"}]')

        network_removed = False
        network_created = False

        def fake_run(cmd, description, timeout=None, **kwargs):
            nonlocal network_removed, network_created
            if "network" in cmd and "ls" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="mynetwork\n", stderr="")
            elif "network" in cmd and "rm" in cmd:
                network_removed = True
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif "network" in cmd and "create" in cmd:
                network_created = True
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif "ps" in cmd:
                # No containers attached
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm.repo, "restore_snapshot", Mock())
        monkeypatch.setattr(rm, "_list_containers_on_network", Mock(return_value=[]))

        count = rm._restore_networks(rp, tmp_path)

        # Network should be removed and recreated
        assert network_removed is True
        assert network_created is True
        assert count == 1

    def test_recreate_with_attached_containers(self, monkeypatch, tmp_path):
        """Should stop containers, recreate network, and restart containers."""
        rm = make_manager()
        rm.force_recreate_networks = True

        rp = RestorePoint(
            unit_name="teststack",
            backup_id="uuid-123",
            timestamp=datetime.now(timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[{"id": "netsnap123", "tags": {}}],
        )

        networks_dir = tmp_path / "networks"
        networks_dir.mkdir()
        networks_json = networks_dir / "networks.json"
        networks_json.write_text('[{"Name": "mynetwork", "Driver": "bridge"}]')

        containers_stopped = False
        containers_restarted = False

        def mock_list_containers(net_name, include_stopped=False):
            return [("c1", "web"), ("c2", "db")]

        def mock_stop_containers(containers, net_name):
            nonlocal containers_stopped
            containers_stopped = True
            return ["c1", "c2"]

        def mock_restart_containers(ids, net_name):
            nonlocal containers_restarted
            containers_restarted = True

        def fake_run(cmd, description, timeout=None, **kwargs):
            if "network" in cmd and "ls" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="mynetwork\n", stderr="")
            elif "network" in cmd and "rm" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif "network" in cmd and "create" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm.repo, "restore_snapshot", Mock())
        monkeypatch.setattr(rm, "_list_containers_on_network", mock_list_containers)
        monkeypatch.setattr(rm, "_stop_containers", mock_stop_containers)
        monkeypatch.setattr(rm, "_restart_containers", mock_restart_containers)
        monkeypatch.setattr(rm, "_disconnect_containers_from_network", Mock(return_value=True))
        monkeypatch.setattr(rm, "_reconnect_containers_to_network", Mock())

        count = rm._restore_networks(rp, tmp_path)

        # Containers should be stopped and restarted
        assert containers_stopped is True
        assert containers_restarted is True
        assert count == 1

    def test_rollback_on_network_removal_failure(self, monkeypatch, tmp_path):
        """Should rollback (reconnect containers) if network removal fails."""
        rm = make_manager()
        rm.force_recreate_networks = True

        rp = RestorePoint(
            unit_name="teststack",
            backup_id="uuid-123",
            timestamp=datetime.now(timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[{"id": "netsnap123", "tags": {}}],
        )

        networks_dir = tmp_path / "networks"
        networks_dir.mkdir()
        networks_json = networks_dir / "networks.json"
        networks_json.write_text('[{"Name": "mynetwork", "Driver": "bridge"}]')

        containers_reconnected = False
        containers_restarted = False

        def mock_reconnect(net_name, containers):
            nonlocal containers_reconnected
            containers_reconnected = True

        def mock_restart(ids, net_name):
            nonlocal containers_restarted
            containers_restarted = True

        def fake_run(cmd, description, timeout=None, **kwargs):
            if "network" in cmd and "ls" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="mynetwork\n", stderr="")
            elif "network" in cmd and "rm" in cmd:
                # Removal fails
                raise restore_manager.SubprocessError(cmd, 1, "network has active endpoints")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm.repo, "restore_snapshot", Mock())
        monkeypatch.setattr(rm, "_list_containers_on_network", Mock(return_value=[("c1", "web")]))
        monkeypatch.setattr(rm, "_stop_containers", Mock(return_value=["c1"]))
        monkeypatch.setattr(rm, "_disconnect_containers_from_network", Mock(return_value=True))
        monkeypatch.setattr(rm, "_reconnect_containers_to_network", mock_reconnect)
        monkeypatch.setattr(rm, "_restart_containers", mock_restart)

        count = rm._restore_networks(rp, tmp_path)

        # Should rollback: reconnect containers and restart them
        assert containers_reconnected is True
        assert containers_restarted is True
        assert count == 0  # No networks successfully restored

    def test_abort_if_cannot_stop_running_containers(self, monkeypatch, tmp_path):
        """Should abort recreation if running containers cannot be stopped."""
        rm = make_manager()
        rm.force_recreate_networks = True

        rp = RestorePoint(
            unit_name="teststack",
            backup_id="uuid-123",
            timestamp=datetime.now(timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[{"id": "netsnap123", "tags": {}}],
        )

        networks_dir = tmp_path / "networks"
        networks_dir.mkdir()
        networks_json = networks_dir / "networks.json"
        networks_json.write_text('[{"Name": "mynetwork", "Driver": "bridge"}]')

        network_removed = False

        def fake_run(cmd, description, timeout=None, **kwargs):
            nonlocal network_removed
            if "network" in cmd and "ls" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="mynetwork\n", stderr="")
            elif "network" in cmd and "rm" in cmd:
                network_removed = True
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm.repo, "restore_snapshot", Mock())
        monkeypatch.setattr(rm, "_list_containers_on_network", Mock(return_value=[("c1", "web")]))
        # Stop fails - returns empty list
        monkeypatch.setattr(rm, "_stop_containers", Mock(return_value=[]))

        count = rm._restore_networks(rp, tmp_path)

        # Network should NOT be removed (aborted)
        assert network_removed is False
        assert count == 0

    def test_non_interactive_auto_recreates_network(self, monkeypatch, tmp_path):
        """Should auto-recreate network in non-interactive mode."""
        rm = make_manager()
        rm.non_interactive = True
        rm.force_recreate_networks = False  # Not forced, but non-interactive

        rp = RestorePoint(
            unit_name="teststack",
            backup_id="uuid-123",
            timestamp=datetime.now(timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[{"id": "netsnap123", "tags": {}}],
        )

        networks_dir = tmp_path / "networks"
        networks_dir.mkdir()
        networks_json = networks_dir / "networks.json"
        networks_json.write_text('[{"Name": "mynetwork", "Driver": "bridge"}]')

        network_created = False

        def fake_run(cmd, description, timeout=None, **kwargs):
            nonlocal network_created
            if "network" in cmd and "ls" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="mynetwork\n", stderr="")
            elif "network" in cmd and "rm" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif "network" in cmd and "create" in cmd:
                network_created = True
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif "ps" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm.repo, "restore_snapshot", Mock())
        monkeypatch.setattr(rm, "_list_containers_on_network", Mock(return_value=[]))

        count = rm._restore_networks(rp, tmp_path)

        # Network should be auto-recreated
        assert network_created is True
        assert count == 1

    def test_network_creation_with_ipam_config(self, monkeypatch, tmp_path):
        """Should create network with IPAM configuration from snapshot."""
        rm = make_manager()
        rm.force_recreate_networks = True

        rp = RestorePoint(
            unit_name="teststack",
            backup_id="uuid-123",
            timestamp=datetime.now(timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[{"id": "netsnap123", "tags": {}}],
        )

        networks_dir = tmp_path / "networks"
        networks_dir.mkdir()
        networks_json = networks_dir / "networks.json"
        networks_json.write_text(
            """[{
            "Name": "mynetwork",
            "Driver": "bridge",
            "IPAM": {
                "Config": [{
                    "Subnet": "172.20.0.0/16",
                    "Gateway": "172.20.0.1",
                    "IPRange": "172.20.10.0/24"
                }]
            }
        }]"""
        )

        create_cmd = []

        def fake_run(cmd, description, timeout=None, **kwargs):
            nonlocal create_cmd
            if "network" in cmd and "ls" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="mynetwork\n", stderr="")
            elif "network" in cmd and "rm" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif "network" in cmd and "create" in cmd:
                create_cmd = cmd
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            elif "ps" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)
        monkeypatch.setattr(rm.repo, "restore_snapshot", Mock())
        monkeypatch.setattr(rm, "_list_containers_on_network", Mock(return_value=[]))

        count = rm._restore_networks(rp, tmp_path)

        # Verify IPAM config was included
        assert "--subnet" in create_cmd
        assert "172.20.0.0/16" in create_cmd
        assert "--gateway" in create_cmd
        assert "172.20.0.1" in create_cmd
        assert "--ip-range" in create_cmd
        assert "172.20.10.0/24" in create_cmd
        assert count == 1

    def test_handles_missing_networks_json(self, monkeypatch, tmp_path):
        """Should handle missing networks.json gracefully."""
        rm = make_manager()

        rp = RestorePoint(
            unit_name="teststack",
            backup_id="uuid-123",
            timestamp=datetime.now(timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[{"id": "netsnap123", "tags": {}}],
        )

        networks_dir = tmp_path / "networks"
        networks_dir.mkdir()
        # No networks.json file created

        monkeypatch.setattr(rm.repo, "restore_snapshot", Mock())

        count = rm._restore_networks(rp, tmp_path)

        # Should handle gracefully
        assert count == 0

    def test_handles_no_network_snapshots(self, monkeypatch, tmp_path):
        """Should return 0 when no network snapshots exist."""
        rm = make_manager()

        rp = RestorePoint(
            unit_name="teststack",
            backup_id="uuid-123",
            timestamp=datetime.now(timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],  # No network snapshots
        )

        count = rm._restore_networks(rp, tmp_path)

        assert count == 0


# =============================================================================
# Interactive Restore Flow Tests
# =============================================================================


@pytest.mark.unit
class TestInteractiveRestoreFlow:
    """Tests for interactive restore wizard flow."""

    def test_dependency_check_failure_aborts_restore(self, monkeypatch, capsys):
        """Should abort if dependencies are missing."""
        rm = make_manager()

        # Mock missing Docker
        mock_deps = Mock()
        mock_deps.check_docker.return_value = False
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Should show missing dependency and abort
        assert "Missing required dependencies" in output
        assert "Docker" in output
        assert "Install missing dependencies" in output

    def test_repository_not_connected_aborts(self, monkeypatch, capsys):
        """Should abort if repository is not connected."""
        rm = make_manager()

        # Mock deps OK but repo not connected
        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True

        rm.repo.is_connected.return_value = False

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Should show not connected message
        assert "Not connected to Kopia repository" in output
        assert "kopi-docka init" in output

    def test_no_backups_found_aborts(self, monkeypatch, capsys):
        """Should abort if no restore points found."""
        rm = make_manager()

        # Mock deps OK, repo connected, but no backups
        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True

        rm.repo.is_connected.return_value = True
        monkeypatch.setattr(rm, "_find_restore_points", Mock(return_value=[]))

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Should show no backups message
        assert "No backups found" in output

    def test_session_selection_interactive(self, monkeypatch, capsys):
        """User selects a session interactively."""
        rm = make_manager()
        rm.non_interactive = False

        # Mock deps and repo
        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True
        rm.repo.is_connected.return_value = True

        # Mock restore points
        rp1 = RestorePoint(
            unit_name="unit1",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[{"id": "vol1", "tags": {}}],
            network_snapshots=[],
        )

        monkeypatch.setattr(rm, "_find_restore_points", Mock(return_value=[rp1]))
        monkeypatch.setattr(rm, "_restore_unit", Mock())

        # Mock user input: select session 1, confirm yes
        inputs = iter(["1", "yes"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Verify session was shown and selected
        assert "Available backup sessions" in output
        assert "unit1" in output
        assert "This will guide you through restoring" in output

        # Verify restore was called
        rm._restore_unit.assert_called_once()

    def test_quit_at_session_selection(self, monkeypatch, capsys):
        """User quits at session selection."""
        rm = make_manager()
        rm.non_interactive = False

        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True
        rm.repo.is_connected.return_value = True

        rp1 = RestorePoint(
            unit_name="unit1",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],
        )

        monkeypatch.setattr(rm, "_find_restore_points", Mock(return_value=[rp1]))
        monkeypatch.setattr(rm, "_restore_unit", Mock())

        # User enters 'q'
        monkeypatch.setattr("builtins.input", lambda _: "q")

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Verify quit message
        assert "Restore cancelled" in output

        # Verify restore was NOT called
        rm._restore_unit.assert_not_called()

    def test_quit_at_unit_selection(self, monkeypatch, capsys):
        """User quits at unit selection."""
        rm = make_manager()
        rm.non_interactive = False

        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True
        rm.repo.is_connected.return_value = True

        # Multiple units in same session
        rp1 = RestorePoint(
            unit_name="unit1",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],
        )
        rp2 = RestorePoint(
            unit_name="unit2",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 1, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],
        )

        monkeypatch.setattr(rm, "_find_restore_points", Mock(return_value=[rp1, rp2]))
        monkeypatch.setattr(rm, "_restore_unit", Mock())

        # User selects session 1, then quits at unit selection
        inputs = iter(["1", "q"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Verify quit message
        assert "Restore cancelled" in output
        rm._restore_unit.assert_not_called()

    def test_quit_at_confirmation(self, monkeypatch, capsys):
        """User quits at final confirmation."""
        rm = make_manager()
        rm.non_interactive = False

        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True
        rm.repo.is_connected.return_value = True

        rp1 = RestorePoint(
            unit_name="unit1",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],
        )

        monkeypatch.setattr(rm, "_find_restore_points", Mock(return_value=[rp1]))
        monkeypatch.setattr(rm, "_restore_unit", Mock())

        # User selects session, then says 'no' at confirmation
        inputs = iter(["1", "no"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Verify cancelled message
        assert "Restore cancelled" in output
        rm._restore_unit.assert_not_called()

    def test_non_interactive_auto_selects(self, monkeypatch, capsys):
        """Non-interactive mode auto-selects without prompts."""
        rm = make_manager()
        rm.non_interactive = True

        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True
        rm.repo.is_connected.return_value = True

        # Multiple sessions and units
        rp1 = RestorePoint(
            unit_name="unit1",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],
        )
        rp2 = RestorePoint(
            unit_name="unit2",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 1, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],
        )

        monkeypatch.setattr(rm, "_find_restore_points", Mock(return_value=[rp1, rp2]))
        monkeypatch.setattr(rm, "_restore_unit", Mock())

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Verify auto-selection messages
        assert "Auto-selecting most recent session" in output
        assert "Auto-selecting first unit" in output
        assert "Auto-confirming restore" in output

        # Verify restore was called
        rm._restore_unit.assert_called_once()

    def test_single_unit_auto_selected(self, monkeypatch, capsys):
        """Single unit in session is auto-selected."""
        rm = make_manager()
        rm.non_interactive = False

        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True
        rm.repo.is_connected.return_value = True

        # Single unit
        rp1 = RestorePoint(
            unit_name="unit1",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],
        )

        monkeypatch.setattr(rm, "_find_restore_points", Mock(return_value=[rp1]))
        monkeypatch.setattr(rm, "_restore_unit", Mock())

        # Only need to confirm
        monkeypatch.setattr("builtins.input", lambda prompt: "1" if "session" in prompt else "yes")

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        # Should skip unit selection since only one unit
        rm._restore_unit.assert_called_once()

    def test_invalid_session_selection_retries(self, monkeypatch, capsys):
        """Invalid session number prompts retry."""
        rm = make_manager()
        rm.non_interactive = False

        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True
        rm.repo.is_connected.return_value = True

        rp1 = RestorePoint(
            unit_name="unit1",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],
        )

        monkeypatch.setattr(rm, "_find_restore_points", Mock(return_value=[rp1]))
        monkeypatch.setattr(rm, "_restore_unit", Mock())

        # Invalid input, then valid
        inputs = iter(["99", "1", "yes"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Verify error message shown
        assert "Invalid selection" in output

        # But restore eventually succeeds
        rm._restore_unit.assert_called_once()

    def test_keyboard_interrupt_at_session_selection(self, monkeypatch, capsys):
        """KeyboardInterrupt cancels restore gracefully."""
        rm = make_manager()
        rm.non_interactive = False

        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True
        rm.repo.is_connected.return_value = True

        rp1 = RestorePoint(
            unit_name="unit1",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],
        )

        monkeypatch.setattr(rm, "_find_restore_points", Mock(return_value=[rp1]))
        monkeypatch.setattr(rm, "_restore_unit", Mock())

        # Simulate Ctrl+C
        def raise_interrupt(_):
            raise KeyboardInterrupt()

        monkeypatch.setattr("builtins.input", raise_interrupt)

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Verify cancelled message
        assert "Restore cancelled" in output
        rm._restore_unit.assert_not_called()

    def test_multiple_units_requires_selection(self, monkeypatch, capsys):
        """Multiple units in session requires user selection."""
        rm = make_manager()
        rm.non_interactive = False

        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True
        rm.repo.is_connected.return_value = True

        # Two units in same session
        rp1 = RestorePoint(
            unit_name="unit1",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[{"id": "vol1", "tags": {}}],
            network_snapshots=[],
        )
        rp2 = RestorePoint(
            unit_name="unit2",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 1, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[{"id": "vol2", "tags": {}}],
            network_snapshots=[],
        )

        monkeypatch.setattr(rm, "_find_restore_points", Mock(return_value=[rp1, rp2]))
        monkeypatch.setattr(rm, "_restore_unit", Mock())

        # Select session 1, then unit 2
        inputs = iter(["1", "2", "yes"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Verify unit selection prompt shown
        assert "Units in this backup session" in output
        assert "unit1" in output
        assert "unit2" in output

        # Verify correct unit was restored
        # Note: After sorting by timestamp (newest first), rp2 is first, rp1 is second
        # So selecting "2" selects rp1 (unit1)
        rm._restore_unit.assert_called_once()
        restored_unit = rm._restore_unit.call_args[0][0]
        assert restored_unit.unit_name == "unit1"

    def test_session_grouping_by_time(self, monkeypatch, capsys):
        """Restore points are grouped into sessions by 5-minute window."""
        rm = make_manager()
        rm.non_interactive = True

        mock_deps = Mock()
        mock_deps.check_docker.return_value = True
        mock_deps.check_tar.return_value = True
        mock_deps.check_kopia.return_value = True
        rm.repo.is_connected.return_value = True

        # Two sessions: one at 10:00, another at 11:00
        rp1 = RestorePoint(
            unit_name="unit1",
            backup_id="uuid-1",
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],
        )
        rp2 = RestorePoint(
            unit_name="unit2",
            backup_id="uuid-2",
            timestamp=datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc),  # 1 hour later
            recipe_snapshots=[],
            volume_snapshots=[],
            network_snapshots=[],
        )

        monkeypatch.setattr(rm, "_find_restore_points", Mock(return_value=[rp2, rp1]))
        monkeypatch.setattr(rm, "_restore_unit", Mock())

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Should show 2 sessions
        assert "1. 📅" in output
        assert "2. 📅" in output

    def test_all_dependencies_missing(self, monkeypatch, capsys):
        """Should list all missing dependencies."""
        rm = make_manager()

        # All deps missing
        mock_deps = Mock()
        mock_deps.check_docker.return_value = False
        mock_deps.check_tar.return_value = False
        mock_deps.check_kopia.return_value = False

        with patch("kopi_docka.cores.dependency_manager.DependencyManager", return_value=mock_deps):
            rm.interactive_restore()

        captured = capsys.readouterr()
        output = captured.out

        # Should show all three
        assert "Docker" in output
        assert "tar" in output
        assert "Kopia" in output
        assert "Missing required dependencies" in output


# =============================================================================
# Container Network Operations Tests (disconnect/reconnect/restart)
# =============================================================================


@pytest.mark.unit
class TestContainerNetworkOperations:
    """Tests for container disconnect/reconnect/restart operations."""

    def test_disconnect_containers_from_network(self, monkeypatch):
        """Disconnects all containers from specified network."""
        rm = make_manager()

        run_calls = []

        def fake_run(cmd, description, timeout=None, check=True, **kwargs):
            run_calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)

        containers = [("abc123", "web"), ("xyz789", "db")]
        rm._disconnect_containers_from_network("mynet", containers)

        # Should call docker network disconnect for each container with -f flag
        assert len(run_calls) == 2
        assert run_calls[0] == ["docker", "network", "disconnect", "-f", "mynet", "abc123"]
        assert run_calls[1] == ["docker", "network", "disconnect", "-f", "mynet", "xyz789"]

    def test_disconnect_containers_handles_failure(self, monkeypatch):
        """Continues disconnecting other containers if one fails."""
        rm = make_manager()

        call_count = [0]

        def fake_run(cmd, description, timeout=None, check=True, **kwargs):
            call_count[0] += 1
            # Return failure for first container, success for second
            if call_count[0] == 1:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not found")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)

        containers = [("abc123", "web"), ("xyz789", "db")]
        result = rm._disconnect_containers_from_network("mynet", containers)

        # Should try both, but only return successful ones
        assert call_count[0] == 2
        assert result == ["xyz789"]  # Only the second one succeeded

    def test_reconnect_containers_to_network(self, monkeypatch):
        """Reconnects containers to network after recreation."""
        rm = make_manager()

        run_calls = []

        def fake_run(cmd, description, timeout=None, check=True, **kwargs):
            run_calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)

        containers = [("abc123", "web"), ("xyz789", "db")]
        rm._reconnect_containers_to_network("mynet", containers)

        # Should call docker network connect for each container
        assert len(run_calls) == 2
        assert run_calls[0] == ["docker", "network", "connect", "mynet", "abc123"]
        assert run_calls[1] == ["docker", "network", "connect", "mynet", "xyz789"]

    def test_reconnect_containers_handles_failure(self, monkeypatch):
        """Continues reconnecting other containers if one fails."""
        rm = make_manager()

        call_count = [0]

        def fake_run(cmd, description, timeout=None, check=True, **kwargs):
            call_count[0] += 1
            # Return failure for first container, success for second
            if call_count[0] == 1:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network not found")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)

        containers = [("abc123", "web"), ("xyz789", "db")]
        rm._reconnect_containers_to_network("mynet", containers)

        # Should attempt both
        assert call_count[0] == 2

    def test_restart_containers_success(self, monkeypatch):
        """Restarts all containers successfully."""
        rm = make_manager()
        rm.start_timeout = 60

        run_calls = []

        def fake_run(cmd, description, timeout=None, check=True, **kwargs):
            run_calls.append((cmd, timeout))
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)

        container_ids = ["abc123", "xyz789"]
        rm._restart_containers(container_ids, "mynet")

        # Should call docker start once with all containers
        assert len(run_calls) == 1
        assert run_calls[0][0] == ["docker", "start", "abc123", "xyz789"]
        assert run_calls[0][1] == 60

    def test_restart_containers_handles_failure(self, monkeypatch):
        """Logs error when container restart fails."""
        rm = make_manager()

        def fake_run(cmd, description, timeout=None, check=True, **kwargs):
            raise restore_manager.SubprocessError(cmd, 1, "container exited")

        monkeypatch.setattr(restore_manager, "run_command", fake_run)

        container_ids = ["abc123"]
        # Should not raise exception
        rm._restart_containers(container_ids, "mynet")


# =============================================================================
# Secret Detection Tests
# =============================================================================


@pytest.mark.unit
class TestSecretDetection:
    """Tests for _check_for_secrets method."""

    def test_check_for_secrets_detects_redacted_in_inspect_json(self, tmp_path, capsys):
        """Detects redacted secrets in inspect JSON files."""
        rm = make_manager()

        recipe_dir = tmp_path / "mystack"
        recipe_dir.mkdir()
        (recipe_dir / "container_inspect.json").write_text('{"env": ["PASSWORD=***REDACTED***"]}')

        rm._check_for_secrets(recipe_dir)

        captured = capsys.readouterr()
        output = captured.out

        assert "REDACTED" in output or "redacted" in output

    def test_check_for_secrets_no_warning_when_clean(self, tmp_path, capsys):
        """No warning when no redacted secrets found."""
        rm = make_manager()

        recipe_dir = tmp_path / "mystack"
        recipe_dir.mkdir()
        (recipe_dir / "docker_inspect.json").write_text('{"env": ["PATH=/usr/bin"]}')

        rm._check_for_secrets(recipe_dir)

        captured = capsys.readouterr()
        output = captured.out

        # Should not mention redacted secrets
        assert "REDACTED" not in output


# =============================================================================
# Safety Backup Cleanup Tests
# =============================================================================


@pytest.mark.unit
class TestSafetyBackupCleanup:
    """Tests for cleanup_old_safety_backups method."""

    def test_cleanup_handles_no_backups(self, monkeypatch):
        """Cleanup handles case with no safety backups."""
        rm = make_manager()

        # Mock glob to return empty list
        monkeypatch.setattr("pathlib.Path.glob", lambda self, pattern: [])

        # Should not raise exception
        rm.cleanup_old_safety_backups(keep_last=3)


# =============================================================================
# User ID Helpers Tests
# =============================================================================


@pytest.mark.unit
class TestUserIdHelpers:
    """Tests for _get_real_user_ids method."""

    def test_get_real_user_ids_from_sudo(self, monkeypatch):
        """Gets real user IDs from SUDO_UID and SUDO_GID."""
        rm = make_manager()

        monkeypatch.setenv("SUDO_UID", "1000")
        monkeypatch.setenv("SUDO_GID", "1000")
        monkeypatch.setenv("SUDO_USER", "testuser")

        uid, gid, user = rm._get_real_user_ids()

        assert uid == 1000
        assert gid == 1000
        assert user == "testuser"

    def test_get_real_user_ids_fallback_to_current(self, monkeypatch):
        """Falls back to current user when not running via sudo."""
        rm = make_manager()

        # Remove SUDO env vars
        monkeypatch.delenv("SUDO_UID", raising=False)
        monkeypatch.delenv("SUDO_GID", raising=False)
        monkeypatch.delenv("SUDO_USER", raising=False)

        with patch("os.getuid", return_value=1001):
            with patch("os.getgid", return_value=1001):
                uid, gid, user = rm._get_real_user_ids()

        assert uid == 1001
        assert gid == 1001
        assert user == "root"  # Default when SUDO_USER not set


# =============================================================================
# Volume Restore TAR Tests (LEGACY)
# =============================================================================


@pytest.mark.unit
class TestVolumeRestoreTar:
    """Tests for _execute_volume_restore_tar method (legacy TAR format)."""

    @patch("kopi_docka.cores.restore_manager.run_command")
    @patch("kopi_docka.cores.restore_manager.shutil.rmtree")
    @patch("kopi_docka.cores.restore_manager.tempfile.mkdtemp")
    def test_successful_tar_restore(self, mock_mkdtemp, mock_rmtree, mock_run):
        """Should successfully restore TAR format backup."""
        from pathlib import Path
        import tempfile

        rm = make_manager()

        # Create a real temp directory for testing
        real_temp_dir = Path(tempfile.mkdtemp(prefix="test-tar-restore-"))
        mock_mkdtemp.return_value = str(real_temp_dir)

        try:
            # Create the expected directory structure
            volumes_dir = real_temp_dir / "volumes" / "myunit"
            volumes_dir.mkdir(parents=True, exist_ok=True)

            # Create a fake tar file
            tar_file = volumes_dir / "myvolume"
            tar_file.write_bytes(b"fake tar content")

            # Mock run_command responses
            mock_run.side_effect = [
                CompletedProcess([], 0, stdout="", stderr=""),  # docker ps -q
                CompletedProcess([], 0, stdout="", stderr=""),  # safety backup
                CompletedProcess([], 0, stdout="", stderr=""),  # kopia restore
                CompletedProcess([], 0, stdout="tar archive", stderr=""),  # file type check
                CompletedProcess([], 0, stdout="", stderr=""),  # docker run (tar extract)
                CompletedProcess([], 0, stdout="c1\nc2", stderr=""),  # docker ps -q (restart)
                CompletedProcess([], 0, stdout="", stderr=""),  # docker start
            ]

            result = rm._execute_volume_restore_tar("myvolume", "myunit", "snap123", "/tmp/config")

            assert result is True
            # Verify kopia restore was called
            kopia_calls = [c for c in mock_run.call_args_list if "kopia" in str(c)]
            assert len(kopia_calls) == 1

        finally:
            # Cleanup
            if real_temp_dir.exists():
                import shutil

                shutil.rmtree(real_temp_dir)

    @patch("kopi_docka.cores.restore_manager.run_command")
    @patch("kopi_docka.cores.restore_manager.shutil.rmtree")
    @patch("kopi_docka.cores.restore_manager.tempfile.mkdtemp")
    def test_tar_file_not_found(self, mock_mkdtemp, mock_rmtree, mock_run):
        """Should return False if tar file not found after restore."""
        from pathlib import Path
        import tempfile

        rm = make_manager()

        # Create a real temp directory
        real_temp_dir = Path(tempfile.mkdtemp(prefix="test-tar-missing-"))
        mock_mkdtemp.return_value = str(real_temp_dir)

        try:
            # Create directory structure but NO tar file
            volumes_dir = real_temp_dir / "volumes" / "myunit"
            volumes_dir.mkdir(parents=True, exist_ok=True)
            # Don't create the tar file

            # Mock run_command responses
            mock_run.side_effect = [
                CompletedProcess([], 0, stdout="", stderr=""),  # docker ps -q
                CompletedProcess([], 0, stdout="", stderr=""),  # safety backup
                CompletedProcess([], 0, stdout="", stderr=""),  # kopia restore
            ]

            result = rm._execute_volume_restore_tar("myvolume", "myunit", "snap123", "/tmp/config")

            assert result is False

        finally:
            # Cleanup
            if real_temp_dir.exists():
                import shutil

                shutil.rmtree(real_temp_dir)

    @patch("kopi_docka.cores.restore_manager.run_command")
    @patch("kopi_docka.cores.restore_manager.shutil.rmtree")
    @patch("kopi_docka.cores.restore_manager.tempfile.mkdtemp")
    def test_invalid_tar_file(self, mock_mkdtemp, mock_rmtree, mock_run):
        """Should return False if restored file is not a tar archive."""
        from pathlib import Path
        import tempfile

        rm = make_manager()

        # Create a real temp directory
        real_temp_dir = Path(tempfile.mkdtemp(prefix="test-tar-invalid-"))
        mock_mkdtemp.return_value = str(real_temp_dir)

        try:
            # Create directory structure with a non-tar file
            volumes_dir = real_temp_dir / "volumes" / "myunit"
            volumes_dir.mkdir(parents=True, exist_ok=True)

            # Create a file that's not a tar archive
            tar_file = volumes_dir / "myvolume"
            tar_file.write_text("not a tar file")

            # Mock run_command responses
            mock_run.side_effect = [
                CompletedProcess([], 0, stdout="", stderr=""),  # docker ps -q
                CompletedProcess([], 0, stdout="", stderr=""),  # safety backup
                CompletedProcess([], 0, stdout="", stderr=""),  # kopia restore
                CompletedProcess(
                    [], 0, stdout="ASCII text", stderr=""
                ),  # file type check - NOT tar
            ]

            result = rm._execute_volume_restore_tar("myvolume", "myunit", "snap123", "/tmp/config")

            assert result is False

        finally:
            # Cleanup
            if real_temp_dir.exists():
                import shutil

                shutil.rmtree(real_temp_dir)

    @patch("kopi_docka.cores.restore_manager.run_command")
    @patch("kopi_docka.cores.restore_manager.shutil.rmtree")
    @patch("kopi_docka.cores.restore_manager.tempfile.mkdtemp")
    def test_tar_extraction_fails(self, mock_mkdtemp, mock_rmtree, mock_run):
        """Should return False if tar extraction fails."""
        from pathlib import Path
        import tempfile

        rm = make_manager()

        # Create a real temp directory
        real_temp_dir = Path(tempfile.mkdtemp(prefix="test-tar-extract-fail-"))
        mock_mkdtemp.return_value = str(real_temp_dir)

        try:
            # Create directory structure with tar file
            volumes_dir = real_temp_dir / "volumes" / "myunit"
            volumes_dir.mkdir(parents=True, exist_ok=True)

            tar_file = volumes_dir / "myvolume"
            tar_file.write_bytes(b"fake tar content")

            # Mock run_command responses
            mock_run.side_effect = [
                CompletedProcess([], 0, stdout="", stderr=""),  # docker ps -q
                CompletedProcess([], 0, stdout="", stderr=""),  # safety backup
                CompletedProcess([], 0, stdout="", stderr=""),  # kopia restore
                CompletedProcess([], 0, stdout="tar archive", stderr=""),  # file type check
                CompletedProcess(
                    [], 1, stdout="", stderr="tar: Error extracting"
                ),  # docker run FAILS
            ]

            result = rm._execute_volume_restore_tar("myvolume", "myunit", "snap123", "/tmp/config")

            assert result is False

        finally:
            # Cleanup
            if real_temp_dir.exists():
                import shutil

                shutil.rmtree(real_temp_dir)

    @patch("kopi_docka.cores.restore_manager.run_command")
    @patch("kopi_docka.cores.restore_manager.shutil.rmtree")
    @patch("kopi_docka.cores.restore_manager.tempfile.mkdtemp")
    def test_stops_and_restarts_containers(self, mock_mkdtemp, mock_rmtree, mock_run):
        """Should stop containers before restore and restart after."""
        from pathlib import Path
        import tempfile

        rm = make_manager()

        # Create a real temp directory
        real_temp_dir = Path(tempfile.mkdtemp(prefix="test-tar-containers-"))
        mock_mkdtemp.return_value = str(real_temp_dir)

        try:
            # Create directory structure with tar file
            volumes_dir = real_temp_dir / "volumes" / "myunit"
            volumes_dir.mkdir(parents=True, exist_ok=True)

            tar_file = volumes_dir / "myvolume"
            tar_file.write_bytes(b"fake tar content")

            # Mock run_command responses
            mock_run.side_effect = [
                CompletedProcess(
                    [], 0, stdout="c1\nc2", stderr=""
                ),  # docker ps -q (finds 2 containers)
                CompletedProcess([], 0, stdout="", stderr=""),  # docker stop
                CompletedProcess([], 0, stdout="", stderr=""),  # safety backup
                CompletedProcess([], 0, stdout="", stderr=""),  # kopia restore
                CompletedProcess([], 0, stdout="tar archive", stderr=""),  # file type check
                CompletedProcess([], 0, stdout="", stderr=""),  # docker run (extract)
                CompletedProcess([], 0, stdout="c1\nc2", stderr=""),  # docker ps -q (restart)
                CompletedProcess([], 0, stdout="", stderr=""),  # docker start
            ]

            result = rm._execute_volume_restore_tar("myvolume", "myunit", "snap123", "/tmp/config")

            assert result is True

            # Verify docker stop was called
            stop_calls = [c for c in mock_run.call_args_list if "stop" in str(c[0][0])]
            assert len(stop_calls) > 0

            # Verify docker start was called
            start_calls = [c for c in mock_run.call_args_list if "start" in str(c[0][0])]
            assert len(start_calls) > 0

        finally:
            # Cleanup
            if real_temp_dir.exists():
                import shutil

                shutil.rmtree(real_temp_dir)

    @patch("kopi_docka.cores.restore_manager.run_command")
    @patch("kopi_docka.cores.restore_manager.shutil.rmtree")
    @patch("kopi_docka.cores.restore_manager.tempfile.mkdtemp")
    def test_creates_safety_backup(self, mock_mkdtemp, mock_rmtree, mock_run):
        """Should create safety backup before restore."""
        from pathlib import Path
        import tempfile

        rm = make_manager()

        # Create a real temp directory
        real_temp_dir = Path(tempfile.mkdtemp(prefix="test-tar-safety-"))
        mock_mkdtemp.return_value = str(real_temp_dir)

        try:
            # Create directory structure with tar file
            volumes_dir = real_temp_dir / "volumes" / "myunit"
            volumes_dir.mkdir(parents=True, exist_ok=True)

            tar_file = volumes_dir / "myvolume"
            tar_file.write_bytes(b"fake tar content")

            # Mock run_command responses
            mock_run.side_effect = [
                CompletedProcess([], 0, stdout="", stderr=""),  # docker ps -q
                CompletedProcess([], 0, stdout="", stderr=""),  # safety backup (tar -czf)
                CompletedProcess([], 0, stdout="", stderr=""),  # kopia restore
                CompletedProcess([], 0, stdout="tar archive", stderr=""),  # file type check
                CompletedProcess([], 0, stdout="", stderr=""),  # docker run (extract)
                CompletedProcess([], 0, stdout="", stderr=""),  # docker ps -q (restart)
            ]

            result = rm._execute_volume_restore_tar("myvolume", "myunit", "snap123", "/tmp/config")

            # Verify safety backup command was called
            backup_calls = [c for c in mock_run.call_args_list if "tar -czf" in str(c)]
            assert len(backup_calls) > 0

        finally:
            # Cleanup
            if real_temp_dir.exists():
                import shutil

                shutil.rmtree(real_temp_dir)

# =============================================================================
# Backup Scope Detection Tests
# =============================================================================


@pytest.mark.unit
class TestBackupScopeDetection:
    """Tests for backup scope detection and warnings in RestoreManager."""

    def test_get_backup_scope_minimal_from_volume_snapshot(self):
        """Should detect minimal scope from volume snapshot tags."""
        rm = make_manager()

        rp = RestorePoint(
            unit_name="mystack",
            timestamp=datetime.now(timezone.utc),
            backup_id="backup-123",
            volume_snapshots=[
                {"tags": {"backup_scope": "minimal", "type": "volume"}}
            ],
        )

        scope = rm._get_backup_scope(rp)
        assert scope == "minimal"

    def test_get_backup_scope_standard_from_recipe_snapshot(self):
        """Should detect standard scope from recipe snapshot tags."""
        rm = make_manager()

        rp = RestorePoint(
            unit_name="mystack",
            timestamp=datetime.now(timezone.utc),
            backup_id="backup-456",
            recipe_snapshots=[
                {"tags": {"backup_scope": "standard", "type": "recipe"}}
            ],
        )

        scope = rm._get_backup_scope(rp)
        assert scope == "standard"

    def test_get_backup_scope_full_from_docker_config_snapshot(self):
        """Should detect full scope from docker_config snapshot tags."""
        rm = make_manager()

        rp = RestorePoint(
            unit_name="mystack",
            timestamp=datetime.now(timezone.utc),
            backup_id="backup-789",
            docker_config_snapshots=[
                {"tags": {"backup_scope": "full", "type": "docker_config"}}
            ],
        )

        scope = rm._get_backup_scope(rp)
        assert scope == "full"

    def test_get_backup_scope_defaults_to_standard_for_legacy_snapshots(self):
        """Should default to 'standard' for snapshots without backup_scope tag."""
        rm = make_manager()

        rp = RestorePoint(
            unit_name="mystack",
            timestamp=datetime.now(timezone.utc),
            backup_id="backup-old",
            volume_snapshots=[
                {"tags": {"type": "volume"}}  # No backup_scope tag
            ],
        )

        scope = rm._get_backup_scope(rp)
        assert scope == "standard"

    def test_get_backup_scope_defaults_to_standard_for_empty_restore_point(self):
        """Should default to 'standard' for empty restore points."""
        rm = make_manager()

        rp = RestorePoint(
            unit_name="mystack",
            timestamp=datetime.now(timezone.utc),
            backup_id="backup-empty",
        )

        scope = rm._get_backup_scope(rp)
        assert scope == "standard"

    def test_get_backup_scope_reads_from_first_snapshot(self):
        """Should read scope from first available snapshot."""
        rm = make_manager()

        rp = RestorePoint(
            unit_name="mystack",
            timestamp=datetime.now(timezone.utc),
            backup_id="backup-multi",
            volume_snapshots=[
                {"tags": {"backup_scope": "full", "type": "volume"}},
                {"tags": {"backup_scope": "full", "type": "volume"}},
            ],
            recipe_snapshots=[
                {"tags": {"backup_scope": "full", "type": "recipe"}},
            ],
        )

        scope = rm._get_backup_scope(rp)
        assert scope == "full"

    def test_show_scope_warnings_minimal_displays_message(self, capsys):
        """Should display warning for minimal scope backups."""
        rm = make_manager()

        rp = RestorePoint(
            unit_name="mystack",
            timestamp=datetime.now(timezone.utc),
            backup_id="backup-123",
        )

        rm._show_scope_warnings("minimal", rp)

        # Check captured output contains minimal warning
        captured = capsys.readouterr()
        assert "MINIMAL" in captured.out or "minimal" in captured.out.lower()
        assert "Containers must be recreated manually" in captured.out

    
    def test_show_scope_warnings_docker_config_displays_info(self, capsys):
        """Should display info message when docker_config snapshots are present."""
        rm = make_manager()

        rp = RestorePoint(
            unit_name="mystack",
            timestamp=datetime.now(timezone.utc),
            backup_id="backup-456",
            docker_config_snapshots=[
                {"tags": {"backup_scope": "full", "type": "docker_config"}}
            ],
        )

        rm._show_scope_warnings("full", rp)

        # Check captured output contains docker config info
        captured = capsys.readouterr()
        assert "docker" in captured.out.lower() or "daemon" in captured.out.lower()

    
    def test_show_scope_warnings_standard_no_warning(self, capsys):
        """Should not display warning for standard scope."""
        rm = make_manager()

        rp = RestorePoint(
            unit_name="mystack",
            timestamp=datetime.now(timezone.utc),
            backup_id="backup-789",
        )

        rm._show_scope_warnings("standard", rp)

        # For standard scope without docker_config, no warnings
        captured = capsys.readouterr()
        assert "MINIMAL" not in captured.out
        assert "docker" not in captured.out.lower()

    
    def test_docker_config_snapshots_grouped_correctly(self):
        """Should group docker_config snapshots in restore points."""
        rm = make_manager()
        rm.repo.list_snapshots.return_value = [
            {
                "tags": {
                    "unit": "mystack",
                    "backup_id": "backup-123",
                    "type": "docker_config",
                    "backup_scope": "full",
                    "timestamp": "2025-12-28T10:00:00Z",
                }
            },
            {
                "tags": {
                    "unit": "mystack",
                    "backup_id": "backup-123",
                    "type": "volume",
                    "backup_scope": "full",
                    "timestamp": "2025-12-28T10:00:00Z",
                }
            },
        ]

        restore_points = rm._find_restore_points()

        assert len(restore_points) == 1
        rp = restore_points[0]
        assert len(rp.docker_config_snapshots) == 1
        assert len(rp.volume_snapshots) == 1
        assert rp.docker_config_snapshots[0]["tags"]["type"] == "docker_config"
