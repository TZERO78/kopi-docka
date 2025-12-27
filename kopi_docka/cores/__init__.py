################################################################################
# KOPI-DOCKA
#
# @file:        __init__.py
# @module:      kopi_docka.cores
# @description: Core business logic modules for Kopi-Docka
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Core business logic modules for Kopi-Docka."""

from .backup_manager import BackupManager
from .restore_manager import RestoreManager
from .docker_discovery import DockerDiscovery
from .repository_manager import KopiaRepository
from .dependency_manager import DependencyManager
from .dry_run_manager import DryRunReport
from .disaster_recovery_manager import DisasterRecoveryManager
from .service_manager import (
    KopiDockaService,
    ServiceConfig,
    write_systemd_units,  # ← Diese Zeile hinzufügen
)
from .service_helper import ServiceHelper
from .kopia_policy_manager import KopiaPolicyManager
from .notification_manager import NotificationManager, BackupStats

__all__ = [
    "BackupManager",
    "RestoreManager",
    "DockerDiscovery",
    "KopiaRepository",
    "DependencyManager",
    "DryRunReport",
    "DisasterRecoveryManager",
    "KopiDockaService",
    "ServiceConfig",
    "write_systemd_units",  # ← Diese Zeile hinzufügen
    "ServiceHelper",
    "KopiaPolicyManager",
    "NotificationManager",
    "BackupStats",
]
