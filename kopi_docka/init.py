"""
Kopi-Docka: A robust backup solution for Docker environments using Kopia.

This package provides a modular command-line tool for backing up and restoring
Docker containers and their associated data with minimal downtime and maximum
reliability.
"""

__version__ = "1.0.0"
__author__ = "Kopia-Docka Development Team"

from .types import BackupUnit, ContainerInfo, VolumeInfo
from .config import Config
from .discovery import DockerDiscovery
from .backup import BackupManager
from .restore import RestoreManager
from .repository import KopiaRepository

__all__ = [
    'BackupUnit',
    'ContainerInfo',
    'VolumeInfo',
    'Config',
    'DockerDiscovery',
    'BackupManager',
    'RestoreManager',
    'KopiaRepository',
]