"""
Unit tests for RestoreManager class.

Tests the restore orchestration business logic with mocked external dependencies.
"""

import subprocess
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

import kopi_docka.cores.restore_manager as restore_manager
from kopi_docka.types import RestorePoint


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
