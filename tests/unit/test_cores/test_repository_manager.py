"""
Unit tests for KopiaRepository class.

Tests the business logic of Kopia repository interactions,
with subprocess calls mocked.
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch, Mock, MagicMock

from kopi_docka.cores.repository_manager import KopiaRepository
from kopi_docka.types import MachineInfo


def make_mock_config(kopia_params: str = "filesystem --path /backup/repo") -> Mock:
    """Create a mock Config object for testing."""
    config = Mock()
    config.get.return_value = kopia_params
    config.kopia_profile = "kopi-docka"
    config.get_password.return_value = "test-password"
    config.kopia_cache_directory = "/tmp/kopia-cache"
    config.kopia_cache_size_mb = 500
    return config


def make_repository(config: Mock = None) -> KopiaRepository:
    """Create a KopiaRepository instance without running __init__ validation."""
    repo = KopiaRepository.__new__(KopiaRepository)
    repo.config = config or make_mock_config()
    repo.kopia_params = repo.config.get("kopia", "kopia_params", fallback="")
    repo.profile_name = repo.config.kopia_profile
    return repo


# =============================================================================
# Config File Path Tests
# =============================================================================


@pytest.mark.unit
class TestGetConfigFile:
    """Tests for _get_config_file method."""

    def test_returns_profile_specific_path(self):
        """Config file path should include profile name."""
        repo = make_repository()
        repo.profile_name = "myprofile"

        config_file = repo._get_config_file()

        assert "repository-myprofile.config" in config_file
        assert ".config/kopia" in config_file

    def test_default_profile_name(self):
        """Default profile should be kopi-docka."""
        repo = make_repository()

        config_file = repo._get_config_file()

        assert "repository-kopi-docka.config" in config_file


# =============================================================================
# Environment Tests
# =============================================================================


@pytest.mark.unit
class TestGetEnv:
    """Tests for _get_env method."""

    def test_includes_password(self):
        """Environment should include KOPIA_PASSWORD."""
        config = make_mock_config()
        config.get_password.return_value = "secret123"
        repo = make_repository(config)

        env = repo._get_env()

        assert env["KOPIA_PASSWORD"] == "secret123"

    def test_includes_cache_directory(self):
        """Environment should include KOPIA_CACHE_DIRECTORY."""
        config = make_mock_config()
        config.kopia_cache_directory = "/custom/cache"
        repo = make_repository(config)

        env = repo._get_env()

        assert env["KOPIA_CACHE_DIRECTORY"] == "/custom/cache"

    def test_includes_config_path(self):
        """Environment should include KOPIA_CONFIG_PATH."""
        repo = make_repository()

        env = repo._get_env()

        assert "KOPIA_CONFIG_PATH" in env
        assert "repository-kopi-docka.config" in env["KOPIA_CONFIG_PATH"]


# =============================================================================
# Connection Status Tests
# =============================================================================


@pytest.mark.unit
class TestIsConnected:
    """Tests for is_connected method."""

    @patch("shutil.which")
    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_returns_true_when_connected(self, mock_run_command, mock_which):
        """Should return True when kopia status succeeds."""
        mock_which.return_value = "/usr/bin/kopia"
        mock_run_command.return_value = CompletedProcess([], 0, stdout="{}", stderr="")
        repo = make_repository()

        result = repo.is_connected()

        assert result is True

    @patch("shutil.which")
    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_returns_false_when_not_connected(self, mock_run_command, mock_which):
        """Should return False when kopia status fails."""
        mock_which.return_value = "/usr/bin/kopia"
        mock_run_command.return_value = CompletedProcess([], 1, stdout="", stderr="not connected")
        repo = make_repository()

        result = repo.is_connected()

        assert result is False

    @patch("shutil.which")
    def test_returns_false_when_kopia_not_installed(self, mock_which):
        """Should return False when kopia binary not found."""
        mock_which.return_value = None
        repo = make_repository()

        result = repo.is_connected()

        assert result is False


# =============================================================================
# Status Tests
# =============================================================================


@pytest.mark.unit
class TestStatus:
    """Tests for status method."""

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_returns_parsed_json(self, mock_run_command):
        """Should parse JSON output from kopia status."""
        status_json = {
            "configFile": "/path/to/config",
            "formatVersion": "2",
            "storage": {"type": "filesystem"},
        }
        mock_run_command.return_value = CompletedProcess([], 0, stdout=json.dumps(status_json), stderr="")
        repo = make_repository()

        result = repo.status(json_output=True)

        assert result == status_json

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_returns_raw_text_when_requested(self, mock_run_command):
        """Should return raw text when json_output=False."""
        mock_run_command.return_value = CompletedProcess(
            [], 0, stdout="Status: connected\nPath: /backup", stderr=""
        )
        repo = make_repository()

        result = repo.status(json_output=False)

        assert "Status: connected" in result

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_raises_on_failure(self, mock_run_command):
        """Should raise RuntimeError when status fails."""
        mock_run_command.return_value = CompletedProcess(
            [], 1, stdout="", stderr="repository not connected"
        )
        repo = make_repository()

        with pytest.raises(RuntimeError, match="repository status.*failed"):
            repo.status()


# =============================================================================
# Create Snapshot Tests
# =============================================================================


@pytest.mark.unit
class TestCreateSnapshot:
    """Tests for create_snapshot method."""

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_returns_snapshot_id(self, mock_run_command):
        """Should return snapshot ID from Kopia output."""
        mock_run_command.return_value = CompletedProcess(
            [], 0, stdout='{"snapshotID": "k1234567890abcdef"}', stderr=""
        )
        repo = make_repository()

        snapshot_id = repo.create_snapshot("/path/to/backup")

        assert snapshot_id == "k1234567890abcdef"

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_handles_id_field(self, mock_run_command):
        """Should also handle 'id' field (older Kopia versions)."""
        mock_run_command.return_value = CompletedProcess(
            [], 0, stdout='{"id": "k9876543210fedcba"}', stderr=""
        )
        repo = make_repository()

        snapshot_id = repo.create_snapshot("/path/to/backup")

        assert snapshot_id == "k9876543210fedcba"

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_includes_tags_in_command(self, mock_run_command):
        """Should pass tags to Kopia command."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout='{"snapshotID": "k123"}', stderr="")
        repo = make_repository()

        repo.create_snapshot("/path", tags={"unit": "mystack", "type": "volume"})

        call_args = mock_run_command.call_args[0][0]
        assert "--tags" in call_args
        assert "unit:mystack" in call_args
        assert "type:volume" in call_args

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_includes_exclude_patterns(self, mock_run_command):
        """Should pass exclude patterns to Kopia command."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout='{"snapshotID": "k123"}', stderr="")
        repo = make_repository()

        repo.create_snapshot("/path", exclude_patterns=["*.log", "cache/*"])

        call_args = mock_run_command.call_args[0][0]
        assert "--ignore" in call_args
        assert "*.log" in call_args
        assert "cache/*" in call_args

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_raises_on_empty_path(self, mock_run_command):
        """Should raise ValueError for empty path."""
        repo = make_repository()

        with pytest.raises(ValueError, match="path cannot be empty"):
            repo.create_snapshot("")

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_raises_on_missing_snapshot_id(self, mock_run_command):
        """Should raise RuntimeError if snapshot ID not in output."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout='{"status": "ok"}', stderr="")
        repo = make_repository()

        with pytest.raises(RuntimeError, match="Could not determine snapshot ID"):
            repo.create_snapshot("/path")

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_raises_on_command_failure(self, mock_run_command):
        """Should raise RuntimeError when Kopia command fails."""
        from kopi_docka.helpers.ui_utils import SubprocessError
        mock_run_command.side_effect = SubprocessError(["kopia", "snapshot", "create"], 1, "permission denied")
        repo = make_repository()

        with pytest.raises(RuntimeError, match="permission denied"):
            repo.create_snapshot("/path")


