################################################################################
# KOPI-DOCKA
#
# @file:        metadata_reader.py
# @module:      kopi_docka.helpers
# @description: Read-only loader for backup metadata JSON files.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Backup metadata reader — loads and filters metadata JSONs from disk.

Think Simple: read files, parse, sort. No cache, no DB.
Reused by: history command (Plan 0021), stale-detection (Plan 0022).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .logging import get_logger
from ..types import BackupMetadata

logger = get_logger(__name__)


class MetadataReader:
    """Reads backup metadata JSONs from the metadata directory.

    Think Simple: read files, parse, sort. No cache, no DB.
    """

    def __init__(self, metadata_dir: Path):
        self.metadata_dir = metadata_dir

    def read_all(
        self,
        unit_name: Optional[str] = None,
        only_failed: bool = False,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[BackupMetadata]:
        """Load all metadata, filter, sorted by timestamp (newest first)."""
        if not self.metadata_dir.is_dir():
            return []

        entries: List[BackupMetadata] = []
        for path in self.metadata_dir.glob("*.json"):
            meta = self._load_file(path)
            if meta is not None:
                entries.append(meta)

        # Sort newest first
        entries.sort(key=lambda m: m.timestamp, reverse=True)

        # Apply filters
        if unit_name is not None:
            entries = [m for m in entries if m.unit_name == unit_name]
        if only_failed:
            entries = [m for m in entries if not m.success]
        if since is not None:
            entries = [m for m in entries if m.timestamp >= since]
        if limit is not None:
            entries = entries[:limit]

        return entries

    def read_latest(self, unit_name: Optional[str] = None) -> Optional[BackupMetadata]:
        """Most recent backup (optionally for a specific unit)."""
        results = self.read_all(unit_name=unit_name, limit=1)
        return results[0] if results else None

    def get_unit_names(self) -> List[str]:
        """All known unit names from metadata files."""
        entries = self.read_all()
        names = sorted({m.unit_name for m in entries})
        return names

    def _load_file(self, path: Path) -> Optional[BackupMetadata]:
        """Load a single metadata JSON file. Returns None on error."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return BackupMetadata.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.warning(f"Skipping corrupt metadata file {path.name}: {e}")
            return None
        except OSError as e:
            logger.warning(f"Cannot read metadata file {path.name}: {e}")
            return None
