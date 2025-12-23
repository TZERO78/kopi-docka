"""Unit tests for ServiceHelper class."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, mock_open

import pytest

from kopi_docka.cores.service_helper import (
    ServiceHelper,
    ServiceStatus,
    TimerStatus,
    BackupInfo,
)


@pytest.fixture
def helper():
    """Create ServiceHelper instance for testing."""
    return ServiceHelper()


class TestServiceHelper:
    """Test ServiceHelper basic functionality."""

    def test_init(self, helper):
        """Test ServiceHelper initialization."""
        assert helper.service_name == "kopi-docka.service"
        assert helper.timer_name == "kopi-docka.timer"
        assert helper.backup_service_name == "kopi-docka-backup.service"
        assert helper.timer_file == Path("/etc/systemd/system/kopi-docka.timer")


class TestValidation:
    """Test validation methods."""

    def test_validate_time_format_valid(self, helper):
        """Test valid time format validation."""
        assert helper.validate_time_format("00:00") is True
        assert helper.validate_time_format("12:30") is True
        assert helper.validate_time_format("23:59") is True
        assert helper.validate_time_format("9:15") is True

    def test_validate_time_format_invalid(self, helper):
        """Test invalid time format validation."""
        assert helper.validate_time_format("24:00") is False
        assert helper.validate_time_format("12:60") is False
        assert helper.validate_time_format("1260") is False
        assert helper.validate_time_format("12-30") is False
        assert helper.validate_time_format("") is False
        assert helper.validate_time_format("abc") is False

    @patch("kopi_docka.cores.service_helper.run_command")
    def test_validate_oncalendar_valid(self, mock_run, helper):
        """Test OnCalendar validation with valid syntax."""
        mock_run.return_value = Mock(returncode=0)

        result = helper.validate_oncalendar("*-*-* 02:00:00")

        assert result is True
        mock_run.assert_called_once_with(
            ["systemd-analyze", "calendar", "*-*-* 02:00:00"],
            "Validating calendar syntax",
            timeout=5,
            check=False,
        )

    @patch("kopi_docka.cores.service_helper.run_command")
    def test_validate_oncalendar_invalid(self, mock_run, helper):
        """Test OnCalendar validation with invalid syntax."""
        mock_run.return_value = Mock(returncode=1)

        result = helper.validate_oncalendar("invalid syntax")

        assert result is False

    @patch("kopi_docka.cores.service_helper.run_command")
    def test_validate_oncalendar_timeout(self, mock_run, helper):
        """Test OnCalendar validation with timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 5)

        result = helper.validate_oncalendar("*-*-* 02:00:00")

        assert result is False

    @patch("kopi_docka.cores.service_helper.run_command")
    def test_validate_oncalendar_not_available(self, mock_run, helper):
        """Test OnCalendar validation when systemd-analyze is not available."""
        mock_run.side_effect = FileNotFoundError()

        # Should return True when systemd-analyze is not available
        result = helper.validate_oncalendar("*-*-* 02:00:00")

        assert result is True


