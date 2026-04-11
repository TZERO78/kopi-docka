################################################################################
# KOPI-DOCKA
#
# @file:        backup_volume_handler.py
# @module:      kopi_docka.cores
# @description: Volume backup handler — direct Kopia snapshots and TAR streams.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################
"""Volume backup handler for Kopi-Docka.

Handles volume backups via direct Kopia snapshots (v5.0+) or legacy TAR streams.
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..helpers.logging import get_logger
from ..types import VolumeInfo, BackupUnit
from ..helpers.constants import (
    VOLUME_BACKUP_DIR,
    BACKUP_FORMAT_TAR,
    BACKUP_FORMAT_DIRECT,
    BACKUP_FORMAT_DEFAULT,
)

logger = get_logger(__name__)


class BackupVolumeHandler:
    """Handles volume backups via direct Kopia snapshots or TAR streams."""

    def __init__(self, repo, exclude_patterns: list):
        self.repo = repo
        self.exclude_patterns = exclude_patterns

    def backup_volume(
        self, volume: VolumeInfo, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> Optional[str]:
        """Backup a single volume using the configured backup format.

        Dispatcher that routes to the appropriate backup method based on
        BACKUP_FORMAT_DEFAULT setting.

        Args:
            volume: Volume to backup
            unit: Parent backup unit
            backup_id: Unique ID for this backup run
            backup_scope: Backup scope (minimal/standard/full)

        Returns:
            Snapshot ID if successful, None otherwise
        """
        backup_format = BACKUP_FORMAT_DEFAULT

        if backup_format == BACKUP_FORMAT_DIRECT:
            return self.backup_volume_direct(volume, unit, backup_id, backup_scope)
        else:
            return self.backup_volume_tar(volume, unit, backup_id, backup_scope)

    def backup_volume_direct(
        self, volume: VolumeInfo, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> Optional[str]:
        """Backup a single volume via direct Kopia snapshot (v5.0+).

        This method creates a direct Kopia snapshot of the volume directory,
        enabling block-level deduplication. Only changed blocks are stored
        in subsequent backups.

        Args:
            volume: Volume to backup
            unit: Parent backup unit
            backup_id: Unique ID for this backup run
            backup_scope: Backup scope (minimal/standard/full)

        Returns:
            Snapshot ID if successful, None otherwise
        """
        try:
            volume_path = Path(volume.mountpoint)

            # Verify volume path exists and is accessible
            if not volume_path.exists():
                logger.error(
                    f"Volume path does not exist: {volume_path}",
                    extra={"unit_name": unit.name, "volume": volume.name},
                )
                return None

            if not volume_path.is_dir():
                logger.error(
                    f"Volume path is not a directory: {volume_path}",
                    extra={"unit_name": unit.name, "volume": volume.name},
                )
                return None

            logger.debug(
                f"Backing up volume (direct): {volume.name}",
                extra={
                    "unit_name": unit.name,
                    "volume": volume.name,
                    "path": str(volume_path),
                    "size_bytes": getattr(volume, "size_bytes", 0),
                    "backup_format": BACKUP_FORMAT_DIRECT,
                },
            )

            # Create direct Kopia snapshot of volume directory
            # Pass exclude patterns from config (same as TAR mode)
            snap_id = self.repo.create_snapshot(
                str(volume_path),
                tags={
                    "type": "volume",
                    "unit": unit.name,
                    "volume": volume.name,
                    "backup_id": backup_id,
                    "backup_scope": backup_scope,
                    "timestamp": datetime.now().isoformat(),
                    "size_bytes": str(getattr(volume, "size_bytes", 0) or "0"),
                    "backup_format": BACKUP_FORMAT_DIRECT,
                },
                exclude_patterns=self.exclude_patterns if self.exclude_patterns else None,
            )

            logger.debug(
                f"Created direct snapshot for volume: {volume.name}",
                extra={
                    "unit_name": unit.name,
                    "volume": volume.name,
                    "snapshot_id": snap_id,
                },
            )

            return snap_id

        except Exception as e:
            logger.error(
                f"Failed to backup volume {volume.name} (direct): {e}",
                extra={"unit_name": unit.name, "volume": volume.name},
            )
            return None

    def backup_volume_tar(
        self, volume: VolumeInfo, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> Optional[str]:
        """Backup a single volume via tar stream → Kopia (legacy).

        DEPRECATED: This method uses tar streams which prevent Kopia's
        block-level deduplication. Use backup_volume_direct() instead.

        Note: stderr is written to a temporary file instead of a pipe to prevent
        deadlock when tar produces large amounts of warnings (e.g., "file changed
        as we read it" on thousands of files). The OS pipe buffer (typically 64KB)
        would fill up, causing tar to block while Python waits for tar to finish.
        """
        import tempfile

        try:
            logger.debug(
                f"Backing up volume (tar): {volume.name}",
                extra={
                    "unit_name": unit.name,
                    "volume": volume.name,
                    "size_bytes": getattr(volume, "size_bytes", 0),
                    "backup_format": BACKUP_FORMAT_TAR,
                },
            )

            tar_cmd = [
                "tar",
                "-cf",
                "-",
                "--numeric-owner",
                "--xattrs",
                "--acls",
                "--one-file-system",
                "--mtime=@0",
                "--clamp-mtime",
                "--sort=name",
            ]
            for pattern in self.exclude_patterns:
                tar_cmd.extend(["--exclude", pattern])
            tar_cmd.extend(["-C", volume.mountpoint, "."])

            # Use a temporary file for stderr to avoid deadlock.
            # If tar produces >64KB of warnings, a pipe would fill up and block.
            with tempfile.TemporaryFile(mode="w+b") as stderr_file:
                tar_process = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=stderr_file)

                try:
                    snap_id = self.repo.create_snapshot_from_stdin(
                        tar_process.stdout,
                        dest_virtual_path=f"{VOLUME_BACKUP_DIR}/{unit.name}/{volume.name}",
                        tags={
                            "type": "volume",
                            "unit": unit.name,
                            "volume": volume.name,
                            "backup_id": backup_id,
                            "backup_scope": backup_scope,
                            "timestamp": datetime.now().isoformat(),
                            "size_bytes": str(getattr(volume, "size_bytes", 0) or "0"),
                            "backup_format": BACKUP_FORMAT_TAR,
                        },
                    )
                except Exception:
                    tar_process.kill()
                    tar_process.wait()
                    raise

                tar_process.wait()
                if tar_process.stdout:
                    tar_process.stdout.close()

                if tar_process.returncode != 0:
                    # Read stderr from temp file (seek to beginning first)
                    stderr_file.seek(0)
                    stderr_content = stderr_file.read().decode(errors="replace")
                    # Truncate very long error output for logging
                    if len(stderr_content) > 4096:
                        stderr_content = stderr_content[:4096] + "\n... (truncated)"
                    logger.error(
                        f"Tar failed for volume {volume.name}: {stderr_content}",
                        extra={"unit_name": unit.name, "volume": volume.name},
                    )
                    return None

            return snap_id
        except Exception as e:
            logger.error(
                f"Failed to backup volume {volume.name} (tar): {e}",
                extra={"unit_name": unit.name, "volume": volume.name},
            )
            return None
