#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        restore_manager.py
# @module:      kopi_docka.cores.restore_manager
# @description: Interactive restore wizard for cold backups with dependency checks.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------ 
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Changelog v2.0.0:
# - Added dependency checks (Docker, tar, Kopia) before restore
# - Time-based session grouping (5 min tolerance)
# - Interactive volume restore (yes/no/q options)
# - Direct Python execution instead of bash scripts
# - Quit option ('q') at all input prompts
# - Guaranteed cleanup with context managers
# - Clear manual restore instructions when user declines
################################################################################

"""
Restore management module for Kopi-Docka.

Interactive restoration of Docker containers/volumes from Kopia snapshots.
Uses cold backup strategy: restore recipes and volumes directly.
"""

import json
import subprocess
import tempfile
import shutil
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from contextlib import contextmanager

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

        # Check dependencies FIRST
        from ..cores.dependency_manager import DependencyManager
        
        deps = DependencyManager()
        missing = []
        
        if not deps.check_docker():
            missing.append("Docker")
        if not deps.check_tar():
            missing.append("tar")
        if not deps.check_kopia():
            missing.append("Kopia")
        
        if missing:
            print("\n❌ Missing required dependencies:")
            for dep in missing:
                print(f"   • {dep}")
            print("\nPlease install missing dependencies:")
            print("   kopi-docka install-deps")
            print("\nOr check manually:")
            if "Docker" in missing:
                print("   docker --version")
                print("   systemctl status docker")
            if "tar" in missing:
                print("   which tar")
            if "Kopia" in missing:
                print("   kopia --version")
            logger.error(f"Restore aborted: missing dependencies {missing}")
            return

        # Check if Kopia repository is connected
        if not self.repo.is_connected():
            print("\n❌ Not connected to Kopia repository")
            print("\nPlease connect first:")
            print("   kopi-docka init")
            logger.error("Restore aborted: repository not connected")
            return

        print("\n✓ Dependencies OK")
        print("✓ Repository connected")
        print("")

        points = self._find_restore_points()
        if not points:
            print("\n❌ No backups found to restore.")
            logger.warning("No restore points found")
            return

        # Sortiere alle Points nach Zeit (neueste zuerst)
        sorted_points = sorted(points, key=lambda x: x.timestamp, reverse=True)

        # Gruppiere nach Zeitfenstern (5 Min Toleranz)
        sessions = []
        current_session = None
        
        for p in sorted_points:
            if current_session is None:
                # Erste Session starten
                current_session = {
                    'timestamp': p.timestamp,
                    'units': [p]
                }
            else:
                # Check ob innerhalb 5 Min vom neuesten in aktueller Session
                time_diff = current_session['timestamp'] - p.timestamp
                if time_diff <= timedelta(minutes=5):
                    # Gehört zur aktuellen Session
                    current_session['units'].append(p)
                else:
                    # Neue Session starten
                    sessions.append(current_session)
                    current_session = {
                        'timestamp': p.timestamp,
                        'units': [p]
                    }
        
        # Letzte Session hinzufügen
        if current_session:
            sessions.append(current_session)

        print("\n📋 Available backup sessions:\n")
        for idx, session in enumerate(sessions, 1):
            ts = session['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            units = session['units']
            
            # Zeitspanne der Session
            if len(units) > 1:
                oldest = min(u.timestamp for u in units)
                newest = max(u.timestamp for u in units)
                duration = (newest - oldest).total_seconds()
                time_range = f" (span: {int(duration/60)}min)" if duration > 60 else ""
            else:
                time_range = ""
            
            unit_names = ', '.join([u.unit_name for u in units])
            total_volumes = sum(len(u.volume_snapshots) for u in units)
            
            print(f"{idx}. 📅 {ts}{time_range}")
            print(f"   Units: {unit_names}")
            print(f"   Total volumes: {total_volumes}\n")

        # Session wählen
        while True:
            try:
                choice = input("🎯 Select backup session (number, or 'q' to quit): ").strip().lower()
                
                if choice == 'q':
                    print("\n⚠️ Restore cancelled.")
                    logger.info("Restore cancelled by user (quit)")
                    return
                
                session_idx = int(choice) - 1
                if 0 <= session_idx < len(sessions):
                    break
                print("❌ Invalid selection. Please try again.")
            except ValueError:
                print("❌ Please enter a number or 'q' to quit.")
            except KeyboardInterrupt:
                print("\n⚠️ Restore cancelled.")
                logger.info("Restore cancelled by user (interrupt)")
                return

        selected_session = sessions[session_idx]
        units = selected_session['units']

        # Wenn nur 1 Unit in Session → direkt nehmen
        if len(units) == 1:
            sel = units[0]
        else:
            # Mehrere Units → User wählen lassen
            print("\n📦 Units in this backup session:\n")
            for idx, u in enumerate(units, 1):
                ts = u.timestamp.strftime('%H:%M:%S')
                print(f"{idx}. {u.unit_name} ({len(u.volume_snapshots)} volumes) - {ts}")
            
            while True:
                try:
                    choice = input("\n🎯 Select unit to restore (number, or 'q' to quit): ").strip().lower()
                    
                    if choice == 'q':
                        print("\n⚠️ Restore cancelled.")
                        logger.info("Restore cancelled by user (quit)")
                        return
                    
                    unit_idx = int(choice) - 1
                    if 0 <= unit_idx < len(units):
                        sel = units[unit_idx]
                        break
                    print("❌ Invalid selection. Please try again.")
                except ValueError:
                    print("❌ Please enter a number or 'q' to quit.")
                except KeyboardInterrupt:
                    print("\n⚠️ Restore cancelled.")
                    logger.info("Restore cancelled by user (interrupt)")
                    return

        logger.info(
            f"Selected restore point: {sel.unit_name} from {sel.timestamp}",
            extra={"unit_name": sel.unit_name, "timestamp": sel.timestamp.isoformat()},
        )

        print(f"\n✅ Selected: {sel.unit_name} from {sel.timestamp}")
        print("\n📝 This will guide you through restoring:")
        print(f"  - Recipe/configuration files")
        print(f"  - {len(sel.volume_snapshots)} volumes")

        confirm = input("\n⚠️ Proceed with restore? (yes/no/q): ").strip().lower()
        if confirm not in ('yes', 'y'):
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
                snap_type = tags.get("type", "")

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
        """Interactive volume restore: execute now or show instructions."""
        print("\n   📦 Volume Restoration:")
        print("   " + "-" * 40)

        config_file = self.repo._get_config_file()

        for snap in rp.volume_snapshots:
            tags = snap.get("tags", {})
            vol = tags.get("volume", "unknown")
            unit = tags.get("unit", "unknown")  # ← UNIT auch holen!
            snap_id = snap["id"]

            print(f"\n   📁 Volume: {vol}")
            print(f"   📸 Snapshot: {snap_id[:12]}...")

            # User fragen
            choice = input(f"\n   ⚠️  Restore '{vol}' NOW? (yes/no/q): ").strip().lower()

            if choice == 'q':
                print("\n   ⚠️ Restore cancelled.")
                logger.info("Volume restore cancelled by user")
                return
            
            elif choice in ('yes', 'y'):
                # Python führt direkt aus - MIT UNIT!
                print(f"\n   🚀 Restoring volume '{vol}'...")
                print("   " + "=" * 50)
                
                try:
                    success = self._execute_volume_restore(vol, unit, snap_id, config_file)  # ← UNIT übergeben!
                    
                    if success:
                        print("   " + "=" * 50)
                        print(f"   ✅ Volume '{vol}' restored successfully!\n")
                        logger.info(f"Volume {vol} restored", extra={"volume": vol})
                    else:
                        print("   " + "=" * 50)
                        print(f"   ❌ Restore failed for '{vol}'\n")
                        logger.error(f"Volume restore failed for {vol}")
                        
                except Exception as e:
                    print(f"   ❌ Error: {e}\n")
                    logger.error(f"Volume restore error: {e}", extra={"volume": vol})

            else:
                # Handlungsempfehlung
                print(f"\n   📋 Manual Restore Instructions:")
                print(f"   " + "-" * 50)
                print(f"")
                print(f"   To restore this volume later, run these commands:")
                print(f"")
                print(f"   # 1. Stop containers")
                print(f"   docker ps -q --filter 'volume={vol}' | xargs -r docker stop")
                print(f"")
                print(f"   # 2. Safety backup")
                print(f"   docker run --rm -v {vol}:/src -v /tmp:/backup alpine \\")
                print(f"     sh -c 'tar -czf /backup/{vol}-backup-$(date +%Y%m%d-%H%M%S).tar.gz -C /src .'")
                print(f"")
                print(f"   # 3. Restore from Kopia")
                print(f"   RESTORE_DIR=$(mktemp -d)")
                print(f"   kopia snapshot restore {snap_id} --config-file {config_file} $RESTORE_DIR")
                print(f"   TAR_FILE=$(find $RESTORE_DIR -name '{vol}' -type f)")
                print(f"")
                print(f"   # 4. Extract into volume")
                print(f"   docker run --rm -v {vol}:/target -v $TAR_FILE:/backup.tar:ro debian:bookworm-slim \\")
                print(f"     bash -c 'rm -rf /target/* /target/..?* /target/.[!.]* 2>/dev/null || true; \\")
                print(f"              tar -xpf /backup.tar --numeric-owner --xattrs --acls -C /target'")
                print(f"")
                print(f"   # 5. Cleanup and restart")
                print(f"   rm -rf $RESTORE_DIR")
                print(f"   docker ps -a -q --filter 'volume={vol}' | xargs -r docker start")
                print(f"")
                print(f"   " + "-" * 50 + "\n")
                logger.info(f"Volume restore deferred for {vol}", extra={"volume": vol})

    @contextmanager
    def _temp_restore_dir(self):
        """Context manager for guaranteed cleanup of temp directories."""
        restore_dir = Path(tempfile.mkdtemp(prefix="kopia-restore-"))
        try:
            yield restore_dir
        finally:
            # GARANTIERT cleanup, auch bei Ctrl+C oder Exception
            try:
                shutil.rmtree(restore_dir)
                logger.debug(f"Cleaned up temp dir: {restore_dir}")
            except Exception as e:
                logger.warning(f"Could not clean temp dir {restore_dir}: {e}")

    def _execute_volume_restore(self, vol: str, unit: str, snap_id: str, config_file: str) -> bool:  # ← UNIT Parameter!
        """Execute volume restore directly via Python with guaranteed cleanup."""
        import tempfile
        import shutil
        from contextlib import contextmanager
        
        @contextmanager
        def temp_restore_dir():
            """Context manager for guaranteed cleanup."""
            restore_dir = Path(tempfile.mkdtemp(prefix="kopia-restore-"))
            try:
                yield restore_dir
            finally:
                try:
                    shutil.rmtree(restore_dir)
                    logger.debug(f"Cleaned up temp dir: {restore_dir}")
                except Exception as e:
                    logger.warning(f"Could not clean temp dir {restore_dir}: {e}")
        
        try:
            # 1. Stop containers
            print("   1️⃣ Stopping containers...")
            result = subprocess.run(
                ["docker", "ps", "-q", "--filter", f"volume={vol}"],
                capture_output=True, text=True, check=True
            )
            stopped_ids = [s for s in result.stdout.strip().split() if s]
            
            if stopped_ids:
                subprocess.run(["docker", "stop"] + stopped_ids, check=True)
                print(f"      ✓ Stopped {len(stopped_ids)} container(s)")
            else:
                print("      ℹ No running containers using this volume")
            
            # 2. Safety backup
            print("\n   2️⃣ Creating safety backup...")
            backup_name = f"{vol}-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
            
            result = subprocess.run([
                "docker", "run", "--rm",
                "-v", f"{vol}:/src",
                "-v", "/tmp:/backup",
                "alpine",
                "sh", "-c", f"tar -czf /backup/{backup_name} -C /src . 2>/dev/null || true"
            ], capture_output=True, text=True)
            
            backup_path = Path(f"/tmp/{backup_name}")
            if backup_path.exists():
                print(f"      ✓ Backup: {backup_path}")
                logger.info(f"Safety backup created: {backup_path}")
            else:
                print("      ⚠ No backup created (volume might be empty)")
            
            # 3. Restore from Kopia
            print("\n   3️⃣ Restoring from Kopia...")
            print("      (This may take a while...)")
            
            with temp_restore_dir() as restore_dir:
                # CREATE directory structure BEFORE restore!
                volume_path = restore_dir / "volumes" / unit
                volume_path.mkdir(parents=True, exist_ok=True)  # ← FIX!
                
                # Restore snapshot
                subprocess.run([
                    "kopia", "snapshot", "restore", snap_id,
                    "--config-file", config_file,
                    str(restore_dir)
                ], check=True, capture_output=True, text=True)
                
                # Find tar file
                tar_file = restore_dir / "volumes" / unit / vol
                
                if not tar_file.exists():
                    print(f"      ❌ Volume tar file not found: {tar_file}")
                    return False
                
                # Verify it's a tar
                file_check = subprocess.run(
                    ["file", str(tar_file)],
                    capture_output=True, text=True
                )
                
                if "tar archive" not in file_check.stdout.lower():
                    print(f"      ❌ Restored file is not a tar archive")
                    return False
                
                size_mb = tar_file.stat().st_size / 1024 / 1024
                print(f"      ✓ Found tar archive ({size_mb:.1f} MB)")
                
                # Extract tar into volume
                print("      ℹ Extracting into volume...")
                docker_proc = subprocess.run([
                    "docker", "run", "--rm",
                    "-v", f"{vol}:/target",
                    "-v", f"{tar_file}:/backup.tar:ro",
                    "debian:bookworm-slim",
                    "bash", "-c",
                    "rm -rf /target/* /target/..?* /target/.[!.]* 2>/dev/null || true; "
                    "tar -xpf /backup.tar --numeric-owner --xattrs --acls -C /target"
                ], capture_output=True, text=True)
                
                if docker_proc.returncode != 0:
                    print(f"      ❌ Tar extract failed: {docker_proc.stderr}")
                    return False
                
                print("      ✓ Volume restored")
            
            # 4. Restart containers
            print("\n   4️⃣ Restarting containers...")
            result = subprocess.run(
                ["docker", "ps", "-a", "-q", "--filter", f"volume={vol}"],
                capture_output=True, text=True, check=True
            )
            container_ids = [c for c in result.stdout.strip().split() if c]
            
            if container_ids:
                subprocess.run(["docker", "start"] + container_ids, check=True)
                print(f"      ✓ Restarted {len(container_ids)} container(s)")
            else:
                print("      ℹ No containers to restart")
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"      ❌ Command failed: {e}")
            return False
        except KeyboardInterrupt:
            print(f"\n      ⚠️ Restore interrupted by user")
            logger.info("Restore interrupted", extra={"volume": vol})
            return False
        except Exception as e:
            print(f"      ❌ Unexpected error: {e}")
            logger.error(f"Restore error: {e}", extra={"volume": vol})
            return False

    def cleanup_old_safety_backups(self, keep_last: int = 5):
        """Clean up old safety backups in /tmp."""
        try:
            backups = sorted(Path("/tmp").glob("*-backup-*.tar.gz"))
            if len(backups) > keep_last:
                removed_count = 0
                for old in backups[:-keep_last]:
                    try:
                        old.unlink()
                        logger.info(f"Removed old backup: {old}")
                        removed_count += 1
                    except Exception as e:
                        logger.warning(f"Could not remove {old}: {e}")
                
                if removed_count > 0:
                    print(f"\n   🧹 Cleaned up {removed_count} old safety backups")
        except Exception as e:
            logger.debug(f"Backup cleanup failed: {e}")

    def _display_restart_instructions(self, recipe_dir: Path):
        """Show modern docker compose restart steps (no legacy fallback)."""
        compose_file = recipe_dir / "docker-compose.yml"
        project_files_dir = recipe_dir / "project-files"
        
        print("\n   🐳 Service Restart:")
        print("   " + "-" * 40)
        
        # Check if project files exist
        if project_files_dir.exists() and any(project_files_dir.iterdir()):
            config_files = list(project_files_dir.glob("*"))
            print(f"\n   📁 Restored {len(config_files)} project configuration files:")
            for cf in sorted(config_files)[:10]:  # Show max 10
                print(f"      • {cf.name}")
            if len(config_files) > 10:
                print(f"      ... and {len(config_files) - 10} more")
            
            print(f"\n   📋 To use these config files:")
            print(f"   1. Copy them to your deployment directory:")
            print(f"      cp {project_files_dir}/* /path/to/your/project/")
            print(f"")
            print(f"   2. Or interactively select destination:")
            print(f"      cd {recipe_dir}")
            print(f"      # Review files in project-files/")
            print(f"      # Copy needed files to your docker compose directory")
            print(f"")
        
        if compose_file.exists():
            print(f"   3. Navigate to your project directory and start:")
            print(f"      cd /path/to/your/project  # where you copied the files")
            print(f"      docker compose up -d")
            print(f"")
            print(f"   💡 Tip: Original compose file also available at:")
            print(f"      {compose_file}")
        else:
            print(f"   ⚠️  No docker-compose.yml found in backup")
            print(f"   Review the inspect files in: {recipe_dir}")
            print(f"   Recreate containers with appropriate 'docker run' options")
