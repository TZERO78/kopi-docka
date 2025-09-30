################################################################################
# KOPI-DOCKA
#
# @file:        init.py
# @module:      kopi_docka
# @description: Exposes version, logging, and core managers for package consumers.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Re-exports Config, DockerDiscovery, BackupManager, and other entry points
# - Sets __version__ from constants.VERSION for tooling introspection
# - Keeps logging helpers accessible via the package namespace
################################################################################

"""
Kopi-Docka: A robust backup solution for Docker environments using Kopia.

This package provides a modular command-line tool for backing up and restoring
Docker containers and their associated data with minimal downtime and maximum
reliability.
"""

from .constants import VERSION

__version__ = VERSION
__author__ = "Kopi-Docka Development Team"

from .logging import (
    get_logger,
    log_manager,
    setup_logging,
    StructuredFormatter,
    Colors,
)

from .types import (
    BackupUnit,
    ContainerInfo,
    VolumeInfo,
    BackupMetadata,
    RestorePoint,
)

from .config import Config
from .discovery import DockerDiscovery
from .backup import BackupManager
from .restore import RestoreManager
from .repository import KopiaRepository

__all__ = [
    "VERSION",
    "BackupUnit",
    "ContainerInfo",
    "VolumeInfo",
    "BackupMetadata",
    "RestorePoint",
    "Config",
    "DockerDiscovery",
    "BackupManager",
    "RestoreManager",
    "KopiaRepository",
    "get_logger",
    "log_manager",
    "setup_logging",
    "StructuredFormatter",
    "Colors",
]
