################################################################################
# KOPI-DOCKA
#
# @file:        system_utils.py
# @module:      kopi_docka.helpers.system_utils
# @description: System-level helpers for resource probing and scheduling decisions.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Detects remote repository URLs to skip local filesystem probes
# - get_optimal_workers caps concurrency based on RAM thresholds
# - get_system_info aggregates CPU, RAM, and disk metrics for reports
################################################################################

"""
System utilities module for Kopi-Docka.

This module provides system-level utilities including resource monitoring
and optimization calculations.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import psutil

from .constants import RAM_WORKER_THRESHOLDS
from .ui_utils import run_command

logger = logging.getLogger(__name__)


def _is_remote_path(path_str: str) -> bool:
    """Return True if the string looks like a remote URL (e.g., s3://, b2://)."""
    return "://" in path_str


def _disk_probe_base(path: str) -> str:
    """
    Return a valid filesystem path for disk space probing.
    
    For remote URLs (s3://, b2://, etc.): returns '/'
    For local paths: walks up to nearest existing parent, falls back to '/'
    
    Args:
        path: Path to probe (local or remote URL)
        
    Returns:
        Existing filesystem path safe for psutil.disk_usage()
    """
    if _is_remote_path(path):
        return "/"
    
    try:
        probe_path = Path(path)
        # Walk up directory tree to find first existing parent
        while not probe_path.exists():
            parent = probe_path.parent
            if parent == probe_path:  # Reached filesystem root
                return "/"
            probe_path = parent
        return str(probe_path)
    except Exception:
        return "/"


class SystemUtils:
    """
    System utilities for resource management.

    Provides methods for checking system resources and calculating
    optimal configurations based on system capabilities.
    """

    def __init__(self):
        """Initialize SystemUtils with DependencyManager instance."""
        self._dep_manager = None

    def _get_dep_manager(self):
        """Lazy-load DependencyManager instance."""
        if self._dep_manager is None:
            from ..cores.dependency_manager import DependencyManager

            self._dep_manager = DependencyManager()
        return self._dep_manager

    # Dependency checks (delegate to DependencyManager)

    def check_docker(self) -> bool:
        """Check if Docker is installed and accessible."""
        return self._get_dep_manager().check_docker()

    def check_kopia(self) -> bool:
        """Check if Kopia is installed and accessible."""
        return self._get_dep_manager().check_kopia()

    def check_tar(self) -> bool:
        """Check if tar is installed and accessible."""
        return self._get_dep_manager().check_tar()

    # Resource monitoring methods

    @staticmethod
    def get_available_ram() -> float:
        """
        Get available system RAM in gigabytes.

        Returns:
            Available RAM in GB
        """
        try:
            memory = psutil.virtual_memory()
            return memory.available / (1024**3)  # Available, not total
        except Exception as e:
            logger.error(f"Failed to get RAM info: {e}")
            return 2.0  # Conservative default

    @staticmethod
    def get_available_disk_space(path: str = "/") -> float:
        """
        Get available disk space in gigabytes.

        Args:
            path: Path to check disk space for

        Returns:
            Available disk space in GB
        """
        try:
            probe = _disk_probe_base(path)
            usage = psutil.disk_usage(probe)
            return usage.free / (1024**3)
        except Exception as e:
            logger.error(f"Failed to get disk space for {path}: {e}")
            return 0.0

    @staticmethod
    def get_total_disk_space(path: str = "/") -> float:
        """
        Get total disk space in gigabytes.

        Args:
            path: Path to check disk space for

        Returns:
            Total disk space in GB
        """
        try:
            probe = _disk_probe_base(path)
            usage = psutil.disk_usage(probe)
            return usage.total / (1024**3)
        except Exception as e:
            logger.error(f"Failed to get total disk space for {path}: {e}")
            return 0.0

    @staticmethod
    def get_disk_usage_percent(path: str = "/") -> float:
        """
        Get disk usage percentage.

        Args:
            path: Path to check disk usage for

        Returns:
            Disk usage percentage (0-100)
        """
        try:
            probe = _disk_probe_base(path)
            usage = psutil.disk_usage(probe)
            return usage.percent
        except Exception as e:
            logger.error(f"Failed to get disk usage for {path}: {e}")
            return 0.0

    @staticmethod
    def get_cpu_count() -> int:
        """
        Get number of CPU cores.

        Returns:
            Number of CPU cores
        """
        try:
            return psutil.cpu_count(logical=True) or 1
        except Exception:
            return 1

    @staticmethod
    def get_optimal_workers() -> int:
        """
        Calculate optimal number of parallel workers based on system resources.

        Returns:
            Recommended number of workers
        """
        ram_gb = SystemUtils.get_available_ram()
        cpu_count = SystemUtils.get_cpu_count()

        # Determine workers based on RAM thresholds
        ram_workers = 1
        for threshold_gb, workers in RAM_WORKER_THRESHOLDS:
            if ram_gb <= threshold_gb:
                ram_workers = workers
                break

        # Don't exceed CPU count
        optimal = min(ram_workers, cpu_count)

        logger.debug(
            f"System has {ram_gb:.1f}GB available RAM, {cpu_count} CPUs. "
            f"Recommending {optimal} workers."
        )

        return optimal

    @staticmethod
    def estimate_backup_size(path: str) -> int:
        """
        Estimate size of path for backup.

        Args:
            path: Path to estimate

        Returns:
            Estimated size in bytes
        """
        try:
            if os.path.isfile(path):
                return os.path.getsize(path)

            total_size = 0
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, IOError):
                        continue

            return total_size

        except Exception as e:
            logger.error(f"Failed to estimate size of {path}: {e}")
            return 0

    @staticmethod
    def format_bytes(size_bytes: int) -> str:
        """
        Format bytes into human-readable string.

        Args:
            size_bytes: Size in bytes

        Returns:
            Formatted string (e.g., "1.5 GB")
        """
        if size_bytes <= 0:
            return "0 B"

        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} EB"

    @staticmethod
    def format_duration(seconds: float) -> str:
        """
        Format duration into human-readable string.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted string (e.g., "2h 15m 30s")
        """
        if seconds <= 0:
            return "0s"

        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")

        return " ".join(parts)

    @staticmethod
    def is_root() -> bool:
        """
        Check if running as root.

        Returns:
            True if running as root
        """
        return os.geteuid() == 0

    @staticmethod
    def get_current_user() -> str:
        """
        Get current username.

        Returns:
            Current username
        """
        import pwd

        try:
            return pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            return os.environ.get("USER", "unknown")

    @staticmethod
    def ensure_directory(path: Path, mode: int = 0o755):
        """
        Ensure directory exists with proper permissions.

        Args:
            path: Directory path
            mode: Permission mode
        """
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(mode)
        except Exception:
            # Some FS may not support chmod (e.g., mounted cloud drives)
            pass

    @staticmethod
    def check_port_available(port: int, host: str = "127.0.0.1") -> bool:
        """
        Check if a network port is available.

        Args:
            port: Port number
            host: Host address

        Returns:
            True if port is available
        """
        import socket

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex((host, port))
                return result != 0  # True if port is NOT in use
        except Exception:
            return False

    @staticmethod
    def get_system_info() -> Dict[str, object]:
        """
        Get comprehensive system information.

        Returns:
            Dictionary with system information
        """
        import platform

        try:
            info: Dict[str, object] = {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "hostname": platform.node(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "cpu_count": SystemUtils.get_cpu_count(),
                "ram_gb": SystemUtils.get_available_ram(),
                "disk_free_gb": SystemUtils.get_available_disk_space(),
            }

            # Add Docker info if available
            try:
                docker_version = SystemUtils.get_docker_version()
                if docker_version:
                    info["docker_version"] = ".".join(map(str, docker_version))
            except Exception:
                pass

            # Add Kopia info if available
            try:
                kopia_version = SystemUtils.get_kopia_version()
                if kopia_version:
                    info["kopia_version"] = kopia_version
            except Exception:
                pass

            return info

        except Exception as e:
            logger.error(f"Failed to get system info: {e}")
            return {}

    @staticmethod
    def get_docker_version() -> Optional[Tuple[int, int, int]]:
        """
        Get Docker version.

        Returns:
            Version tuple (major, minor, patch) or None
        """
        try:
            result = run_command(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                "Getting Docker version",
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                version_str = result.stdout.strip()
                # Parse version like "20.10.21" or "24.0.5"
                parts = version_str.split(".")
                if len(parts) >= 3:
                    return (int(parts[0]), int(parts[1]), int(parts[2]))
                elif len(parts) == 2:
                    return (int(parts[0]), int(parts[1]), 0)
        except Exception as e:
            logger.debug(f"Failed to get Docker version: {e}")

        return None

    @staticmethod
    def get_kopia_version() -> Optional[str]:
        """
        Get Kopia version.

        Returns:
            Version string or None
        """
        # Try common variants for compatibility across distributions
        for args in (["kopia", "--version"], ["kopia", "version"]):
            try:
                result = run_command(args, "Getting Kopia version", timeout=5, check=False)
                if result.returncode == 0:
                    for line in (result.stdout or result.stderr).split("\n"):
                        if "version" in line.lower() or line.strip():
                            # Return first token that looks like a semver
                            for token in line.replace(",", " ").split():
                                if token and token[0].isdigit():
                                    return token
                    # Fallback: whole trimmed line
                    out = (result.stdout or result.stderr).strip()
                    if out:
                        return out
            except Exception as e:
                logger.debug(f"Failed to get Kopia version via {' '.join(args)}: {e}")
        return None

    @staticmethod
    def get_load_average() -> Tuple[float, float, float]:
        """
        Get system load average.

        Returns:
            Tuple of (1min, 5min, 15min) load averages
        """
        try:
            return os.getloadavg()
        except Exception:
            return (0.0, 0.0, 0.0)

    @staticmethod
    def get_memory_info() -> Dict[str, float]:
        """
        Get detailed memory information.

        Returns:
            Dictionary with memory stats in GB
        """
        try:
            mem = psutil.virtual_memory()
            return {
                "total_gb": mem.total / (1024**3),
                "available_gb": mem.available / (1024**3),
                "used_gb": mem.used / (1024**3),
                "free_gb": mem.free / (1024**3),
                "percent_used": float(mem.percent),
            }
        except Exception as e:
            logger.error(f"Failed to get memory info: {e}")
            return {}

    @staticmethod
    def check_writable(path: str) -> bool:
        """
        Check if path is writable.

        Args:
            path: Path to check

        Returns:
            True if path is writable
        """
        try:
            test_path = Path(path)
            if test_path.is_dir():
                # Test directory writability
                test_file = test_path / ".kopi_docka_write_test"
                try:
                    test_file.touch()
                    test_file.unlink()
                    return True
                except Exception:
                    return False
            else:
                # Test parent directory writability
                return os.access(test_path.parent, os.W_OK)
        except Exception:
            return False
