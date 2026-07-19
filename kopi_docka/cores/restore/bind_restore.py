################################################################################
# KOPI-DOCKA
#
# @file:        bind_restore.py
# @module:      kopi_docka.cores.restore
# @description: Restores persistent bind-mount snapshots back to their host path.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Bind mounts are host-directory mappings (e.g. ./vw-data:/data). Their host
#   source path is stored in the snapshot tag ``bind_source``; restore writes the
#   snapshot content back to exactly that path.
# - A backup that captures bind data (incl. secrets) is only useful if it can be
#   restored — this engine is the restore half of Plan 0040 / issue #129.
# - Role module: first slice of the restore_manager decomposition (Plan 0033).
################################################################################
"""Bind-mount restore engine for Kopi-Docka."""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...helpers.logging import get_logger
from ...helpers.ui_utils import run_command, SubprocessError

logger = get_logger(__name__)


class BindRestoreEngine:
    """Restores persistent bind-mount snapshots to their original host path.

    Kept deliberately decoupled from ``RestoreManager``: it only needs a
    ``KopiaRepository`` (to pull the snapshot through ``restore_snapshot`` — no
    direct ``subprocess``→kopia call, per the architecture rule) and a couple of
    UI flags. The wizard calls :meth:`restore_all` after volumes.
    """

    def __init__(self, repo, non_interactive: bool = False):
        self.repo = repo
        self.non_interactive = non_interactive

    # ---------------------------------------------------------------- public

    def restore_all(
        self,
        bind_snapshots: List[Dict[str, Any]],
        unit_name: str,
        data_safety_handler=None,
    ) -> int:
        """Restore every bind snapshot in ``bind_snapshots``.

        Returns the number of bind mounts successfully restored.
        """
        if not bind_snapshots:
            return 0

        print("\n   🔗 Bind-mount restoration:")
        print("   " + "-" * 40)
        print(
            "   ⚠️  Make sure the containers/stack using these host paths are"
            " stopped before restoring."
        )

        restored = 0
        for snap in bind_snapshots:
            if self._restore_one(snap, unit_name, data_safety_handler):
                restored += 1
        return restored

    # --------------------------------------------------------------- helpers

    def _restore_one(self, snap: Dict[str, Any], unit_name: str, data_safety_handler) -> bool:
        tags = snap.get("tags", {}) or {}
        source = tags.get("bind_source")
        destination = tags.get("bind_destination", "")
        snap_id = snap.get("id")

        if not source or not snap_id:
            logger.warning(
                "Skipping bind snapshot without bind_source/id tag",
                extra={"unit_name": unit_name},
            )
            print("   ⚠️  Skipping a bind snapshot with missing metadata.")
            return False

        ro = tags.get("read_only") == "true"
        print(f"\n   📁 Bind mount: {source}" + (f"  →  {destination}" if destination else ""))
        print(f"   📸 Snapshot: {snap_id[:12]}..." + ("  (read-only mount)" if ro else ""))

        if self.non_interactive:
            print(f"   ✓ Auto-restoring '{source}' (--yes mode)")
        else:
            choice = input(f"\n   ⚠️  Restore '{source}' NOW? (yes/no/q): ").strip().lower()
            if choice == "q":
                print("   ⚠️ Bind restore cancelled.")
                return False
            if choice not in ("yes", "y"):
                self._print_manual_instructions(source, snap_id)
                return False

        return self._execute(source, snap_id, unit_name, data_safety_handler)

    def _execute(self, source: str, snap_id: str, unit_name: str, data_safety_handler) -> bool:
        source_path = Path(source)
        restore_dir = Path(tempfile.mkdtemp(prefix="kopia-docka-bind-restore-"))
        if data_safety_handler:
            data_safety_handler.register_temp_dir(str(restore_dir))

        try:
            # 1) Safety backup of existing host content (best effort)
            self._safety_backup(source_path)

            # 2) Restore snapshot into a temp dir (through KopiaRepository)
            print("   📥 Restoring from Kopia...")
            self.repo.restore_snapshot(snap_id, str(restore_dir))
            file_count = sum(1 for p in restore_dir.rglob("*") if p.is_file())
            print(f"      ✓ Restored {file_count} file(s) to staging")

            # 3) Ensure the host path exists, then sync content into place
            source_path.mkdir(parents=True, exist_ok=True)
            self._sync_into_place(restore_dir, source_path)
            print(f"      ✓ Bind data restored to {source}")

            logger.info(
                "Bind mount restored",
                extra={"unit_name": unit_name, "bind_source": source},
            )
            return True

        except SubprocessError as e:
            print(f"      ❌ Command failed: {e}")
            logger.error(f"Bind restore failed for {source}: {e}", extra={"unit_name": unit_name})
            return False
        except Exception as e:
            print(f"      ❌ Unexpected error: {e}")
            logger.error(f"Bind restore error for {source}: {e}", extra={"unit_name": unit_name})
            return False
        finally:
            try:
                if restore_dir.exists():
                    shutil.rmtree(restore_dir)
            except Exception as cleanup_error:
                logger.warning(f"Could not clean up {restore_dir}: {cleanup_error}")

    def _safety_backup(self, source_path: Path) -> Optional[Path]:
        """Tar the current host content before overwriting it (best effort)."""
        if not source_path.exists() or not any(source_path.iterdir()):
            print("      ℹ No existing data to back up (path empty or new)")
            return None

        safe_name = str(source_path).strip("/").replace("/", "_") or "root"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_dir = Path(tempfile.mkdtemp(prefix="kopia-docka-bind-safety-"))
        backup_path = backup_dir / f"{safe_name}-{stamp}.tar.gz"

        print("   🛟 Creating safety backup of current content...")
        result = run_command(
            ["tar", "-czf", str(backup_path), "-C", str(source_path), "."],
            "Creating bind safety backup",
            timeout=300,
            check=False,
        )
        if result.returncode == 0 and backup_path.exists():
            print(f"      ✓ Safety backup: {backup_path}")
            return backup_path
        print("      ⚠ Could not create safety backup (continuing)")
        return None

    def _sync_into_place(self, restore_dir: Path, source_path: Path) -> None:
        """rsync restored content into the host path, cp -a as fallback."""
        result = run_command(
            ["rsync", "-a", "--delete", "--numeric-ids",
             f"{restore_dir}/", f"{source_path}/"],
            "Syncing bind data into place",
            timeout=600,
            check=False,
        )
        if result.returncode == 0:
            return

        logger.warning("rsync failed for bind restore, falling back to cp")
        for entry in source_path.iterdir():
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
        run_command(
            ["cp", "-a", f"{restore_dir}/.", f"{source_path}/"],
            "Copying bind data into place",
            timeout=600,
        )

    def _print_manual_instructions(self, source: str, snap_id: str) -> None:
        config_file = self.repo._get_config_file()
        print("\n   📋 Manual restore later:")
        print("   RESTORE_DIR=$(mktemp -d)")
        print(f"   kopia snapshot restore {snap_id} --config-file {config_file} $RESTORE_DIR")
        print(f"   rsync -a --delete --numeric-ids $RESTORE_DIR/ {source}/")
        print("   rm -rf $RESTORE_DIR\n")
