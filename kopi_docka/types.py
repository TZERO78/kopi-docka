################################################################################
# KOPI-DOCKA
#
# @file:        types.py
# @module:      kopi_docka.types
# @description: Shared data models for backup units, metadata, and restore points.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - ContainerInfo and VolumeInfo capture Docker metadata snapshots
# - BackupUnit groups containers, volumes, and optional compose files
# - BackupMetadata and RestorePoint track snapshot ids and errors
################################################################################

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


# ---- Core DTOs used by backup/restore ----


@dataclass
class ContainerInfo:
    """Container information."""

    id: str
    name: str
    image: str
    status: str
    labels: Dict[str, str] = field(default_factory=dict)
    environment: Dict[str, str] = field(default_factory=dict)
    volumes: List[str] = field(default_factory=list)
    compose_files: List[Path] = field(default_factory=list)  # All compose files (incl. overrides)
    inspect_data: Optional[Dict[str, Any]] = None
    database_type: Optional[str] = None

    @property
    def compose_file(self) -> Optional[Path]:
        """First compose file (backwards compatibility)."""
        return self.compose_files[0] if self.compose_files else None

    @property
    def is_running(self) -> bool:
        """Check if container is running."""
        return self.status.lower().startswith("running")

    @property
    def is_database(self) -> bool:
        """Check if container is a database."""
        return self.database_type is not None

    @property
    def stack_name(self) -> Optional[str]:
        """Get stack name from labels."""
        from .helpers.constants import DOCKER_COMPOSE_PROJECT_LABEL

        return self.labels.get(DOCKER_COMPOSE_PROJECT_LABEL)


@dataclass
class VolumeInfo:
    """Volume information."""

    name: str
    driver: str
    mountpoint: str
    labels: Dict[str, str] = field(default_factory=dict)
    size_bytes: Optional[int] = None
    container_ids: List[str] = field(default_factory=list)


@dataclass
class MachineInfo:
    """Information about a backup source machine (for cross-machine restore).

    Used by the advanced restore wizard to show all machines that have
    backups in the repository.
    """

    hostname: str
    last_backup: datetime
    backup_count: int = 0
    units: List[str] = field(default_factory=list)
    total_size: int = 0


@dataclass
class BackupUnit:
    name: str
    type: str  # ← WICHTIG: "stack" oder "standalone"
    containers: List[ContainerInfo] = field(default_factory=list)
    volumes: List[VolumeInfo] = field(default_factory=list)
    compose_files: List[Path] = field(default_factory=list)  # All compose files (incl. overrides)

    @property
    def compose_file(self) -> Optional[Path]:
        """First compose file (backwards compatibility)."""
        return self.compose_files[0] if self.compose_files else None

    @property
    def has_databases(self) -> bool:
        """Check if unit contains database containers."""
        return any(c.database_type for c in self.containers)

    @property
    def running_containers(self) -> List[ContainerInfo]:
        """Get list of running containers."""
        return [c for c in self.containers if c.is_running]

    @property
    def total_volume_size(self) -> int:
        """Get total size of all volumes."""
        return sum(v.size_bytes or 0 for v in self.volumes)

    def get_database_containers(self) -> List[ContainerInfo]:
        """Get containers with database_type set."""
        return [c for c in self.containers if c.database_type]


# ---- Metadata & Restore points ----


@dataclass
class BackupMetadata:
    unit_name: str
    timestamp: datetime
    duration_seconds: float
    backup_id: str  # REQUIRED
    success: bool = True
    error_message: Optional[str] = None
    kopia_snapshot_ids: List[str] = field(default_factory=list)
    volumes_backed_up: int = 0
    databases_backed_up: int = 0
    errors: List[str] = field(default_factory=list)
    backup_scope: str = "standard"  # minimal, standard, full
    networks_backed_up: int = 0
    docker_config_backed_up: bool = False
    hooks_executed: List[str] = field(default_factory=list)
    backup_format: str = "direct"  # "tar" (legacy) or "direct" (v5.0+)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_name": self.unit_name,
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
            "backup_id": self.backup_id,
            "success": self.success,
            "error_message": self.error_message,
            "kopia_snapshot_ids": self.kopia_snapshot_ids,
            "volumes_backed_up": self.volumes_backed_up,
            "databases_backed_up": self.databases_backed_up,
            "errors": self.errors,
            "backup_scope": self.backup_scope,
            "networks_backed_up": self.networks_backed_up,
            "docker_config_backed_up": self.docker_config_backed_up,
            "hooks_executed": self.hooks_executed,
            "backup_format": self.backup_format,
        }


@dataclass
class RestorePoint:
    unit_name: str
    timestamp: datetime
    backup_id: str  # REQUIRED
    recipe_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    volume_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    database_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    network_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    docker_config_snapshots: List[Dict[str, Any]] = field(default_factory=list)
