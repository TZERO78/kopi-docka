################################################################################
# KOPI-DOCKA
#
# @file:        service_helper.py
# @module:      kopi_docka.cores.service_helper
# @description: Helper class for systemctl and journalctl operations
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
ServiceHelper - Wrapper for systemctl and journalctl operations.

This module provides a high-level interface for managing kopi-docka systemd
services without requiring direct systemctl knowledge.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..helpers.logging import get_logger
from ..helpers.ui_utils import run_command, SubprocessError

LOGGER = get_logger("kopi_docka.service_helper")


@dataclass
class ServiceStatus:
    """Status information for a systemd service."""

    active: bool  # Service is currently running
    enabled: bool  # Service is enabled to start at boot
    failed: bool  # Service is in failed state


@dataclass
class TimerStatus:
    """Status information for a systemd timer."""

    active: bool  # Timer is currently active
    enabled: bool  # Timer is enabled
    next_run: Optional[str]  # Next scheduled run time
    left: Optional[str]  # Time remaining until next run


@dataclass
class BackupInfo:
    """Information about last backup run."""

    timestamp: Optional[str]  # When the backup ran
    status: str  # 'success', 'failed', or 'unknown'
    duration: Optional[str]  # How long it took


class ServiceHelper:
    """
    Helper class for managing kopi-docka systemd services.

    This class wraps systemctl and journalctl commands to provide
    a simple interface for service management.
    """

    def __init__(self):
        """Initialize ServiceHelper."""
        self.service_name = "kopi-docka.service"
        self.timer_name = "kopi-docka.timer"
        self.backup_service_name = "kopi-docka-backup.service"
        self.timer_file = Path("/etc/systemd/system") / self.timer_name

    # -------------------------------------------------------------------------
    # Status Methods
    # -------------------------------------------------------------------------

    def get_service_status(self) -> ServiceStatus:
        """
        Get status of kopi-docka.service.

        Returns:
            ServiceStatus object with active, enabled, and failed states
        """
        try:
            # Check if service is active (running)
            active_result = run_command(
                ["systemctl", "is-active", self.service_name],
                "Checking service status",
                timeout=10,
                check=False,
            )
            active = active_result.stdout.strip() == "active"

            # Check if service is enabled (starts at boot)
            enabled_result = run_command(
                ["systemctl", "is-enabled", self.service_name],
                "Checking service enabled",
                timeout=10,
                check=False,
            )
            enabled = enabled_result.stdout.strip() == "enabled"

            # Check if service is in failed state
            failed_result = run_command(
                ["systemctl", "is-failed", self.service_name],
                "Checking service failed",
                timeout=10,
                check=False,
            )
            failed = failed_result.stdout.strip() == "failed"

            return ServiceStatus(active=active, enabled=enabled, failed=failed)

        except Exception as e:
            LOGGER.error(f"Failed to get service status: {e}")
            return ServiceStatus(active=False, enabled=False, failed=False)

    def get_timer_status(self) -> TimerStatus:
        """
        Get status of kopi-docka.timer.

        Returns:
            TimerStatus object with active, enabled, next_run, and left fields
        """
        try:
            # Check if timer is active
            active_result = run_command(
                ["systemctl", "is-active", self.timer_name],
                "Checking timer status",
                timeout=10,
                check=False,
            )
            active = active_result.stdout.strip() == "active"

            # Check if timer is enabled
            enabled_result = run_command(
                ["systemctl", "is-enabled", self.timer_name],
                "Checking timer enabled",
                timeout=10,
                check=False,
            )
            enabled = enabled_result.stdout.strip() == "enabled"

            # Get next run time
            next_run, left = self._parse_timer_info()

            return TimerStatus(active=active, enabled=enabled, next_run=next_run, left=left)

        except Exception as e:
            LOGGER.error(f"Failed to get timer status: {e}")
            return TimerStatus(active=False, enabled=False, next_run=None, left=None)

    def _parse_timer_info(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse timer information from systemctl list-timers.

        Returns:
            Tuple of (next_run_time, time_left)
        """
        try:
            result = run_command(
                ["systemctl", "list-timers", self.timer_name, "--no-pager"],
                "Getting timer schedule",
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                return None, None

            # Parse output - looking for line with timer info
            for line in result.stdout.splitlines():
                if self.timer_name in line:
                    # Format: NEXT  LEFT  LAST  PASSED  UNIT  ACTIVATES
                    parts = line.split()
                    if len(parts) >= 2:
                        # NEXT is typically date + time (2-3 columns)
                        # LEFT is typically "Xh Ymin left" (2-3 columns)
                        # We need to intelligently parse this
                        # Simple heuristic: find "left" keyword
                        left_index = None
                        for i, part in enumerate(parts):
                            if "left" in part.lower():
                                left_index = i
                                break

                        if left_index and left_index >= 2:
                            # Next run is everything before LEFT
                            next_run = " ".join(parts[0 : left_index - 1])
                            # Time left is everything up to and including "left"
                            left = " ".join(parts[left_index - 1 : left_index + 1])
                            return next_run, left

            return None, None

        except Exception as e:
            LOGGER.debug(f"Failed to parse timer info: {e}")
            return None, None

    def get_current_schedule(self) -> Optional[str]:
        """
        Get current OnCalendar value from timer file.

        Returns:
            OnCalendar string or None if not found
        """
        try:
            if not self.timer_file.exists():
                return None

            content = self.timer_file.read_text()

            # Parse OnCalendar= line (not commented)
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("OnCalendar=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip()

            return None

        except Exception as e:
            LOGGER.error(f"Failed to read timer schedule: {e}")
            return None

    def get_lock_status(self) -> Dict[str, any]:
        """
        Check lock file status (READ-ONLY operation).

        This method ONLY reads the lock file and checks if the process is running.
        It NEVER creates or modifies the lock file.

        Lock files are ONLY created by the daemon service (kopi-docka.service)
        when it starts via 'kopi-docka admin service daemon'.

        Returns:
            Dict with exists, pid, and process_running fields
        """

        lock_file = Path("/run/kopi-docka/kopi-docka.lock")

        # Check if lock file exists (READ-ONLY - does not create file)
        if not lock_file.exists():
            LOGGER.debug("No lock file found at %s", lock_file)
            return {"exists": False, "pid": None, "process_running": False}

        try:
            # Read PID from lock file (READ-ONLY operation)
            pid_str = lock_file.read_text().strip()
            LOGGER.debug("Lock file found with PID: %s", pid_str)

            pid = int(pid_str) if pid_str.isdigit() else None

            # Check if process is running
            process_running = False
            if pid:
                try:
                    proc_check = run_command(
                        ["kill", "-0", str(pid)],
                        "Checking lock PID",
                        timeout=5,
                        check=False,
                    )
                    returncode = getattr(proc_check, "returncode", 0)
                    try:
                        process_running = int(returncode) == 0
                    except Exception:
                        process_running = True
                    if process_running:
                        LOGGER.debug("Process %d is running", pid)
                    else:
                        LOGGER.debug("Process %d is not running (stale lock)", pid)
                except subprocess.CalledProcessError:
                    process_running = False
                except (ProcessLookupError, PermissionError):
                    process_running = False

            return {"exists": True, "pid": pid, "process_running": process_running}

        except Exception as e:
            LOGGER.warning(f"Error reading lock file: {e}")
            return {"exists": True, "pid": None, "process_running": False}

    def remove_stale_lock(self) -> bool:
        """
        Remove stale lock file if the process is not running.

        A lock is considered stale if:
        1. The lock file exists
        2. The PID in the lock file is not a running process

        Returns:
            True if stale lock was removed, False otherwise
        """
        lock_status = self.get_lock_status()

        if not lock_status["exists"]:
            LOGGER.debug("No lock file to remove")
            return False

        if lock_status["process_running"]:
            LOGGER.warning(
                "Lock file belongs to running process (PID: %s), not removing", lock_status["pid"]
            )
            return False

        # Lock exists but process is not running - it's stale
        lock_file = Path("/run/kopi-docka/kopi-docka.lock")
        try:
            lock_file.unlink()
            LOGGER.info("Removed stale lock file (PID: %s)", lock_status["pid"])
            return True
        except Exception as e:
            LOGGER.error(f"Failed to remove stale lock file: {e}")
            return False

    # -------------------------------------------------------------------------
    # Log Methods
    # -------------------------------------------------------------------------

    def get_logs(self, mode: str = "last", lines: int = 20, unit: str = "service") -> List[str]:
        """
        Get backup logs via journalctl.

        Args:
            mode: Log mode - 'last', 'errors', 'hour', 'today'
            lines: Number of lines for 'last' mode
            unit: Which unit to get logs for - 'service' or 'backup'

        Returns:
            List of log lines
        """
        try:
            unit_name = self.service_name if unit == "service" else self.backup_service_name
            cmd = ["journalctl", "-u", unit_name, "--no-pager"]

            if mode == "last":
                cmd.extend(["-n", str(lines)])
            elif mode == "errors":
                cmd.extend(["-p", "err"])
            elif mode == "hour":
                cmd.extend(["--since", "1 hour ago"])
            elif mode == "today":
                cmd.extend(["--since", "today"])
            else:
                cmd.extend(["-n", str(lines)])

            result = run_command(cmd, "Retrieving logs", timeout=30, check=False)

            if result.returncode != 0:
                return [f"Failed to retrieve logs: {result.stderr}"]

            log_lines = result.stdout.splitlines()
            return log_lines if log_lines else ["No logs found"]

        except Exception as e:
            LOGGER.error(f"Failed to get logs: {e}")
            return [f"Error retrieving logs: {e}"]

    def get_last_backup_info(self) -> BackupInfo:
        """
        Parse logs to find last backup run information.

        Returns:
            BackupInfo object with timestamp, status, and duration
        """
        try:
            # Get recent logs
            logs = self.get_logs(mode="last", lines=100)

            # Look for backup-related log lines
            timestamp = None
            status = "unknown"
            duration = None

            # Patterns to match
            start_pattern = re.compile(r"Starting backup|Backup started")
            success_pattern = re.compile(r"Backup (finished successfully|completed|success)")
            failed_pattern = re.compile(r"Backup (failed|error)")

            for line in reversed(logs):  # Start from most recent
                # Extract timestamp from journalctl line
                # Format: "Dec 21 14:00:00 hostname kopi-docka[12345]: message"
                parts = line.split()
                if len(parts) >= 3:
                    timestamp_candidate = " ".join(parts[0:3])

                    if success_pattern.search(line):
                        status = "success"
                        timestamp = timestamp_candidate
                        break
                    elif failed_pattern.search(line):
                        status = "failed"
                        timestamp = timestamp_candidate
                        break
                    elif start_pattern.search(line) and timestamp is None:
                        timestamp = timestamp_candidate

            return BackupInfo(timestamp=timestamp, status=status, duration=duration)

        except Exception as e:
            LOGGER.error(f"Failed to get last backup info: {e}")
            return BackupInfo(timestamp=None, status="unknown", duration=None)

    # -------------------------------------------------------------------------
    # Control Methods
    # -------------------------------------------------------------------------

    def control_service(self, action: str, unit: str = "service") -> bool:
        """
        Execute systemctl action on service.

        Args:
            action: Action to perform - 'start', 'stop', 'restart', 'enable', 'disable'
            unit: Which unit to control - 'service' or 'timer'

        Returns:
            True if successful, False otherwise
        """
        valid_actions = ["start", "stop", "restart", "enable", "disable"]
        if action not in valid_actions:
            LOGGER.error(f"Invalid action: {action}")
            return False

        try:
            unit_name = self.timer_name if unit == "timer" else self.service_name

            result = run_command(
                ["systemctl", action, unit_name],
                f"Running systemctl {action}",
                timeout=30,
                check=False,
            )

            if result.returncode == 0:
                LOGGER.info(f"Successfully executed: systemctl {action} {unit_name}")
                return True
            else:
                LOGGER.error(f"Failed to {action} {unit_name}: {result.stderr or result.stdout}")
                return False

        except Exception as e:
            LOGGER.error(f"Failed to control service: {e}")
            return False

    def reload_daemon(self) -> bool:
        """
        Reload systemd daemon configuration.

        Returns:
            True if successful, False otherwise
        """
        try:
            result = run_command(
                ["systemctl", "daemon-reload"],
                "Reloading systemd daemon",
                timeout=30,
                check=False,
            )
            return result.returncode == 0
        except Exception as e:
            LOGGER.error(f"Failed to reload daemon: {e}")
            return False

    def validate_service_configuration(self) -> Dict[str, any]:
        """
        Validate service/timer configuration for timer-triggered mode.

        Timer-triggered mode (recommended):
        - Service: disabled (only runs when timer triggers it)
        - Timer: enabled (schedules automatic backups)

        Returns:
            Dict with:
                - health: str ('healthy', 'warning', 'error')
                - message: str (brief health description)
                - issues: List[str] (problems found)
                - recommendations: List[str] (what to do)
                - service_enabled: bool
                - timer_enabled: bool
        """
        try:
            # Check if service is enabled
            service_enabled_result = run_command(
                ["systemctl", "is-enabled", self.service_name],
                "Checking service enabled",
                timeout=10,
                check=False,
            )
            service_enabled = service_enabled_result.stdout.strip() == "enabled"

            # Check if timer is enabled
            timer_enabled_result = run_command(
                ["systemctl", "is-enabled", self.timer_name],
                "Checking timer enabled",
                timeout=10,
                check=False,
            )
            timer_enabled = timer_enabled_result.stdout.strip() == "enabled"

            issues = []
            recommendations = []

            # Validate configuration
            # CORRECT: Timer enabled + Service disabled (timer-triggered mode)
            if timer_enabled and not service_enabled:
                health = "healthy"
                message = "Healthy (timer-triggered mode)"

            # WARNING: Both enabled (causes restart loops)
            elif timer_enabled and service_enabled:
                health = "warning"
                message = "Service should be disabled"
                issues.append("Service is enabled (can cause restart loops)")
                issues.append("May create unnecessary lock files")
                recommendations.append("Disable service: allows timer to control it")
                recommendations.append("Keep timer enabled: schedules automatic backups")

            # ERROR: Timer disabled (backups won't run)
            elif not timer_enabled and not service_enabled:
                health = "error"
                message = "Timer disabled - backups won't run"
                issues.append("Timer is disabled (backups will not run automatically)")
                recommendations.append("Enable timer: enables automatic scheduled backups")

            # WARNING: Only service enabled (no scheduling)
            elif not timer_enabled and service_enabled:
                health = "warning"
                message = "Timer disabled - using service mode"
                issues.append("Timer is disabled (no automatic scheduling)")
                issues.append("Service runs continuously without timer")
                recommendations.append("Enable timer: enables scheduled backups")
                recommendations.append("Disable service: prevents continuous running")

            else:
                health = "unknown"
                message = "Unknown configuration"
                issues.append("Unexpected configuration state")

            return {
                "health": health,
                "message": message,
                "issues": issues,
                "recommendations": recommendations,
                "service_enabled": service_enabled,
                "timer_enabled": timer_enabled,
            }

        except Exception as e:
            LOGGER.error(f"Failed to validate configuration: {e}")
            return {
                "health": "unknown",
                "message": "Failed to check configuration",
                "issues": [f"Error: {e}"],
                "recommendations": [],
                "service_enabled": False,
                "timer_enabled": False,
            }

    def fix_service_configuration(self) -> bool:
        """
        Fix service configuration to recommended timer-triggered mode.

        Actions performed:
        1. Stop kopi-docka.service (if running)
        2. Disable kopi-docka.service
        3. Enable kopi-docka.timer
        4. Start kopi-docka.timer (if not running)
        5. Remove stale lock files

        Returns:
            True if all steps successful, False otherwise
        """
        try:
            success = True

            # Step 1: Stop service if running
            LOGGER.info("Stopping service...")
            if not self.control_service("stop", "service"):
                LOGGER.warning("Failed to stop service (may already be stopped)")
                # Don't fail - service might already be stopped

            # Step 2: Disable service
            LOGGER.info("Disabling service...")
            if not self.control_service("disable", "service"):
                LOGGER.error("Failed to disable service")
                success = False

            # Step 3: Enable timer
            LOGGER.info("Enabling timer...")
            if not self.control_service("enable", "timer"):
                LOGGER.error("Failed to enable timer")
                success = False

            # Step 4: Start timer if not running
            timer_status = self.get_timer_status()
            if not timer_status.active:
                LOGGER.info("Starting timer...")
                if not self.control_service("start", "timer"):
                    LOGGER.error("Failed to start timer")
                    success = False

            # Step 5: Remove stale lock files
            LOGGER.info("Cleaning up stale lock files...")
            self.remove_stale_lock()  # Don't fail if this doesn't work

            if success:
                LOGGER.info("Configuration fixed successfully")
            else:
                LOGGER.error("Some configuration steps failed")

            return success

        except Exception as e:
            LOGGER.error(f"Failed to fix configuration: {e}")
            return False

    def start_backup_now(self) -> bool:
        """
        Start a backup immediately using the one-shot backup service.

        This uses kopi-docka-backup.service (Type=oneshot) instead of
        kopi-docka.service (Type=notify daemon) to avoid timeout issues.

        The daemon service idles waiting for timer events, which causes
        systemd to timeout waiting for sd_notify READY signal. The one-shot
        backup service executes immediately and completes.

        Returns:
            True if backup started successfully, False otherwise
        """
        try:
            LOGGER.info("Starting one-shot backup via kopi-docka-backup.service")
            cmd = ["systemctl", "start", self.backup_service_name]

            run_command(
                cmd,
                "Starting backup service",
                timeout=300,  # 5 minute timeout for backup start
            )

            LOGGER.info("Backup service started successfully")
            return True

        except SubprocessError as e:
            LOGGER.error(f"Failed to start backup: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            LOGGER.error("Backup start timed out after 5 minutes")
            return False
        except Exception as e:
            LOGGER.error(f"Unexpected error starting backup: {e}")
            return False

    def get_backup_service_status(self) -> Dict[str, any]:
        """
        Get status of the last backup run from kopi-docka-backup.service.

        Returns:
            Dict with:
                - active: bool (service is currently running)
                - result: str ('success', 'failed', 'running', 'unknown')
                - exit_code: int or None
        """
        try:
            cmd = [
                "systemctl",
                "show",
                self.backup_service_name,
                "--property=ActiveState,SubState,ExecMainStatus",
            ]
            result = run_command(cmd, "Getting backup service status", timeout=10)

            # Parse output
            props = {}
            for line in result.stdout.strip().split("\n"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    props[key] = value

            active = props.get("ActiveState", "unknown") == "active"
            exit_code_str = props.get("ExecMainStatus", "-1")
            exit_code = int(exit_code_str) if exit_code_str.lstrip("-").isdigit() else -1

            # Determine result
            if active:
                result_status = "running"
            elif exit_code == 0:
                result_status = "success"
            elif exit_code > 0:
                result_status = "failed"
            else:
                result_status = "unknown"

            return {
                "active": active,
                "result": result_status,
                "exit_code": exit_code if exit_code >= 0 else None,
            }

        except Exception as e:
            LOGGER.error(f"Failed to get backup service status: {e}")
            return {"active": False, "result": "unknown", "exit_code": None}

    # -------------------------------------------------------------------------
    # Configuration Methods
    # -------------------------------------------------------------------------

    def edit_timer_schedule(self, new_schedule: str) -> bool:
        """
        Update OnCalendar in timer file.

        Args:
            new_schedule: New OnCalendar value (e.g., "*-*-* 03:00:00")

        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate schedule first
            if not self.validate_oncalendar(new_schedule):
                LOGGER.error(f"Invalid OnCalendar syntax: {new_schedule}")
                return False

            if not self.timer_file.exists():
                LOGGER.error(f"Timer file not found: {self.timer_file}")
                return False

            # Backup current file
            backup_file = self.timer_file.with_suffix(".timer.bak")
            content = self.timer_file.read_text()
            backup_file.write_text(content)
            LOGGER.info(f"Backed up timer file to {backup_file}")

            # Replace OnCalendar= line
            new_lines = []
            replaced = False

            for line in content.splitlines():
                if line.strip().startswith("OnCalendar=") and not line.strip().startswith("#"):
                    new_lines.append(f"OnCalendar={new_schedule}")
                    replaced = True
                else:
                    new_lines.append(line)

            if not replaced:
                LOGGER.error("No OnCalendar= line found in timer file")
                return False

            # Write updated content
            self.timer_file.write_text("\n".join(new_lines) + "\n")
            LOGGER.info(f"Updated timer schedule to: {new_schedule}")

            # Reload systemd and restart timer
            if not self.reload_daemon():
                LOGGER.error("Failed to reload systemd daemon")
                return False

            if not self.control_service("restart", unit="timer"):
                LOGGER.error("Failed to restart timer")
                return False

            return True

        except Exception as e:
            LOGGER.error(f"Failed to edit timer schedule: {e}")
            return False

    # -------------------------------------------------------------------------
    # Validation Methods
    # -------------------------------------------------------------------------

    def validate_time_format(self, time_str: str) -> bool:
        """
        Validate HH:MM format.

        Args:
            time_str: Time string to validate (e.g., "14:30")

        Returns:
            True if valid, False otherwise
        """
        pattern = r"^([0-1]?\d|2[0-3]):[0-5]\d$"
        return bool(re.match(pattern, time_str))

    def validate_oncalendar(self, calendar_str: str) -> bool:
        """
        Test OnCalendar syntax via systemd-analyze.

        Args:
            calendar_str: OnCalendar string to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            result = run_command(
                ["systemd-analyze", "calendar", calendar_str],
                "Validating calendar syntax",
                timeout=5,
                check=False,
            )
            # systemd-analyze returns 0 if syntax is valid
            return result.returncode == 0

        except subprocess.TimeoutExpired:
            LOGGER.warning("systemd-analyze calendar timed out")
            return False
        except FileNotFoundError:
            LOGGER.warning("systemd-analyze not available, skipping validation")
            # If systemd-analyze is not available, accept the input
            # (better to allow the change than block it)
            return True
        except Exception as e:
            LOGGER.debug(f"Failed to validate OnCalendar: {e}")
            return False

    # -------------------------------------------------------------------------
    # Installation Methods
    # -------------------------------------------------------------------------

    def units_exist(self) -> bool:
        """
        Check if systemd units are installed.

        Returns:
            True if units exist, False otherwise
        """
        service_file = Path("/etc/systemd/system") / self.service_name
        timer_file = Path("/etc/systemd/system") / self.timer_name

        return service_file.exists() and timer_file.exists()