class TestStatusMethods:
    """Test status retrieval methods."""

    @patch("subprocess.run")
    def test_get_service_status_active_enabled(self, mock_run, helper):
        """Test getting service status when active and enabled."""
        mock_run.side_effect = [
            Mock(stdout="active\n"),  # is-active
            Mock(stdout="enabled\n"),  # is-enabled
            Mock(stdout="inactive\n"),  # is-failed
        ]

        status = helper.get_service_status()

        assert status.active is True
        assert status.enabled is True
        assert status.failed is False

    @patch("subprocess.run")
    def test_get_service_status_inactive_disabled(self, mock_run, helper):
        """Test getting service status when inactive and disabled."""
        mock_run.side_effect = [
            Mock(stdout="inactive\n"),  # is-active
            Mock(stdout="disabled\n"),  # is-enabled
            Mock(stdout="inactive\n"),  # is-failed
        ]

        status = helper.get_service_status()

        assert status.active is False
        assert status.enabled is False
        assert status.failed is False

    @patch("subprocess.run")
    def test_get_service_status_failed(self, mock_run, helper):
        """Test getting service status when failed."""
        mock_run.side_effect = [
            Mock(stdout="inactive\n"),  # is-active
            Mock(stdout="enabled\n"),  # is-enabled
            Mock(stdout="failed\n"),  # is-failed
        ]

        status = helper.get_service_status()

        assert status.active is False
        assert status.enabled is True
        assert status.failed is True

    @patch("subprocess.run")
    def test_get_service_status_exception(self, mock_run, helper):
        """Test getting service status when exception occurs."""
        mock_run.side_effect = Exception("Test error")

        status = helper.get_service_status()

        # Should return default values on error
        assert status.active is False
        assert status.enabled is False
        assert status.failed is False

    @patch("subprocess.run")
    def test_get_timer_status(self, mock_run, helper):
        """Test getting timer status."""
        mock_run.side_effect = [
            Mock(stdout="active\n"),  # is-active
            Mock(stdout="enabled\n"),  # is-enabled
            Mock(
                stdout="NEXT                        LEFT          LAST                        PASSED       UNIT                 ACTIVATES\n"
                "Sat 2025-12-21 02:00:00 UTC 5h 30min left n/a                         n/a          kopi-docka.timer     kopi-docka.service\n",
                returncode=0,
            ),  # list-timers
        ]

        status = helper.get_timer_status()

        assert status.active is True
        assert status.enabled is True
        # next_run and left parsing is tested separately


class TestLockStatus:
    """Test lock file status checking."""

    def test_get_lock_status_not_exists(self, helper):
        """Test lock status when file doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            status = helper.get_lock_status()

            assert status["exists"] is False
            assert status["pid"] is None
            assert status["process_running"] is False

    @patch("subprocess.run")
    def test_get_lock_status_exists_running(self, mock_run, helper):
        """Test lock status when file exists and process is running."""
        mock_run.return_value = Mock()  # kill -0 succeeds

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value="12345"):
                status = helper.get_lock_status()

                assert status["exists"] is True
                assert status["pid"] == 12345
                assert status["process_running"] is True

    @patch("subprocess.run")
    def test_get_lock_status_exists_not_running(self, mock_run, helper):
        """Test lock status when file exists but process is not running."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "kill")

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value="12345"):
                status = helper.get_lock_status()

                assert status["exists"] is True
                assert status["pid"] == 12345
                assert status["process_running"] is False


class TestControlMethods:
    """Test service control methods."""

    @patch("kopi_docka.cores.service_helper.run_command")
    def test_control_service_start(self, mock_run, helper):
        """Test starting service."""
        mock_run.return_value = Mock(returncode=0)

        result = helper.control_service("start", "service")

        assert result is True
        mock_run.assert_called_once_with(
            ["systemctl", "start", "kopi-docka.service"],
            "Running systemctl start",
            timeout=30,
            check=False,
        )

    @patch("kopi_docka.cores.service_helper.run_command")
    def test_control_service_stop_timer(self, mock_run, helper):
        """Test stopping timer."""
        mock_run.return_value = Mock(returncode=0)

        result = helper.control_service("stop", "timer")

        assert result is True
        mock_run.assert_called_once_with(
            ["systemctl", "stop", "kopi-docka.timer"],
            "Running systemctl stop",
            timeout=30,
            check=False,
        )

    @patch("kopi_docka.cores.service_helper.run_command")
    def test_control_service_invalid_action(self, mock_run, helper):
        """Test invalid action."""
        result = helper.control_service("invalid", "service")

        assert result is False
        mock_run.assert_not_called()

    @patch("kopi_docka.cores.service_helper.run_command")
    def test_control_service_failure(self, mock_run, helper):
        """Test service control failure."""
        mock_run.return_value = Mock(returncode=1, stderr="Error")

        result = helper.control_service("start", "service")

        assert result is False

    @patch("kopi_docka.cores.service_helper.run_command")
    def test_reload_daemon(self, mock_run, helper):
        """Test daemon reload."""
        mock_run.return_value = Mock(returncode=0)

        result = helper.reload_daemon()

        assert result is True
        mock_run.assert_called_once_with(
            ["systemctl", "daemon-reload"],
            "Reloading systemd daemon",
            timeout=30,
            check=False,
        )


