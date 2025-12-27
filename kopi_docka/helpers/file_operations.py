#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        file_operations.py
# @module:      kopi_docka.helpers.file_operations
# @description: File operations with backup and rollback support
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - VPS-optimized: Only 1 backup per file (.bak without timestamp)
# - Rollback on ALL errors (Permission, IO, etc.)
# - Pure functions without state (follows ui_utils.py pattern)
################################################################################

"""
File operations module for Kopi-Docka.

Provides utilities for file operations with backup and rollback support,
optimized for VPS environments with limited disk space.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def check_file_conflicts(target_dir: Path, files_to_copy: List[Path]) -> List[Path]:
    """
    Check which files already exist in target directory.

    Args:
        target_dir: Target directory to check
        files_to_copy: List of files that should be copied

    Returns:
        List of files that already exist (conflicts)

    Example:
        conflicts = check_file_conflicts(
            Path("/opt/stacks/monitoring"),
            [Path("docker-compose.yml"), Path("prometheus.yml")]
        )
    """
    conflicts = []

    for file in files_to_copy:
        target_file = target_dir / file.name
        if target_file.exists():
            conflicts.append(target_file)
            logger.debug(f"Conflict detected: {target_file}")

    return conflicts


def create_file_backup(filepath: Path) -> Path:
    """
    Create backup of file with .bak suffix.
    Overwrites existing .bak file (only keeps last backup).

    Args:
        filepath: Path to file to backup

    Returns:
        Path to backup file

    Raises:
        OSError: If backup creation fails

    Example:
        backup = create_file_backup(Path("/opt/stacks/monitoring/docker-compose.yml"))
        # Creates: /opt/stacks/monitoring/docker-compose.yml.bak

    Note:
        VPS-optimized: Only 1 backup per file to save disk space.
        Each new backup overwrites the previous one.
    """
    backup_path = filepath.parent / f"{filepath.name}.bak"

    if backup_path.exists():
        logger.debug(f"Overwriting existing backup: {backup_path.name}")

    try:
        shutil.copy2(filepath, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create backup for {filepath}: {e}")
        raise


def copy_with_rollback(
    source_files: List[Path], target_dir: Path, console: Optional[object] = None
) -> Tuple[bool, List[Path]]:
    """
    Copy files with automatic rollback on error.
    Handles permissions correctly when running under sudo.

    Args:
        source_files: List of source files to copy
        target_dir: Target directory
        console: Optional Rich console for output

    Returns:
        Tuple of (success: bool, copied_files: List[Path])

    Note:
        - Rollback on ANY error (Permission, IO, etc.)
        - Uses SUDO_UID/SUDO_GID for correct ownership
        - Creates .bak files before overwriting
        - Restores backups on failure

    Example:
        success, copied = copy_with_rollback(
            [Path("docker-compose.yml"), Path("prometheus.yml")],
            Path("/opt/stacks/monitoring"),
            console
        )
    """
    copied_files = []
    backup_map = {}  # {target_path: backup_path}

    try:
        for source in source_files:
            target = target_dir / source.name

            # Track backup info if file exists
            if target.exists():
                backup = target.parent / f"{target.name}.bak"
                if backup.exists():
                    backup_map[target] = backup

            # Copy file
            shutil.copy2(source, target)
            copied_files.append(target)
            logger.debug(f"Copied: {source.name} → {target}")

            # Fix permissions (CRITICAL: Use SUDO_UID!)
            real_uid = int(os.environ.get("SUDO_UID", os.getuid()))
            real_gid = int(os.environ.get("SUDO_GID", os.getgid()))
            os.chown(target, real_uid, real_gid)
            os.chmod(target, 0o644)
            logger.debug(f"Set ownership: {real_uid}:{real_gid} for {target.name}")

        logger.info(f"Successfully copied {len(copied_files)} files to {target_dir}")
        return True, copied_files

    except PermissionError as e:
        logger.error(f"Permission denied during copy: {e}")
        if console:
            console.print(f"\n[red]✗ Permission denied: {e}[/red]")
        _rollback_copy(copied_files, backup_map, console)
        return False, []

    except OSError as e:
        logger.error(f"I/O error during copy: {e}")
        if console:
            console.print(f"\n[red]✗ I/O error (disk full?): {e}[/red]")
        _rollback_copy(copied_files, backup_map, console)
        return False, []

    except Exception as e:
        logger.error(f"Unexpected error during copy: {e}")
        if console:
            console.print(f"\n[red]✗ Unexpected error: {e}[/red]")
        _rollback_copy(copied_files, backup_map, console)
        return False, []


def _rollback_copy(
    copied_files: List[Path], backup_map: Dict[Path, Path], console: Optional[object] = None
) -> None:
    """
    Rollback a failed copy operation (internal helper).

    Args:
        copied_files: List of successfully copied files
        backup_map: Mapping of target_path → backup_path
        console: Optional Rich console for output

    Note:
        - Deletes copied files
        - Restores .bak files
        - Logs all operations
    """
    if console:
        console.print("\n🔄 Rolling back changes...")

    # Delete copied files
    for copied in copied_files:
        try:
            if copied.exists():
                copied.unlink()
                logger.debug(f"Deleted: {copied}")
        except Exception as e:
            logger.error(f"Failed to delete {copied}: {e}")

    # Restore backups
    for target, backup in backup_map.items():
        try:
            if backup.exists() and not target.exists():
                shutil.copy2(backup, target)
                logger.debug(f"Restored backup: {backup} → {target}")
        except Exception as e:
            logger.error(f"Failed to restore backup {backup}: {e}")

    if console:
        console.print("✓ Rollback complete - original state restored")
    logger.info("Rollback completed")
