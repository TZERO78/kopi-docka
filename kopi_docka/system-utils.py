"""
System utilities module for Kopi-Docka.

This module provides system-level utilities including resource monitoring,
dependency checking, and optimization calculations.
"""

import logging
import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple

import psutil

from .constants import RAM_WORKER_THRESHOLDS


logger = logging.getLogger(__name__)


class SystemUtils:
    """
    System utilities for resource management and dependency checking.
    
    Provides methods for checking system resources, validating dependencies,
    and calculating optimal configurations based on system capabilities.
    """
    
    @staticmethod
    def check_docker() -> bool:
        """
        Check if Docker is installed and accessible.
        
        Returns:
            True if Docker is available
        """
        try:
            result = subprocess.run(
                ['docker', 'version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    @staticmethod
    def check_kopia() -> bool:
        """
        Check if Kopia is installed and accessible.
        
        Returns:
            True if Kopia is available
        """
        return shutil.which('kopia') is not None
    
    @staticmethod
    def check_tar() -> bool:
        """
        Check if tar is installed and accessible.
        
        Returns:
            True if tar is available
        """
        return shutil.which('tar') is not None
    
    @staticmethod
    def get_available_ram() -> float:
        """
        Get available system RAM in gigabytes.
        
        Returns:
            Available RAM in GB
        """
        try:
            memory = psutil.virtual_memory()
            return memory.total / (1024 ** 3)  # Convert to GB
        except Exception as e:
            logger.error(f"Failed to get RAM info: {e}")
            return 2.0  # Conservative default
    
    @staticmethod
    def get_available_disk_space(path: str = '/') -> float:
        """
        Get available disk space in gigabytes.
        
        Args:
            path: Path to check disk space for
            
        Returns:
            Available disk space in GB
        """
        try:
            usage = psutil.disk_usage(path)
            return usage.free / (1024 ** 3)  # Convert to GB
        except Exception as e:
            logger.error(f"Failed to get disk space: {e}")
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
        
        # Determine workers based on RAM
        ram_workers = 1
        for threshold_gb, workers in RAM_WORKER_THRESHOLDS:
            if ram_gb <= threshold_gb:
                ram_workers = workers
                break
        
        # Don't exceed CPU count
        optimal = min(ram_workers, cpu_count)
        
        logger.debug(f"System has {ram_gb:.1f}GB RAM, {cpu_count} CPUs. "
                    f"Recommending {optimal} workers.")
        
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
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """
        Format duration into human-readable string.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted string (e.g., "2h 15m 30s")
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
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
    def ensure_directory(path: Path, mode: int = 0o755):
        """
        Ensure directory exists with proper permissions.
        
        Args:
            path: Directory path
            mode: Permission mode
        """
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(mode)
    
    @staticmethod
    def check_port_available(port: int, host: str = '127.0.0.1') -> bool:
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
                return result != 0
        except Exception:
            return False
    
    @staticmethod
    def get_docker_version() -> Optional[Tuple[int, int, int]]:
        """
        Get Docker version.
        
        Returns:
            Version tuple (major, minor, patch) or None
        """
        try:
            result = subprocess.run(
                ['docker', 'version', '--format', '{{.Server.Version}}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version_str = result.stdout.strip()
                # Parse version like "20.10.21"
                parts = version_str.split('.')
                if len(parts) >= 3:
                    return (int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception as e:
            logger.error(f"Failed to get Docker version: {e}")
        
        return None
    
    @staticmethod
    def get_kopia_version() -> Optional[str]:
        """
        Get Kopia version.
        
        Returns:
            Version string or None
        """
        try:
            result = subprocess.run(
                ['kopia', 'version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Parse version from output
                for line in result.stdout.split('\n'):
                    if line.startswith('VERSION:'):
                        return line.split(':', 1)[1].strip()
        except Exception as e:
            logger.error(f"Failed to get Kopia version: {e}")
        
        return None