# =============================================================================
# List Snapshots Tests
# =============================================================================


@pytest.mark.unit
class TestListSnapshots:
    """Tests for list_snapshots method."""

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_parses_snapshot_list(self, mock_run_command):
        """Should parse JSON array of snapshots."""
        snapshots_json = [
            {
                "id": "snap1",
                "source": {"path": "/backup/vol1"},
                "startTime": "2025-01-15T10:00:00Z",
                "tags": {"tag:unit": "mystack", "tag:type": "volume"},
                "stats": {"totalSize": 1024},
            },
            {
                "id": "snap2",
                "source": {"path": "/backup/vol2"},
                "startTime": "2025-01-15T11:00:00Z",
                "tags": {"tag:unit": "mystack", "tag:type": "recipe"},
                "stats": {"totalSize": 2048},
            },
        ]
        mock_run_command.return_value = CompletedProcess(
            [], 0, stdout=json.dumps(snapshots_json), stderr=""
        )
        repo = make_repository()

        result = repo.list_snapshots()

        assert len(result) == 2
        assert result[0]["id"] == "snap1"
        assert result[0]["path"] == "/backup/vol1"
        assert result[0]["size"] == 1024
        # Tags should have "tag:" prefix removed
        assert result[0]["tags"]["unit"] == "mystack"
        assert result[0]["tags"]["type"] == "volume"

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_removes_tag_prefix(self, mock_run_command):
        """Should remove 'tag:' prefix from tag keys."""
        snapshots_json = [
            {
                "id": "snap1",
                "source": {},
                "tags": {"tag:unit": "app", "tag:backup_id": "uuid123"},
                "stats": {},
            }
        ]
        mock_run_command.return_value = CompletedProcess(
            [], 0, stdout=json.dumps(snapshots_json), stderr=""
        )
        repo = make_repository()

        result = repo.list_snapshots()

        assert result[0]["tags"] == {"unit": "app", "backup_id": "uuid123"}

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_filters_by_tag(self, mock_run_command):
        """Should filter snapshots by tag when tag_filter provided."""
        snapshots_json = [
            {
                "id": "snap1",
                "source": {},
                "tags": {"tag:unit": "app1"},
                "stats": {},
            },
            {
                "id": "snap2",
                "source": {},
                "tags": {"tag:unit": "app2"},
                "stats": {},
            },
        ]
        mock_run_command.return_value = CompletedProcess(
            [], 0, stdout=json.dumps(snapshots_json), stderr=""
        )
        repo = make_repository()

        result = repo.list_snapshots(tag_filter={"unit": "app1"})

        assert len(result) == 1
        assert result[0]["id"] == "snap1"

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_returns_empty_list_on_no_snapshots(self, mock_run_command):
        """Should return empty list when no snapshots exist."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout="[]", stderr="")
        repo = make_repository()

        result = repo.list_snapshots()

        assert result == []

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_handles_invalid_json(self, mock_run_command):
        """Should return empty list on invalid JSON."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout="not valid json", stderr="")
        repo = make_repository()

        result = repo.list_snapshots()

        assert result == []


