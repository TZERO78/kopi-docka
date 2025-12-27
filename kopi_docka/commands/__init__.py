################################################################################
# KOPI-DOCKA
#
# @file:        __init__.py
# @module:      kopi_docka.commands
# @description: CLI command modules for Kopi-Docka
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.4.1
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
CLI command modules for Kopi-Docka.

Top-Level Commands (The Big 6):
  - setup_commands          - Complete setup wizard
  - backup_commands         - Backup and restore
  - dry_run_commands        - Backup simulation
  - disaster_recovery_commands - Recovery bundle creation
  - doctor_commands         - System health check

Admin Commands (under commands/advanced/):
  - config_commands         - Configuration management
  - repo_commands           - Repository management
  - service_commands        - Systemd service management
  - system_commands         - Dependency management
  - snapshot_commands       - Snapshot/unit management

Legacy modules (still available for internal use):
  - config_commands         - Original config commands
  - dependency_commands     - Original dependency commands
  - repository_commands     - Original repository commands
  - service_commands        - Original service commands
"""

# Top-level command modules
from . import (
    setup_commands,
    backup_commands,
    dry_run_commands,
    disaster_recovery_commands,
    doctor_commands,
)

# Legacy modules (kept for backward compatibility/internal use)
from . import (
    config_commands,
    dependency_commands,
    repository_commands,
    service_commands,
)

__all__ = [
    # Top-level commands
    "setup_commands",
    "backup_commands",
    "dry_run_commands",
    "disaster_recovery_commands",
    "doctor_commands",
    # Legacy modules
    "config_commands",
    "dependency_commands",
    "repository_commands",
    "service_commands",
]
