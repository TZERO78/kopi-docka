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
    id: str
    name: str
    is_running: bool = False
    database_type: Optional[str] = None  # e.g. "postgres", "mysql", "mariadb", "mongo", "redis"


@dataclass
class VolumeInfo:
    name: str
    mountpoint: str
    size_bytes: Optional[int] = None


@dataclass
class BackupUnit:
    name: str
    containers: List[ContainerInfo] = field(default_factory=list)
    volumes: List[VolumeInfo] = field(default_factory=list)
    compose_file: Optional[Path] = None  # path to docker-compose.yml (optional)

    def get_database_containers(self) -> List[ContainerInfo]:
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
        }


@dataclass
class RestorePoint:
    unit_name: str
    timestamp: datetime
    backup_id: str  # REQUIRED
    recipe_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    volume_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    database_snapshots: List[Dict[str, Any]] = field(default_factory=list)