# =============================================================================
# List All Snapshots Tests
# =============================================================================


@pytest.mark.unit
class TestListAllSnapshots:
    """Tests for list_all_snapshots method."""

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_includes_host_in_results(self, mock_run_command):
        """Should include hostname from source."""
        snapshots_json = [
            {
                "id": "snap1",
                "source": {"path": "/backup", "host": "server1", "userName": "root"},
                "tags": {},
                "stats": {},
            },
            {
                "id": "snap2",
                "source": {"path": "/backup", "host": "server2", "userName": "root"},
                "tags": {},
                "stats": {},
            },
        ]
        mock_run_command.return_value = CompletedProcess(
            [], 0, stdout=json.dumps(snapshots_json), stderr=""
        )
        repo = make_repository()

        result = repo.list_all_snapshots()

        assert len(result) == 2
        assert result[0]["host"] == "server1"
        assert result[1]["host"] == "server2"

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_uses_all_flag(self, mock_run_command):
        """Should use --all flag to get all snapshots."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout="[]", stderr="")
        repo = make_repository()

        repo.list_all_snapshots()

        call_args = mock_run_command.call_args[0][0]
        assert "--all" in call_args


# =============================================================================
# Discover Machines Tests
# =============================================================================


@pytest.mark.unit
class TestDiscoverMachines:
    """Tests for discover_machines method."""

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_aggregates_by_hostname(self, mock_run_command):
        """Should aggregate snapshots by hostname."""
        snapshots_json = [
            {
                "id": "snap1",
                "source": {"path": "/backup", "host": "server1"},
                "startTime": "2025-01-15T10:00:00Z",
                "tags": {"tag:unit": "app1"},
                "stats": {"totalSize": 1000},
            },
            {
                "id": "snap2",
                "source": {"path": "/backup", "host": "server1"},
                "startTime": "2025-01-15T11:00:00Z",
                "tags": {"tag:unit": "app2"},
                "stats": {"totalSize": 2000},
            },
            {
                "id": "snap3",
                "source": {"path": "/backup", "host": "server2"},
                "startTime": "2025-01-14T10:00:00Z",
                "tags": {"tag:unit": "db"},
                "stats": {"totalSize": 5000},
            },
        ]
        mock_run_command.return_value = CompletedProcess(
            [], 0, stdout=json.dumps(snapshots_json), stderr=""
        )
        repo = make_repository()

        machines = repo.discover_machines()

        assert len(machines) == 2
        # Sorted by last backup (newest first)
        assert machines[0].hostname == "server1"
        assert machines[0].backup_count == 2
        assert set(machines[0].units) == {"app1", "app2"}
        assert machines[0].total_size == 3000

        assert machines[1].hostname == "server2"
        assert machines[1].backup_count == 1
        assert machines[1].units == ["db"]

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_parses_timestamps_correctly(self, mock_run_command):
        """Should parse ISO timestamps with timezone."""
        snapshots_json = [
            {
                "id": "snap1",
                "source": {"host": "server1"},
                "startTime": "2025-01-15T10:30:00Z",
                "tags": {},
                "stats": {},
            }
        ]
        mock_run_command.return_value = CompletedProcess(
            [], 0, stdout=json.dumps(snapshots_json), stderr=""
        )
        repo = make_repository()

        machines = repo.discover_machines()

        assert machines[0].last_backup.year == 2025
        assert machines[0].last_backup.month == 1
        assert machines[0].last_backup.day == 15
        assert machines[0].last_backup.hour == 10
        assert machines[0].last_backup.minute == 30

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_returns_empty_list_on_no_snapshots(self, mock_run_command):
        """Should return empty list when no snapshots."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout="[]", stderr="")
        repo = make_repository()

        machines = repo.discover_machines()

        assert machines == []


