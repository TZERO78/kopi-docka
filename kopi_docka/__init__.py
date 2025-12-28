################################################################################
# KOPI-DOCKA
#
# @file:        __init__.py
# @module:      kopi_docka
# @description: Package entry point exposing core APIs and utilities
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     5.5.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Changes in v2.0.0:
# - Restructured into helpers/, cores/, commands/ modules
# - Updated imports to reflect new package organization
# - Maintained backward compatibility for external consumers
################################################################################

"""
Kopi-Docka: A robust backup solution for Docker environments using Kopia.

This package provides a modular command-line tool for backing up and restoring
Docker containers and their associated data with minimal downtime and maximum
reliability.
"""

# Version and metadata
from .helpers.constants import VERSION

__version__ = VERSION
__author__ = "Markus F. (TZERO78) & KI-Assistenten"

# Logging utilities
from .helpers.logging import (
    get_logger,
    log_manager,
    setup_logging,
    StructuredFormatter,
    Colors,
)

# Type definitions
from .types import (
    BackupUnit,
    ContainerInfo,
    VolumeInfo,
    BackupMetadata,
    RestorePoint,
)

# Configuration and helpers
from .helpers import (
    Config,
    create_default_config,
    generate_secure_password,
)

# Core business logic
from .cores import (
    BackupManager,
    RestoreManager,
    DockerDiscovery,
    KopiaRepository,
    DependencyManager,
    DryRunReport,
    DisasterRecoveryManager,
    KopiDockaService,
    ServiceConfig,
    KopiaPolicyManager,
)

__all__ = [
    # Version
    "VERSION",
    "__version__",
    "__author__",
    # Types
    "BackupUnit",
    "ContainerInfo",
    "VolumeInfo",
    "BackupMetadata",
    "RestorePoint",
    # Configuration
    "Config",
    "create_default_config",
    "generate_secure_password",
    # Core Managers
    "BackupManager",
    "RestoreManager",
    "DockerDiscovery",
    "KopiaRepository",
    "DependencyManager",
    "DryRunReport",
    "DisasterRecoveryManager",
    "KopiaPolicyManager",
    # Service
    "KopiDockaService",
    "ServiceConfig",
    # Logging
    "get_logger",
    "log_manager",
    "setup_logging",
    "StructuredFormatter",
    "Colors",
]
