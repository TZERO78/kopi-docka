################################################################################
# KOPI-DOCKA
#
# @file:        missed_backup_checker.py
# @module:      kopi_docka.cores
# @description: Zeit-basierte Erkennung und Alerting für ausgebliebene Backups.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2026 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Missed-backup detection using local metadata files.

Reads backup metadata written by BackupManager and compares the last
successful backup timestamp per unit against the configured threshold.
Alert suppression state is persisted in MISSED_BACKUP_STATE_FILE.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..helpers.config import Config
from ..helpers.constants import MISSED_BACKUP_MAX_AGE_HOURS, MISSED_BACKUP_STATE_FILE
from ..helpers.logging import get_logger
from ..helpers.metadata_reader import MetadataReader

logger = get_logger(__name__)


@dataclass
class MissedUnit:
    """A backup unit whose last successful backup exceeded its threshold."""

    name: str
    last_success_at: Optional[datetime]
    threshold_hours: int
    overdue_hours: float


class MissedBackupChecker:
    """Detects backup units that have not been backed up within their threshold.

    Uses MetadataReader to read local backup metadata. Alert suppression
    prevents repeat-spamming: once a unit is alerted, it is suppressed until
    a successful backup resets the state.
    """

    def __init__(self, config: Config, metadata_reader: MetadataReader):
        self.config = config
        self.reader = metadata_reader
        self._state_file = MISSED_BACKUP_STATE_FILE

    def _get_threshold_hours(self, unit_name: str) -> int:
        """Return the effective threshold for a unit (per-unit override > global)."""
        try:
            alerting = self.config._model.alerting
            per_unit = alerting.missed_backup.per_unit
            if unit_name in per_unit:
                return int(per_unit[unit_name])
            return int(alerting.missed_backup.max_age_hours)
        except Exception:
            return MISSED_BACKUP_MAX_AGE_HOURS

    def check_all_units(self) -> List[MissedUnit]:
        """Return units whose last successful backup exceeded their threshold."""
        try:
            alerting = self.config._model.alerting
            if not alerting.missed_backup.enabled:
                return []
        except Exception:
            pass

        now = datetime.now(tz=timezone.utc)
        unit_names = self.reader.get_unit_names()
        missed: List[MissedUnit] = []

        for name in unit_names:
            threshold = self._get_threshold_hours(name)
            entries = self.reader.read_all(unit_name=name)
            last_success = next((m for m in entries if m.success), None)

            if last_success is None:
                # Never backed up successfully → always overdue
                missed.append(
                    MissedUnit(
                        name=name,
                        last_success_at=None,
                        threshold_hours=threshold,
                        overdue_hours=float("inf"),
                    )
                )
                continue

            ts = last_success.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_hours = (now - ts).total_seconds() / 3600

            if age_hours > threshold:
                missed.append(
                    MissedUnit(
                        name=name,
                        last_success_at=ts,
                        threshold_hours=threshold,
                        overdue_hours=round(age_hours - threshold, 1),
                    )
                )

        return missed

    # ---- Alert suppression ----

    def _load_state(self) -> Dict[str, str]:
        """Load persisted alert-sent timestamps keyed by unit name."""
        try:
            if self._state_file.exists():
                return json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug("Could not load missed_state.json: %s", e)
        return {}

    def _save_state(self, state: Dict[str, str]) -> None:
        """Atomically persist alert state."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=self._state_file.parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)
                os.replace(tmp_path, self._state_file)
            except Exception:
                os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.debug("Could not save missed_state.json: %s", e)

    def get_units_to_alert(self, missed: List[MissedUnit]) -> List[MissedUnit]:
        """Filter to units that have not already been alerted in this overdue window."""
        state = self._load_state()
        to_alert = []
        for unit in missed:
            if unit.name not in state:
                to_alert.append(unit)
        return to_alert

    def mark_alerted(self, units: List[MissedUnit]) -> None:
        """Record that alerts have been sent for these units."""
        if not units:
            return
        state = self._load_state()
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        for unit in units:
            state[unit.name] = now_iso
        self._save_state(state)

    def reset_unit(self, unit_name: str) -> None:
        """Reset alert suppression for a unit (call after successful backup)."""
        state = self._load_state()
        if unit_name in state:
            del state[unit_name]
            self._save_state(state)