# =============================================================================
# Verify Password Tests
# =============================================================================


@pytest.mark.unit
class TestVerifyPassword:
    """Tests for verify_password method."""

    @patch("subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        """Should return True when password is correct."""
        mock_run.return_value = CompletedProcess([], 0, stdout="{}", stderr="")
        repo = make_repository()

        result = repo.verify_password("correct-password")

        assert result is True
        # Verify password was passed in environment
        call_env = mock_run.call_args[1]["env"]
        assert call_env["KOPIA_PASSWORD"] == "correct-password"

    @patch("subprocess.run")
    def test_returns_false_on_failure(self, mock_run):
        """Should return False when password is wrong."""
        mock_run.return_value = CompletedProcess([], 1, stdout="", stderr="invalid password")
        repo = make_repository()

        result = repo.verify_password("wrong-password")

        assert result is False


# =============================================================================
# Restore Snapshot Tests
# =============================================================================


@pytest.mark.unit
class TestRestoreSnapshot:
    """Tests for restore_snapshot method."""

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_calls_kopia_restore(self, mock_run_command):
        """Should call kopia snapshot restore with correct args."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout="", stderr="")
        repo = make_repository()

        repo.restore_snapshot("k123456", "/restore/target")

        call_args = mock_run_command.call_args[0][0]
        assert "kopia" in call_args
        assert "snapshot" in call_args
        assert "restore" in call_args
        assert "k123456" in call_args
        assert "/restore/target" in call_args


# =============================================================================
# Verify Snapshot Tests
# =============================================================================


@pytest.mark.unit
class TestVerifySnapshot:
    """Tests for verify_snapshot method."""

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_returns_true_on_success(self, mock_run_command):
        """Should return True when verification succeeds."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout="", stderr="")
        repo = make_repository()

        result = repo.verify_snapshot("k123456")

        assert result is True

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_returns_false_on_failure(self, mock_run_command):
        """Should return False when verification fails."""
        mock_run_command.return_value = CompletedProcess([], 1, stdout="", stderr="verification failed")
        repo = make_repository()

        result = repo.verify_snapshot("k123456")

        assert result is False

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_includes_verify_percent(self, mock_run_command):
        """Should pass verify-files-percent parameter."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout="", stderr="")
        repo = make_repository()

        repo.verify_snapshot("k123456", verify_percent=25)

        call_args = mock_run_command.call_args[0][0]
        assert "--verify-files-percent=25" in call_args


# =============================================================================
# Maintenance Tests
# =============================================================================


@pytest.mark.unit
class TestMaintenanceRun:
    """Tests for maintenance_run method."""

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_runs_full_maintenance(self, mock_run_command):
        """Should run maintenance with --full by default."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout="", stderr="")
        repo = make_repository()

        repo.maintenance_run(full=True)

        call_args = mock_run_command.call_args[0][0]
        assert "maintenance" in call_args
        assert "--full" in call_args

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_runs_quick_maintenance(self, mock_run_command):
        """Should run maintenance without --full when full=False."""
        mock_run_command.return_value = CompletedProcess([], 0, stdout="", stderr="")
        repo = make_repository()

        repo.maintenance_run(full=False)

        call_args = mock_run_command.call_args[0][0]
        assert "maintenance" in call_args
        assert "--full" not in call_args


# =============================================================================
# JSON Parsing Helper Tests
# =============================================================================


@pytest.mark.unit
class TestParseSingleJsonLine:
    """Tests for _parse_single_json_line static method."""

    def test_parses_simple_json(self):
        """Should parse simple JSON object."""
        result = KopiaRepository._parse_single_json_line('{"key": "value"}')

        assert result == {"key": "value"}

    def test_parses_first_line_of_ndjson(self):
        """Should parse first line of NDJSON output."""
        result = KopiaRepository._parse_single_json_line('{"id": "snap1"}\n{"id": "snap2"}')

        assert result == {"id": "snap1"}

    def test_returns_empty_dict_for_empty_string(self):
        """Should return empty dict for empty input."""
        result = KopiaRepository._parse_single_json_line("")

        assert result == {}

    def test_returns_empty_dict_for_none(self):
        """Should return empty dict for None input."""
        result = KopiaRepository._parse_single_json_line(None)

        assert result == {}

    def test_returns_empty_dict_for_invalid_json(self):
        """Should return empty dict for invalid JSON."""
        result = KopiaRepository._parse_single_json_line("not json at all")

        assert result == {}

    def test_handles_whitespace(self):
        """Should handle leading/trailing whitespace."""
        result = KopiaRepository._parse_single_json_line('  {"key": "value"}  ')

        assert result == {"key": "value"}


# =============================================================================
# List Backup Units Tests
# =============================================================================


@pytest.mark.unit
class TestListBackupUnits:
    """Tests for list_backup_units method."""

    @patch("kopi_docka.cores.repository_manager.run_command")
    def test_extracts_units_from_recipe_snapshots(self, mock_run_command):
        """Should extract unique units from recipe snapshots."""
        snapshots_json = [
            {
                "id": "snap1",
                "source": {},
                "startTime": "2025-01-15T10:00:00Z",
                "tags": {"tag:type": "recipe", "tag:unit": "app1"},
                "stats": {},
            },
            {
                "id": "snap2",
                "source": {},
                "startTime": "2025-01-15T11:00:00Z",
                "tags": {"tag:type": "recipe", "tag:unit": "app1"},  # Same unit, newer
                "stats": {},
            },
            {
                "id": "snap3",
                "source": {},
                "startTime": "2025-01-15T09:00:00Z",
                "tags": {"tag:type": "volume", "tag:unit": "app1"},  # Not recipe
                "stats": {},
            },
            {
                "id": "snap4",
                "source": {},
                "startTime": "2025-01-15T10:00:00Z",
                "tags": {"tag:type": "recipe", "tag:unit": "app2"},
                "stats": {},
            },
        ]
        mock_run_command.return_value = CompletedProcess(
            [], 0, stdout=json.dumps(snapshots_json), stderr=""
        )
        repo = make_repository()

        units = repo.list_backup_units()

        assert len(units) == 2
        unit_names = {u["name"] for u in units}
        assert unit_names == {"app1", "app2"}

        # app1 should have the newer snapshot
        app1 = next(u for u in units if u["name"] == "app1")
        assert app1["snapshot_id"] == "snap2"
