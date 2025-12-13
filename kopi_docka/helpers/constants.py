################################################################################
# KOPI-DOCKA
#
# @file:        constants.py
# @module:      kopi_docka.constants
# @description: Central dictionary of application constants and tuning thresholds.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Defines VERSION and default locations for configs and backups
# - DATABASE_IMAGES guides discovery when classifying database containers
# - RAM_WORKER_THRESHOLDS inform SystemUtils worker auto-tuning
################################################################################

"""
Constants used throughout the Kopi-Docka application.

This module defines all constant values used across different modules
to ensure consistency and ease of maintenance.

Notes:
- Kopi-Docka now performs cold backups of recipes and volumes only.
  Database-specific dump/restore has been removed to simplify the tool.
"""

from pathlib import Path

# Version information
VERSION = "3.7.0"

# Backup Scope Levels
BACKUP_SCOPE_MINIMAL = "minimal"      # Only volumes
BACKUP_SCOPE_STANDARD = "standard"    # Volumes + recipes + networks (default)
BACKUP_SCOPE_FULL = "full"           # Everything including daemon config

BACKUP_SCOPES = {
    BACKUP_SCOPE_MINIMAL: {
        "name": "Minimal",
        "description": "Only container data (volumes)",
        "includes": ["volumes"],
        "fast": True,
        "size": "small"
    },
    BACKUP_SCOPE_STANDARD: {
        "name": "Standard",
        "description": "Container data + configuration (recommended)",
        "includes": ["volumes", "recipes", "networks"],
        "fast": False,
        "size": "medium"
    },
    BACKUP_SCOPE_FULL: {
        "name": "Full System",
        "description": "Complete system (DR-ready)",
        "includes": ["volumes", "recipes", "networks", "docker_config"],
        "fast": False,
        "size": "large"
    }
}

# Default config paths
DEFAULT_CONFIG_PATHS = {
    "root": Path("/etc/kopi-docka.json"),
    # fixed app folder name (was 'kopi-docker')
    "user": Path.home() / ".config" / "kopi-docka" / "config.json",
}

# Docker labels
DOCKER_COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
DOCKER_COMPOSE_CONFIG_LABEL = "com.docker.compose.project.config_files"
DOCKER_COMPOSE_SERVICE_LABEL = "com.docker.compose.service"

# Backup paths
DEFAULT_BACKUP_BASE = "/backup/kopi-docka"
RECIPE_BACKUP_DIR = "recipes"
VOLUME_BACKUP_DIR = "volumes"
NETWORK_BACKUP_DIR = "networks"
DOCKER_CONFIG_BACKUP_DIR = "docker-config"
# DATABASE_BACKUP_DIR removed (no DB dumps in cold backups)

# Backup hooks
HOOK_PRE_BACKUP = "pre_backup"
HOOK_POST_BACKUP = "post_backup"
HOOK_PRE_RESTORE = "pre_restore"
HOOK_POST_RESTORE = "post_restore"

# Database image detection (used only for classification/ordering in discovery)
# Kept minimal: only patterns; other fields removed.
DATABASE_IMAGES = {
    "postgres": {
        "patterns": ["postgres:", "postgresql:", "postgis/"],
    },
    "mysql": {
        "patterns": ["mysql:", "percona:"],
    },
    "mariadb": {
        "patterns": ["mariadb:"],
    },
    "mongodb": {
        "patterns": ["mongo:", "mongodb:"],
    },
    "redis": {
        "patterns": ["redis:", "redis/"],
    },
}

# System thresholds
# (available RAM → default parallel workers upper bound)
RAM_WORKER_THRESHOLDS = [
    (2, 1),  # <= 2GB: 1 worker
    (4, 2),  # <= 4GB: 2 workers
    (8, 4),  # <= 8GB: 4 workers
    (16, 8),  # <= 16GB: 8 workers
    (float("inf"), 12),  # > 16GB: 12 workers
]

# Timeouts (in seconds)
CONTAINER_STOP_TIMEOUT = 30
CONTAINER_START_TIMEOUT = 60
# BACKUP_OPERATION_TIMEOUT removed; per-task timeout is configurable via INI (backup.task_timeout)

# Logging
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