class TestConfiguration:
    """Test configuration methods."""

    def test_get_current_schedule_success(self, helper):
        """Test getting current schedule from timer file."""
        timer_content = """[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=timer_content):
                schedule = helper.get_current_schedule()

                assert schedule == "*-*-* 02:00:00"

    def test_get_current_schedule_commented(self, helper):
        """Test getting schedule when OnCalendar is commented."""
        timer_content = """[Timer]
# OnCalendar=*-*-* 02:00:00
OnCalendar=*-*-* 03:00:00
"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=timer_content):
                schedule = helper.get_current_schedule()

                assert schedule == "*-*-* 03:00:00"

    def test_get_current_schedule_not_found(self, helper):
        """Test getting schedule when file doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            schedule = helper.get_current_schedule()

            assert schedule is None

    def test_units_exist_both_present(self, helper):
        """Test units_exist when both files are present."""
        with patch("pathlib.Path.exists", return_value=True):
            result = helper.units_exist()

            assert result is True

    def test_units_exist_missing(self, helper):
        """Test units_exist when files are missing."""
        with patch("pathlib.Path.exists", side_effect=[True, False]):
            result = helper.units_exist()

            assert result is False


class TestLogMethods:
    """Test log retrieval methods."""

    @patch("subprocess.run")
    def test_get_logs_last(self, mock_run, helper):
        """Test getting last N log lines."""
        mock_run.return_value = Mock(
            returncode=0, stdout="Log line 1\nLog line 2\nLog line 3"
        )

        logs = helper.get_logs(mode="last", lines=3)

        assert len(logs) == 3
        assert logs[0] == "Log line 1"
        mock_run.assert_called_once()
        assert "-n" in mock_run.call_args[0][0]
        assert "3" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_get_logs_errors(self, mock_run, helper):
        """Test getting error logs."""
        mock_run.return_value = Mock(returncode=0, stdout="Error log")

        logs = helper.get_logs(mode="errors")

        assert len(logs) == 1
        mock_run.assert_called_once()
        assert "-p" in mock_run.call_args[0][0]
        assert "err" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_get_logs_hour(self, mock_run, helper):
        """Test getting logs from last hour."""
        mock_run.return_value = Mock(returncode=0, stdout="Recent log")

        logs = helper.get_logs(mode="hour")

        assert len(logs) == 1
        mock_run.assert_called_once()
        assert "--since" in mock_run.call_args[0][0]
        assert "1 hour ago" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_get_logs_failure(self, mock_run, helper):
        """Test log retrieval failure."""
        mock_run.return_value = Mock(returncode=1, stderr="Error")

        logs = helper.get_logs(mode="last")

        assert len(logs) == 1
        assert "Failed to retrieve logs" in logs[0]


@pytest.mark.unit
class TestDataClasses:
    """Test dataclass structures."""

    def test_service_status(self):
        """Test ServiceStatus dataclass."""
        status = ServiceStatus(active=True, enabled=False, failed=False)
        assert status.active is True
        assert status.enabled is False
        assert status.failed is False

    def test_timer_status(self):
        """Test TimerStatus dataclass."""
        status = TimerStatus(
            active=True, enabled=True, next_run="2025-12-21 02:00:00", left="5h 30min"
        )
        assert status.active is True
        assert status.next_run == "2025-12-21 02:00:00"
        assert status.left == "5h 30min"

    def test_backup_info(self):
        """Test BackupInfo dataclass."""
        info = BackupInfo(timestamp="2025-12-21 02:00:00", status="success", duration="3m 42s")
        assert info.timestamp == "2025-12-21 02:00:00"
        assert info.status == "success"
        assert info.duration == "3m 42s"
