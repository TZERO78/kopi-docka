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
    bind_mounts: List["BindMountInfo"] = field(default_factory=list)  # Persistent host binds
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
class BindMountInfo:
    """A host-directory bind mount discovered on a container (Plan 0040 / #129).

    Persistent bind mounts (e.g. ``./vw-data:/data``) are first-class backup
    targets — their host ``source`` path is snapshotted just like a named volume.
    Runtime-only host internals (docker socket, /proc, /sys, /dev) are classified
    via :func:`is_runtime_only` and never archived.
    """

    source: str  # Host path (absolute)
    destination: str  # Path inside the container
    read_only: bool = False
    container_ids: List[str] = field(default_factory=list)
    size_bytes: Optional[int] = None

    @property
    def is_runtime_only(self) -> bool:
        """True when the source is a host internal that must not be archived."""
        from .helpers.constants import (
            RUNTIME_ONLY_BIND_PREFIXES,
            RUNTIME_ONLY_BIND_BASENAMES,
        )

        src = (self.source or "").rstrip("/") or "/"
        if any(src == p or src.startswith(p + "/") for p in RUNTIME_ONLY_BIND_PREFIXES):
            return True
        return any(src.endswith("/" + b) or src == b for b in RUNTIME_ONLY_BIND_BASENAMES)


@dataclass
class BackupSource:
    """One source to snapshot in a single backup run (Plan 0028).

    Discovery (Docker walk, recipe staging, network export, …) emits a list
    of these *before* containers are stopped, and the snapshot loop consumes
    them. ``path`` is the absolute filesystem path passed to
    ``kopia snapshot create``; ``tags`` is the metadata dict attached to the
    resulting snapshot so it can be looked up later (unit, backup_id, kind).

    Kind values mirror the historical helpers — ``volume``, ``recipe``,
    ``network``, ``docker_config`` — purely informational; the snapshot
    create call treats them identically.
    """

    path: str
    kind: str
    tags: Dict[str, str] = field(default_factory=dict)
    description: Optional[str] = None
    # Glob patterns passed to `kopia snapshot create --ignore`. Only set for
    # data sources (volumes, binds) where the operator's `exclude_patterns`
    # config should apply; metadata staging (recipes/networks/config) leaves
    # this None so nothing is trimmed from the backup recipe.
    exclude_patterns: Optional[List[str]] = None


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
    bind_mounts: List[BindMountInfo] = field(default_factory=list)  # Persistent host binds
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
class BackupErrorDetail:
    """Structured error context captured from a failed Kopia command."""

    phase: str
    message: str
    exit_code: Optional[int] = None
    stderr_tail: Optional[str] = None


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
    bind_mounts_backed_up: int = 0
    databases_backed_up: int = 0
    errors: List[str] = field(default_factory=list)
    backup_scope: str = "standard"  # minimal, standard, full
    networks_backed_up: int = 0
    docker_config_backed_up: bool = False
    hooks_executed: List[str] = field(default_factory=list)
    backup_format: str = "direct"  # "tar" (legacy) or "direct" (v5.0+)
    error_details: List["BackupErrorDetail"] = field(default_factory=list)

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
            "bind_mounts_backed_up": self.bind_mounts_backed_up,
            "databases_backed_up": self.databases_backed_up,
            "errors": self.errors,
            "backup_scope": self.backup_scope,
            "networks_backed_up": self.networks_backed_up,
            "docker_config_backed_up": self.docker_config_backed_up,
            "hooks_executed": self.hooks_executed,
            "backup_format": self.backup_format,
            "error_details": [
                {
                    "phase": d.phase,
                    "message": d.message,
                    "exit_code": d.exit_code,
                    "stderr_tail": d.stderr_tail,
                }
                for d in self.error_details
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackupMetadata":
        """Create BackupMetadata from dictionary (JSON deserialization).

        Tolerant of missing fields for backwards compatibility
        with older metadata files that had fewer fields.
        """
        timestamp_raw = data.get("timestamp", "")
        if isinstance(timestamp_raw, str):
            timestamp = datetime.fromisoformat(timestamp_raw)
        else:
            timestamp = timestamp_raw

        raw_details = data.get("error_details", [])
        error_details = [
            BackupErrorDetail(
                phase=d.get("phase", ""),
                message=d.get("message", ""),
                exit_code=d.get("exit_code"),
                stderr_tail=d.get("stderr_tail"),
            )
            for d in raw_details
            if isinstance(d, dict)
        ]

        return cls(
            unit_name=data.get("unit_name", "unknown"),
            timestamp=timestamp,
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            backup_id=data.get("backup_id", ""),
            success=data.get("success", True),
            error_message=data.get("error_message"),
            kopia_snapshot_ids=data.get("kopia_snapshot_ids", []),
            volumes_backed_up=int(data.get("volumes_backed_up", 0)),
            bind_mounts_backed_up=int(data.get("bind_mounts_backed_up", 0)),
            databases_backed_up=int(data.get("databases_backed_up", 0)),
            errors=data.get("errors", []),
            backup_scope=data.get("backup_scope", "standard"),
            networks_backed_up=int(data.get("networks_backed_up", 0)),
            docker_config_backed_up=data.get("docker_config_backed_up", False),
            hooks_executed=data.get("hooks_executed", []),
            backup_format=data.get("backup_format", "direct"),
            error_details=error_details,
        )


@dataclass
class RestorePoint:
    unit_name: str
    timestamp: datetime
    backup_id: str  # REQUIRED
    recipe_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    volume_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    bind_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    database_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    network_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    docker_config_snapshots: List[Dict[str, Any]] = field(default_factory=list)
