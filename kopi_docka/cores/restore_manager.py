"""
Restore management module for Kopi-Docka.

Interactive restoration of Docker containers/volumes from Kopia snapshots.
(No database dump logic – cold backups restore via volumes.)
"""

import json
import subprocess
import tempfile
import re
from datetime import datetime
from pathlib import Path
from typing import List

from ..helpers.logging import get_logger
from ..types import RestorePoint
from ..helpers.config import Config
from ..cores.repository_manager import KopiaRepository
from ..helpers.constants import RECIPE_BACKUP_DIR, VOLUME_BACKUP_DIR, CONTAINER_START_TIMEOUT

logger = get_logger(__name__)


class RestoreManager:
    """Interactive restore wizard for cold backups (recipes + volumes)."""

    def __init__(self, config: Config):
        self.config = config
        self.repo = KopiaRepository(config)
        self.start_timeout = self.config.getint(
            "backup", "start_timeout", CONTAINER_START_TIMEOUT
        )

    def interactive_restore(self):
        """Run interactive wizard."""
        print("\n" + "=" * 60)
        print("🔄 Kopi-Docka Restore Wizard")
        print("=" * 60)

        logger.info("Starting interactive restore wizard")

        points = self._find_restore_points()
        if not points:
            print("\n❌ No backups found to restore.")
            logger.warning("No restore points found")
            return

        print("\n📋 Available restore points:\n")
        for idx, p in enumerate(points, 1):
            print(
                f"{idx}. 📦 {p.unit_name}  ({p.timestamp.strftime('%Y-%m-%d %H:%M:%S')})  "
                f"💾 Volumes: {len(p.volume_snapshots)}"
            )

        # selection
        while True:
            try:
                choice = input("\n🎯 Select restore point (number): ").strip()
                i = int(choice) - 1
                if 0 <= i < len(points):
                    sel = points[i]
                    break
                print("❌ Invalid selection. Please try again.")
            except (ValueError, KeyboardInterrupt):
                print("\n⚠️ Restore cancelled.")
                logger.info("Restore cancelled by user")
                return

        logger.info(
            f"Selected restore point: {sel.unit_name} from {sel.timestamp}",
            extra={"unit_name": sel.unit_name, "timestamp": sel.timestamp.isoformat()},
        )

        print(f"\n✅ Selected: {sel.unit_name} from {sel.timestamp}")
        print("\n📝 This will guide you through restoring:")
        print(f"  - Recipe/configuration files")
        print(f"  - {len(sel.volume_snapshots)} volumes")

        confirm = input("\n⚠️ Proceed with restore? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("❌ Restore cancelled.")
            logger.info("Restore cancelled at confirmation")
            return

        self._restore_unit(sel)

    def _find_restore_points(self) -> List[RestorePoint]:
        """Find available restore points grouped by unit + REQUIRED backup_id."""
        out: List[RestorePoint] = []
        try:
            snaps = self.repo.list_snapshots()
            groups = {}

            for s in snaps:
                tags = s.get("tags", {})
                unit = tags.get("unit")
                backup_id = tags.get("backup_id")  # REQUIRED
                ts_str = tags.get("timestamp")
                snap_type = tags.get("type", "")  # ← Type aus Tags holen

                if not unit or not backup_id:
                    continue  # enforce backup_id

                try:
                    ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now()
                except ValueError:
                    ts = datetime.now()

                key = f"{unit}:{backup_id}"
                if key not in groups:
                    groups[key] = RestorePoint(
                        unit_name=unit,
                        timestamp=ts,
                        backup_id=backup_id,
                        recipe_snapshots=[],
                        volume_snapshots=[],
                        database_snapshots=[],  # kept empty for type-compat
                    )

                # Nutze Type aus Tags statt path
                if snap_type == "recipe":
                    groups[key].recipe_snapshots.append(s)
                elif snap_type == "volume":
                    groups[key].volume_snapshots.append(s)

            out = list(groups.values())
            out.sort(key=lambda x: x.timestamp, reverse=True)
            logger.debug(f"Found {len(out)} restore points")
        except Exception as e:
            logger.error(f"Failed to find restore points: {e}")

        return out

    def _restore_unit(self, rp: RestorePoint):
        """Restore a selected backup unit."""
        print("\n" + "-" * 60)
        print("🚀 Starting restoration process...")
        print("-" * 60)

        logger.info(
            f"Starting restore for unit: {rp.unit_name}",
            extra={"unit_name": rp.unit_name},
        )

        safe_unit = re.sub(r"[^A-Za-z0-9._-]+", "_", rp.unit_name)
        restore_dir = Path(tempfile.mkdtemp(prefix=f"kopia-docka-restore-{safe_unit}-"))
        print(f"\n📂 Restore directory: {restore_dir}")

        try:
            # 1) Recipes
            print("\n1️⃣ Restoring recipes...")
            recipe_dir = self._restore_recipe(rp, restore_dir)

            # 2) Volume instructions
            if rp.volume_snapshots:
                print("\n2️⃣ Volume restoration:")
                self._display_volume_restore_instructions(rp, restore_dir)

            # 3) Restart instructions (only modern docker compose)
            print("\n3️⃣ Service restart instructions:")
            self._display_restart_instructions(recipe_dir)

            print("\n" + "=" * 60)
            print("✅ Restoration guide complete!")
            print("📋 Follow the instructions above to restore your service.")
            print("=" * 60)

            logger.info(
                f"Restore guide completed for {rp.unit_name}",
                extra={"unit_name": rp.unit_name, "restore_dir": str(restore_dir)},
            )

        except Exception as e:
            logger.error(f"Restore failed: {e}", extra={"unit_name": rp.unit_name})
            print(f"\n❌ Error during restore: {e}")

    def _restore_recipe(self, rp: RestorePoint, restore_dir: Path) -> Path:
        """Restore recipe snapshots into a folder."""
        if not rp.recipe_snapshots:
            logger.warning(
                "No recipe snapshots found", extra={"unit_name": rp.unit_name}
            )
            return restore_dir

        recipe_dir = restore_dir / "recipes"
        recipe_dir.mkdir(parents=True, exist_ok=True)

        for snap in rp.recipe_snapshots:
            try:
                snapshot_id = snap["id"]
                print(f"   📥 Restoring recipe snapshot: {snapshot_id[:12]}...")

                # Direkt mit kopia restore (einfacher als mount)
                self.repo.restore_snapshot(snapshot_id, str(recipe_dir))

                print(f"   ✅ Recipe files restored to: {recipe_dir}")
                self._check_for_secrets(recipe_dir)

                logger.info(
                    "Recipes restored",
                    extra={"unit_name": rp.unit_name, "recipe_dir": str(recipe_dir)},
                )

            except Exception as e:
                logger.error(
                    f"Failed to restore recipe snapshot: {e}",
                    extra={"unit_name": rp.unit_name},
                )
                print(f"   ⚠️ Warning: Could not restore recipe: {e}")

        return recipe_dir

    def _check_for_secrets(self, recipe_dir: Path):
        """Warn if redacted secrets are present in inspect JSONs."""
        for f in recipe_dir.glob("*_inspect.json"):
            try:
                content = f.read_text()
                if "***REDACTED***" in content:
                    print(f"   ⚠ Note: {f.name} contains redacted secrets")
                    print("     Restore actual values manually if needed.")
                    logger.info(
                        "Found redacted secrets in restore", extra={"file": f.name}
                    )
            except Exception:
                pass

    def _display_volume_restore_instructions(self, rp: RestorePoint, restore_dir: Path):
        """Print safe commands for restoring each volume."""
        print("\n   📦 Volume Restore Commands:")
        print("   " + "-" * 40)

        # Config-File Path dynamisch aus repo holen
        config_file = self.repo._get_config_file()

        for snap in rp.volume_snapshots:
            tags = snap.get("tags", {})
            vol = tags.get("volume", "unknown")
            snap_id = snap["id"]

            print(f"\n   Volume: {vol}")
            print(f"   Snapshot: {snap_id[:12]}...")
            print("\n   Commands:")
            print(
                f"""
    VOLUME_NAME="{vol}"
    SNAP_ID="{snap_id}"
    CONFIG_FILE="{config_file}"

    # 1. Stop containers using this volume
    echo "Stopping containers using volume $VOLUME_NAME..."
    docker ps -q --filter "volume=$VOLUME_NAME" | xargs -r docker stop

    # 2. Safety backup of current volume
    echo "Creating safety backup..."
    docker run --rm -v "$VOLUME_NAME":/src -v /tmp:/backup alpine \\
        sh -c 'tar -czf /backup/$VOLUME_NAME-backup-$(date +%Y%m%d-%H%M%S).tar.gz -C /src .'

    # 3. Restore from Kopia (stream into volume; keep ACLs/xattrs)
    echo "Restoring volume from backup..."
    kopia snapshot restore "$SNAP_ID" --config-file "$CONFIG_FILE" - | \\
        docker run --rm -i -v "$VOLUME_NAME":/target debian:bookworm-slim \\
        bash -c 'set -euo pipefail; rm -rf /target/*; tar -xpf - --numeric-owner --xattrs --acls -C /target'

    # 4. Restart containers
    echo "Restarting containers..."
    docker ps -a -q --filter "volume=$VOLUME_NAME" | xargs -r docker start

    echo "Volume $VOLUME_NAME restored successfully!"
    """
            )

    def _display_restart_instructions(self, recipe_dir: Path):
        """Show modern docker compose restart steps (no legacy fallback)."""
        compose_file = recipe_dir / "docker-compose.yml"
        print("\n   🐳 Service Restart:")
        print("   " + "-" * 40)
        if compose_file.exists():
            print(f"   cd {recipe_dir}")
            print(f"   docker compose up -d  # ensure volumes are restored BEFORE this")
        else:
            print(f"   Review the inspect files in: {recipe_dir}")
            print(f"   Recreate containers with appropriate 'docker run' options")