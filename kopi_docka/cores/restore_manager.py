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
import os
import subprocess
import tempfile
import shutil
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from contextlib import contextmanager

from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

from ..helpers.logging import get_logger
from ..helpers.ui_utils import (
    run_command,
    SubprocessError,
    print_header,
    print_success,
    print_error,
    print_info,
    print_separator,
)
from ..types import RestorePoint
from ..helpers.config import Config
from ..cores.repository_manager import KopiaRepository
from ..cores.hooks_manager import HooksManager
from ..cores.safe_exit_manager import SafeExitManager, DataSafetyHandler
from ..helpers.constants import (
    CONTAINER_START_TIMEOUT,
    BACKUP_FORMAT_TAR,
    BACKUP_FORMAT_DIRECT,
    DOCKER_COMPOSE_PROJECT_LABEL,
)
from ..helpers import (
    check_file_conflicts,
    create_file_backup,
    copy_with_rollback,
)

logger = get_logger(__name__)


class RestoreManager:
    """Interactive restore wizard for cold backups (recipes + volumes)."""

    def __init__(
        self,
        config: Config,
        non_interactive: bool = False,
        force_recreate_networks: bool = False,
        skip_network_recreation: bool = False,
    ):
        self.config = config
        self.repo = KopiaRepository(config)
        self.hooks_manager = HooksManager(config)
        self.start_timeout = self.config.getint("backup", "start_timeout", CONTAINER_START_TIMEOUT)
        self.non_interactive = non_interactive
        self.force_recreate_networks = force_recreate_networks
        self.skip_network_recreation = skip_network_recreation

        if self.force_recreate_networks and self.skip_network_recreation:
            raise ValueError("Cannot force and skip network recreation at the same time")

    def interactive_restore(self):
        """Run interactive wizard."""
        print_header(
            "Kopi-Docka Restore Wizard", "(Non-interactive: --yes)" if self.non_interactive else ""
        )

        logger.info("Starting restore wizard", extra={"non_interactive": self.non_interactive})

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
            print_error("Missing required dependencies:")
            for dep in missing:
                print_info(f"• {dep}")
            print_separator()
            print_info("Install missing dependencies with: kopi-docka install-deps")
            print_info("Or check manually:")
            if "Docker" in missing:
                print_info("docker --version")
                print_info("systemctl status docker")
            if "tar" in missing:
                print_info("which tar")
            if "Kopia" in missing:
                print_info("kopia --version")
            logger.error(f"Restore aborted: missing dependencies {missing}")
            return

        # Check if Kopia repository is connected
        if not self.repo.is_connected():
            print_error("Not connected to Kopia repository")
            print_info("Please connect first: kopi-docka init")
            logger.error("Restore aborted: repository not connected")
            return

        print_success("Dependencies OK")
        print_success("Repository connected")

        points = self._find_restore_points()
        if not points:
            print_error("No backups found to restore.")
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
                current_session = {"timestamp": p.timestamp, "units": [p]}
            else:
                # Check ob innerhalb 5 Min vom neuesten in aktueller Session
                time_diff = current_session["timestamp"] - p.timestamp
                if time_diff <= timedelta(minutes=5):
                    # Gehört zur aktuellen Session
                    current_session["units"].append(p)
                else:
                    # Neue Session starten
                    sessions.append(current_session)
                    current_session = {"timestamp": p.timestamp, "units": [p]}

        # Letzte Session hinzufügen
        if current_session:
            sessions.append(current_session)

        print_info("\n📋 Available backup sessions:\n")
        for idx, session in enumerate(sessions, 1):
            ts = session["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            units = session["units"]

            # Zeitspanne der Session
            if len(units) > 1:
                oldest = min(u.timestamp for u in units)
                newest = max(u.timestamp for u in units)
                duration = (newest - oldest).total_seconds()
                time_range = f" (span: {int(duration/60)}min)" if duration > 60 else ""
            else:
                time_range = ""

            unit_names = ", ".join([u.unit_name for u in units])
            total_volumes = sum(len(u.volume_snapshots) for u in units)

            print(f"{idx}. 📅 {ts}{time_range}")
            print(f"   Units: {unit_names}")
            print(f"   Total volumes: {total_volumes}\n")

        # Session wählen
        if self.non_interactive:
            # Auto-select most recent session (first one)
            session_idx = 0
            print(f"🎯 Auto-selecting most recent session (--yes mode)")
            logger.info("Auto-selected session 1 (non-interactive)")
        else:
            while True:
                try:
                    choice = (
                        input("🎯 Select backup session (number, or 'q' to quit): ").strip().lower()
                    )

                    if choice == "q":
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
        units = selected_session["units"]

        # Wenn nur 1 Unit in Session → direkt nehmen
        if len(units) == 1:
            sel = units[0]
        elif self.non_interactive:
            # Auto-select first unit in non-interactive mode
            sel = units[0]
            print(f"\n🎯 Auto-selecting first unit: {sel.unit_name} (--yes mode)")
            logger.info(f"Auto-selected unit {sel.unit_name} (non-interactive)")
        else:
            # Mehrere Units → User wählen lassen
            print("\n📦 Units in this backup session:\n")
            for idx, u in enumerate(units, 1):
                ts = u.timestamp.strftime("%H:%M:%S")
                print(f"{idx}. {u.unit_name} ({len(u.volume_snapshots)} volumes) - {ts}")

            while True:
                try:
                    choice = (
                        input("\n🎯 Select unit to restore (number, or 'q' to quit): ")
                        .strip()
                        .lower()
                    )

                    if choice == "q":
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
        if sel.network_snapshots:
            print(f"  - {len(sel.network_snapshots)} network(s)")
        print(f"  - {len(sel.volume_snapshots)} volumes")

        if self.non_interactive:
            print("\n✓ Auto-confirming restore (--yes mode)")
            logger.info("Auto-confirmed restore (non-interactive)")
        else:
            confirm = input("\n⚠️ Proceed with restore? (yes/no/q): ").strip().lower()
            if confirm not in ("yes", "y"):
                print("❌ Restore cancelled.")
                logger.info("Restore cancelled at confirmation")
                return

        self._restore_unit(sel)

    def advanced_interactive_restore(self):
        """Run advanced interactive wizard with cross-machine support.

        This wizard shows ALL machines that have backups in the repository,
        allowing restore from a different/crashed server.
        """
        import socket

        print("\n" + "=" * 60)
        print("🔄 Kopi-Docka Advanced Restore Wizard")
        print("   (Cross-Machine Restore Mode)")
        if self.non_interactive:
            print("   (Non-interactive mode: --yes)")
        print("=" * 60)

        logger.info(
            "Starting advanced restore wizard", extra={"non_interactive": self.non_interactive}
        )

        # Check dependencies
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
            logger.error(f"Restore aborted: missing dependencies {missing}")
            return

        if not self.repo.is_connected():
            print("\n❌ Not connected to Kopia repository")
            print("\nPlease connect first:")
            print("   kopi-docka init")
            logger.error("Restore aborted: repository not connected")
            return

        print("\n✓ Dependencies OK")
        print("✓ Repository connected")

        # Step 1: Discover all machines
        print("\n📡 Scanning repository for all machines...")
        machines = self.repo.discover_machines()

        if not machines:
            print("\n❌ No backups found in repository.")
            logger.warning("No machines found in repository")
            return

        current_hostname = socket.gethostname()

        print("\n📋 Machines with backups in repository:\n")
        for idx, m in enumerate(machines, 1):
            is_current = "⭐" if m.hostname == current_hostname else "  "
            last_backup_str = (
                m.last_backup.strftime("%Y-%m-%d %H:%M:%S") if m.last_backup.year > 1 else "unknown"
            )
            size_mb = m.total_size / 1024 / 1024

            print(f"{idx}. {is_current} 🖥️  {m.hostname}")
            print(f"      Last backup: {last_backup_str}")
            print(
                f"      Units: {', '.join(m.units[:5])}{' ...' if len(m.units) > 5 else ''} ({len(m.units)} total)"
            )
            print(f"      Snapshots: {m.backup_count} ({size_mb:.1f} MB)")
            print()

        # Step 2: Select machine
        if self.non_interactive:
            machine_idx = 0
            print(f"🎯 Auto-selecting first machine (--yes mode)")
            logger.info("Auto-selected first machine (non-interactive)")
        else:
            while True:
                try:
                    choice = (
                        input("🎯 Select source machine (number, or 'q' to quit): ").strip().lower()
                    )

                    if choice == "q":
                        print("\n⚠️ Restore cancelled.")
                        logger.info("Restore cancelled by user")
                        return

                    machine_idx = int(choice) - 1
                    if 0 <= machine_idx < len(machines):
                        break
                    print("❌ Invalid selection. Please try again.")
                except ValueError:
                    print("❌ Please enter a number or 'q' to quit.")
                except KeyboardInterrupt:
                    print("\n⚠️ Restore cancelled.")
                    logger.info("Restore cancelled by user (interrupt)")
                    return

        selected_machine = machines[machine_idx]

        # Cross-machine warning
        if selected_machine.hostname != current_hostname:
            print("\n" + "=" * 60)
            print("⚠️  CROSS-MACHINE RESTORE WARNING")
            print("=" * 60)
            print(f"\n   Source:  {selected_machine.hostname}")
            print(f"   Target:  {current_hostname} (current)")
            print("\n   ⚠️  Potential Issues:")
            print("   • Container names may conflict with existing containers")
            print("   • Network names may conflict with existing networks")
            print("   • Volume names may conflict with existing volumes")
            print("   • Paths in configs may need adjustment")

            if not self.non_interactive:
                confirm = (
                    input("\n⚠️  Proceed with cross-machine restore? (yes/no): ").strip().lower()
                )
                if confirm not in ("yes", "y"):
                    print("❌ Restore cancelled.")
                    logger.info("Cross-machine restore cancelled by user")
                    return

        # Step 3: Find restore points for selected machine
        points = self._find_restore_points_for_machine(selected_machine.hostname)

        if not points:
            print(f"\n❌ No backups found for machine: {selected_machine.hostname}")
            logger.warning(f"No restore points found for machine {selected_machine.hostname}")
            return

        # Group by sessions (same as interactive_restore)
        sorted_points = sorted(points, key=lambda x: x.timestamp, reverse=True)

        sessions = []
        current_session = None

        for p in sorted_points:
            if current_session is None:
                current_session = {"timestamp": p.timestamp, "units": [p]}
            else:
                time_diff = current_session["timestamp"] - p.timestamp
                if time_diff <= timedelta(minutes=5):
                    current_session["units"].append(p)
                else:
                    sessions.append(current_session)
                    current_session = {"timestamp": p.timestamp, "units": [p]}

        if current_session:
            sessions.append(current_session)

        print(f"\n📋 Backup sessions for {selected_machine.hostname}:\n")
        for idx, session in enumerate(sessions, 1):
            ts = session["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            units = session["units"]
            unit_names = ", ".join([u.unit_name for u in units])
            total_volumes = sum(len(u.volume_snapshots) for u in units)

            print(f"{idx}. 📅 {ts}")
            print(f"   Units: {unit_names}")
            print(f"   Total volumes: {total_volumes}\n")

        # Select session
        if self.non_interactive:
            session_idx = 0
            print(f"🎯 Auto-selecting most recent session (--yes mode)")
        else:
            while True:
                try:
                    choice = (
                        input("🎯 Select backup session (number, or 'q' to quit): ").strip().lower()
                    )

                    if choice == "q":
                        print("\n⚠️ Restore cancelled.")
                        return

                    session_idx = int(choice) - 1
                    if 0 <= session_idx < len(sessions):
                        break
                    print("❌ Invalid selection. Please try again.")
                except ValueError:
                    print("❌ Please enter a number or 'q' to quit.")
                except KeyboardInterrupt:
                    print("\n⚠️ Restore cancelled.")
                    return

        selected_session = sessions[session_idx]
        units = selected_session["units"]

        # Select unit if multiple
        if len(units) == 1:
            sel = units[0]
        elif self.non_interactive:
            sel = units[0]
            print(f"\n🎯 Auto-selecting first unit: {sel.unit_name} (--yes mode)")
        else:
            print("\n📦 Units in this backup session:\n")
            for idx, u in enumerate(units, 1):
                ts = u.timestamp.strftime("%H:%M:%S")
                print(f"{idx}. {u.unit_name} ({len(u.volume_snapshots)} volumes) - {ts}")

            while True:
                try:
                    choice = (
                        input("\n🎯 Select unit to restore (number, or 'q' to quit): ")
                        .strip()
                        .lower()
                    )

                    if choice == "q":
                        print("\n⚠️ Restore cancelled.")
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
                    return

        logger.info(
            f"Selected restore point: {sel.unit_name} from {sel.timestamp} (machine: {selected_machine.hostname})",
            extra={"unit_name": sel.unit_name, "source_machine": selected_machine.hostname},
        )

        print(f"\n✅ Selected: {sel.unit_name} from {sel.timestamp}")
        print(f"   Source machine: {selected_machine.hostname}")
        print("\n📝 This will restore:")
        print(f"  - Recipe/configuration files")
        if sel.network_snapshots:
            print(f"  - {len(sel.network_snapshots)} network(s)")
        print(f"  - {len(sel.volume_snapshots)} volumes")

        if not self.non_interactive:
            confirm = input("\n⚠️ Proceed with restore? (yes/no/q): ").strip().lower()
            if confirm not in ("yes", "y"):
                print("❌ Restore cancelled.")
                return

        self._restore_unit(sel)

    def _find_restore_points_for_machine(self, hostname: str) -> List[RestorePoint]:
        """Find restore points for a specific machine.

        Args:
            hostname: Hostname to filter by

        Returns:
            List of RestorePoint objects for that machine
        """
        out: List[RestorePoint] = []
        try:
            # Use list_all_snapshots to get snapshots from all machines
            snaps = self.repo.list_all_snapshots()
            groups = {}

            for s in snaps:
                # Filter by hostname
                snap_host = s.get("host", "unknown")
                if snap_host != hostname:
                    continue

                tags = s.get("tags", {})
                unit = tags.get("unit")
                backup_id = tags.get("backup_id")
                ts_str = tags.get("timestamp")
                snap_type = tags.get("type", "")

                if not unit or not backup_id:
                    continue

                try:
                    # Handle ISO format with timezone (Z suffix)
                    ts_clean = ts_str.replace("Z", "+00:00") if ts_str else None
                    ts = (
                        datetime.fromisoformat(ts_clean) if ts_clean else datetime.now(timezone.utc)
                    )
                except ValueError:
                    ts = datetime.now(timezone.utc)

                key = f"{unit}:{backup_id}"
                if key not in groups:
                    groups[key] = RestorePoint(
                        unit_name=unit,
                        timestamp=ts,
                        backup_id=backup_id,
                        recipe_snapshots=[],
                        volume_snapshots=[],
                        database_snapshots=[],
                        network_snapshots=[],
                        docker_config_snapshots=[],
                    )

                if snap_type == "recipe":
                    groups[key].recipe_snapshots.append(s)
                elif snap_type == "volume":
                    groups[key].volume_snapshots.append(s)
                elif snap_type == "networks":
                    groups[key].network_snapshots.append(s)
                elif snap_type == "docker_config":
                    groups[key].docker_config_snapshots.append(s)

            out = list(groups.values())
            out.sort(key=lambda x: x.timestamp, reverse=True)
            logger.debug(f"Found {len(out)} restore points for machine {hostname}")
        except Exception as e:
            logger.error(f"Failed to find restore points for machine {hostname}: {e}")

        return out

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
                    # Handle ISO format with timezone (Z suffix)
                    ts_clean = ts_str.replace("Z", "+00:00") if ts_str else None
                    ts = (
                        datetime.fromisoformat(ts_clean) if ts_clean else datetime.now(timezone.utc)
                    )
                except ValueError:
                    ts = datetime.now(timezone.utc)

                key = f"{unit}:{backup_id}"
                if key not in groups:
                    groups[key] = RestorePoint(
                        unit_name=unit,
                        timestamp=ts,
                        backup_id=backup_id,
                        recipe_snapshots=[],
                        volume_snapshots=[],
                        database_snapshots=[],  # kept empty for type-compat
                        network_snapshots=[],
                        docker_config_snapshots=[],
                    )

                # Nutze Type aus Tags statt path
                if snap_type == "recipe":
                    groups[key].recipe_snapshots.append(s)
                elif snap_type == "volume":
                    groups[key].volume_snapshots.append(s)
                elif snap_type == "networks":
                    groups[key].network_snapshots.append(s)
                elif snap_type == "docker_config":
                    groups[key].docker_config_snapshots.append(s)

            out = list(groups.values())
            out.sort(key=lambda x: x.timestamp, reverse=True)
            logger.debug(f"Found {len(out)} restore points")
        except Exception as e:
            logger.error(f"Failed to find restore points: {e}")

        return out

    def _get_backup_scope(self, restore_point: RestorePoint) -> str:
        """
        Get backup scope from snapshot tags.

        Returns scope string or "standard" if tag not found (legacy snapshots).

        Args:
            restore_point: The restore point to check

        Returns:
            Backup scope ("minimal", "standard", or "full")
        """
        # Check all snapshot types for backup_scope tag
        all_snapshots = (
            restore_point.recipe_snapshots
            + restore_point.volume_snapshots
            + restore_point.network_snapshots
            + restore_point.docker_config_snapshots
        )

        if not all_snapshots:
            return "standard"  # Default for empty restore points

        # Read scope from first snapshot (all should have same scope)
        first_snapshot = all_snapshots[0]
        tags = first_snapshot.get("tags", {})
        scope = tags.get("backup_scope", "standard")
        return scope

    def _show_scope_warnings(self, scope: str, restore_point: RestorePoint):
        """Display warnings based on backup scope.

        Args:
            scope: The backup scope ("minimal", "standard", or "full")
            restore_point: The restore point being restored
        """
        from rich.panel import Panel

        console = Console()

        if scope == "minimal":
            console.print()
            console.print(
                Panel.fit(
                    "[yellow]⚠️  MINIMAL Scope Backup Detected[/yellow]\n\n"
                    "This backup contains ONLY volume data.\n"
                    "Container recipes (docker-compose files) are NOT included.\n\n"
                    "[bold]After restore:[/bold]\n"
                    "• Volumes will be restored\n"
                    "• Containers must be recreated manually\n"
                    "• Networks must be recreated manually\n\n"
                    "Consider using --scope standard or --scope full for complete backups.",
                    border_style="yellow",
                    title="Restore Limitation",
                )
            )
            console.print()

        # Check for docker_config snapshots
        if restore_point.docker_config_snapshots:
            console.print(
                "[blue]ℹ️  Docker daemon configuration is included but will NOT be auto-restored.[/blue]\n"
                "   Use 'kopi-docka restore show-docker-config' to view and manually apply.\n"
            )

    def _restore_unit(self, rp: RestorePoint):
        """Restore a selected backup unit."""
        print_separator()
        print_header("Restore", f"Unit: {rp.unit_name}")

        # Check backup scope and show warnings
        scope = self._get_backup_scope(rp)
        logger.info(
            f"Starting restore for unit: {rp.unit_name} (scope: {scope})",
            extra={"unit_name": rp.unit_name, "backup_scope": scope},
        )

        # Show scope-specific warnings
        self._show_scope_warnings(scope, rp)

        # Pre-restore hook
        print_info("🔧 Executing pre-restore hook...")
        if not self.hooks_manager.execute_pre_restore(rp.unit_name):
            print_error("Pre-restore hook failed")
            logger.error(
                "Pre-restore hook failed, aborting restore", extra={"unit_name": rp.unit_name}
            )
            return

        safe_unit = re.sub(r"[^A-Za-z0-9._-]+", "_", rp.unit_name)
        restore_dir = Path(tempfile.mkdtemp(prefix=f"kopia-docka-restore-{safe_unit}-"))
        print_info(f"📂 Restore directory: {restore_dir}")

        # Setup DataSafetyHandler for emergency cleanup on abort
        safe_exit = SafeExitManager.get_instance()
        data_safety_handler = DataSafetyHandler()
        safe_exit.register_handler(data_safety_handler)
        # Register temp directory for cleanup on abort
        data_safety_handler.register_temp_dir(str(restore_dir))

        try:
            # 1) Recipes
            print("\n1️⃣ Restoring recipes...")
            recipe_dir = self._restore_recipe(rp, restore_dir)

            # 2) Networks
            if rp.network_snapshots:
                print("\n2️⃣ Restoring networks...")
                restored_networks = self._restore_networks(rp, restore_dir)
                if restored_networks > 0:
                    print(f"   ✅ Restored {restored_networks} network(s)")
            else:
                print("\n2️⃣ No networks to restore (or minimal backup scope)")

            # 3) Volume instructions
            if rp.volume_snapshots:
                print("\n3️⃣ Volume restoration:")
                self._display_volume_restore_instructions(rp, restore_dir, data_safety_handler)

            # 4) Interactive config copy (NEW in v3.1.0)
            if recipe_dir.exists():
                print("\n4️⃣ Configuration files:")
                self._interactive_copy_configs(recipe_dir, rp.unit_name)

            # 5) Restart instructions
            print("\n5️⃣ Service restart instructions:")
            self._display_restart_instructions(recipe_dir)

            # 6) Post-restore hook
            print("\n🔧 Executing post-restore hook...")
            if not self.hooks_manager.execute_post_restore(rp.unit_name):
                print("⚠️ Post-restore hook failed")
                logger.warning("Post-restore hook failed", extra={"unit_name": rp.unit_name})

            print_separator()
            print_success("Restoration guide complete!")
            print_info("📋 Follow the instructions above to restore your service.")

            logger.info(
                f"Restore guide completed for {rp.unit_name}",
                extra={"unit_name": rp.unit_name, "restore_dir": str(restore_dir)},
            )

        except Exception as e:
            logger.error(f"Restore failed: {e}", extra={"unit_name": rp.unit_name})
            print(f"\n❌ Error during restore: {e}")

        finally:
            # GUARANTEED CLEANUP: Remove temporary restore directory
            # This prevents /tmp from filling up on VPS systems
            try:
                if restore_dir.exists():
                    shutil.rmtree(restore_dir)
                    logger.debug(f"Cleaned up restore directory: {restore_dir}")
                    print(f"\n🧹 Temporary restore directory cleaned up")
            except Exception as cleanup_error:
                logger.warning(
                    f"Could not clean up restore directory {restore_dir}: {cleanup_error}",
                    extra={"unit_name": rp.unit_name},
                )
                print(f"\n⚠️  Could not clean up {restore_dir}: {cleanup_error}")

            # Unregister DataSafetyHandler (cleanup complete)
            safe_exit.unregister_handler(data_safety_handler)

    def _restore_recipe(self, rp: RestorePoint, restore_dir: Path) -> Path:
        """Restore recipe snapshots into a folder."""
        if not rp.recipe_snapshots:
            logger.warning("No recipe snapshots found", extra={"unit_name": rp.unit_name})
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

    def _restore_networks(self, rp: RestorePoint, restore_dir: Path) -> int:
        """
        Restore Docker networks from snapshot.

        Returns:
            Number of networks restored
        """
        if not rp.network_snapshots:
            logger.debug("No network snapshots found", extra={"unit_name": rp.unit_name})
            return 0

        networks_dir = restore_dir / "networks"
        networks_dir.mkdir(parents=True, exist_ok=True)

        restored_count = 0

        for snap in rp.network_snapshots:
            try:
                snapshot_id = snap["id"]
                print(f"   📥 Restoring network snapshot: {snapshot_id[:12]}...")

                # Restore snapshot to directory
                self.repo.restore_snapshot(snapshot_id, str(networks_dir))

                # Read networks configuration
                networks_file = networks_dir / "networks.json"
                if not networks_file.exists():
                    print(f"   ⚠️ Warning: networks.json not found in snapshot")
                    continue

                network_configs = json.loads(networks_file.read_text())

                # Get list of existing networks
                result = run_command(
                    ["docker", "network", "ls", "--format", "{{.Name}}"],
                    "Listing existing networks",
                    timeout=10,
                )
                existing_networks = {n for n in result.stdout.strip().split("\n") if n}

                # Restore each network
                for net_config in network_configs:
                    net_name = net_config.get("Name")
                    if not net_name:
                        continue
                    attached_containers: List[Tuple[str, str]] = []
                    stopped_container_ids: List[str] = []

                    # Check for conflicts
                    if net_name in existing_networks:
                        print(f"   ⚠️ Network '{net_name}' already exists")

                        if self.skip_network_recreation:
                            print(f"      ↷ Skipping '{net_name}' (--no-recreate-networks)")
                            continue

                        if self.force_recreate_networks:
                            choice = "yes"
                        elif self.non_interactive:
                            print(f"      ✓ Auto-recreating '{net_name}' (--yes mode)")
                            choice = "yes"
                        else:
                            choice = (
                                input(f"      Recreate network '{net_name}'? (yes/no/q): ")
                                .strip()
                                .lower()
                            )

                            if choice == "q":
                                print("\n   ⚠️ Network restore cancelled.")
                                return restored_count

                        if choice not in ("yes", "y"):
                            print(f"      ↷ Skipping '{net_name}'")
                            continue

                        attached_containers = self._list_containers_on_network(
                            net_name,
                            include_stopped=True,
                        )
                        running_containers = self._list_containers_on_network(
                            net_name,
                            include_stopped=False,
                        )
                        stopped_container_ids = self._stop_containers(
                            running_containers,
                            net_name,
                        )

                        # Abort recreation if we couldn't stop running containers
                        if running_containers and not stopped_container_ids:
                            print(
                                "      ↷ Could not stop running containers; "
                                "keeping existing network"
                            )
                            continue

                        disconnected = self._disconnect_containers_from_network(
                            net_name,
                            attached_containers,
                        )

                        # Remove existing network
                        print(f"      🗑️  Removing existing network '{net_name}'...")
                        try:
                            run_command(
                                ["docker", "network", "rm", net_name],
                                f"Removing network {net_name}",
                                timeout=30,
                            )
                        except SubprocessError as e:
                            print(f"      ❌ Failed to remove network: {e.stderr}")
                            print("         Network may still have attached containers.")
                            if disconnected:
                                self._reconnect_containers_to_network(net_name, attached_containers)
                            if stopped_container_ids:
                                self._restart_containers(stopped_container_ids, net_name)
                            continue

                    # Create network
                    print(f"      🔧 Creating network '{net_name}'...")
                    try:
                        cmd = ["docker", "network", "create"]

                        # Driver
                        driver = net_config.get("Driver", "bridge")
                        cmd.extend(["--driver", driver])

                        # IPAM configuration
                        ipam_config = net_config.get("IPAM", {})
                        if ipam_config and ipam_config.get("Config"):
                            for ipam_entry in ipam_config.get("Config", []):
                                subnet = ipam_entry.get("Subnet")
                                if subnet:
                                    cmd.extend(["--subnet", subnet])

                                gateway = ipam_entry.get("Gateway")
                                if gateway:
                                    cmd.extend(["--gateway", gateway])

                                ip_range = ipam_entry.get("IPRange")
                                if ip_range:
                                    cmd.extend(["--ip-range", ip_range])

                        # Labels
                        labels = net_config.get("Labels", {})
                        if labels:
                            for key, value in labels.items():
                                cmd.extend(["--label", f"{key}={value}"])

                        # Options
                        options = net_config.get("Options", {})
                        if options:
                            for key, value in options.items():
                                cmd.extend(["--opt", f"{key}={value}"])

                        # Network name
                        cmd.append(net_name)

                        # Execute
                        run_command(cmd, f"Creating network {net_name}", timeout=30)
                        print(f"      ✅ Network '{net_name}' created")
                        restored_count += 1

                        if attached_containers:
                            self._reconnect_containers_to_network(net_name, attached_containers)

                        if stopped_container_ids:
                            self._restart_containers(stopped_container_ids, net_name)

                        logger.info(
                            f"Network {net_name} restored",
                            extra={"unit_name": rp.unit_name, "network": net_name},
                        )

                    except SubprocessError as e:
                        print(f"      ❌ Failed to create network: {e.stderr}")
                        logger.error(
                            f"Network creation failed: {e.stderr}",
                            extra={"unit_name": rp.unit_name, "network": net_name},
                        )

            except Exception as e:
                logger.error(
                    f"Failed to restore network snapshot: {e}", extra={"unit_name": rp.unit_name}
                )
                print(f"   ⚠️ Warning: Could not restore networks: {e}")

        return restored_count

    def _list_containers_on_network(
        self,
        net_name: str,
        include_stopped: bool = False,
        compose_project: Optional[str] = None,
    ) -> List[Tuple[str, str]]:
        """Return (id, name) tuples for containers attached to a network."""
        cmd = ["docker", "ps"]
        if include_stopped:
            cmd.append("-a")
        cmd.extend(["--filter", f"network={net_name}"])
        if compose_project:
            cmd.extend(["--filter", f"label={DOCKER_COMPOSE_PROJECT_LABEL}={compose_project}"])
        cmd.extend(["--format", "{{.ID}};{{.Names}}"])

        result = run_command(
            cmd,
            f"Listing containers on network {net_name}",
            timeout=10,
            check=False,
        )

        containers: List[Tuple[str, str]] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(";", 1)
            if len(parts) == 2 and parts[0]:
                containers.append((parts[0], parts[1]))
        return containers

    def _stop_containers(self, containers: List[Tuple[str, str]], net_name: str) -> List[str]:
        """Stop running containers connected to a network."""
        ids = [cid for cid, _ in containers]
        if not ids:
            return []

        names = ", ".join(name for _, name in containers)
        print(f"      ⏹️  Stopping containers on '{net_name}': {names}")

        try:
            run_command(
                ["docker", "stop"] + ids,
                f"Stopping {len(ids)} container(s)",
                timeout=60,
            )
            return ids
        except SubprocessError as e:
            print(f"      ❌ Failed to stop containers: {e.stderr}")
            return []

    def _disconnect_containers_from_network(
        self,
        net_name: str,
        containers: List[Tuple[str, str]],
    ) -> List[str]:
        """Disconnect containers from a network to allow removal."""
        if not containers:
            return []

        print("      🔌 Disconnecting containers before recreation...")
        disconnected: List[str] = []

        for cid, name in containers:
            result = run_command(
                ["docker", "network", "disconnect", "-f", net_name, cid],
                f"Disconnecting {name} from {net_name}",
                timeout=15,
                check=False,
            )
            if result.returncode == 0:
                disconnected.append(cid)
            else:
                print(f"      ⚠️ Could not disconnect {name} " f"(exit {result.returncode})")

        return disconnected

    def _reconnect_containers_to_network(
        self,
        net_name: str,
        containers: List[Tuple[str, str]],
    ) -> None:
        """Reconnect previously attached containers to a recreated network."""
        if not containers:
            return

        print(f"      🔌 Re-attaching containers to '{net_name}'...")
        for cid, name in containers:
            result = run_command(
                ["docker", "network", "connect", net_name, cid],
                f"Re-attaching {name} to {net_name}",
                timeout=20,
                check=False,
            )
            if result.returncode != 0:
                print(f"      ⚠️ Could not re-attach {name} " f"(exit {result.returncode})")

    def _restart_containers(self, container_ids: List[str], net_name: str) -> None:
        """Restart containers that were running before network recreation."""
        if not container_ids:
            return

        try:
            run_command(
                ["docker", "start"] + container_ids,
                f"Starting {len(container_ids)} container(s)",
                timeout=60,
            )
            print(f"      🔁 Restarted {len(container_ids)} " f"container(s) on '{net_name}'")
        except SubprocessError as e:
            print(f"      ⚠️ Failed to restart containers: {e.stderr}")

    def _check_for_secrets(self, recipe_dir: Path):
        """Warn if redacted secrets are present in inspect JSONs."""
        for f in recipe_dir.glob("*_inspect.json"):
            try:
                content = f.read_text()
                if "***REDACTED***" in content:
                    print(f"   ⚠ Note: {f.name} contains redacted secrets")
                    print("     Restore actual values manually if needed.")
                    logger.info("Found redacted secrets in restore", extra={"file": f.name})
            except Exception:
                pass

    def _display_volume_restore_instructions(self, rp: RestorePoint, restore_dir: Path, data_safety_handler: DataSafetyHandler):
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

            # User fragen oder auto-bestätigen
            if self.non_interactive:
                print(f"\n   ✓ Auto-restoring '{vol}' (--yes mode)")
                choice = "yes"
            else:
                choice = input(f"\n   ⚠️  Restore '{vol}' NOW? (yes/no/q): ").strip().lower()

                if choice == "q":
                    print("\n   ⚠️ Restore cancelled.")
                    logger.info("Volume restore cancelled by user")
                    return

            if choice in ("yes", "y"):
                # Python führt direkt aus - MIT UNIT!
                print(f"\n   🚀 Restoring volume '{vol}'...")
                print("   " + "=" * 50)

                try:
                    success = self._execute_volume_restore(
                        vol, unit, snap_id, config_file, snapshot=snap, data_safety_handler=data_safety_handler
                    )  # Pass snapshot for format detection and data safety handler

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
                print(
                    f"     sh -c 'tar -czf /backup/{vol}-backup-$(date +%Y%m%d-%H%M%S).tar.gz -C /src .'"
                )
                print(f"")
                print(f"   # 3. Restore from Kopia")
                print(f"   RESTORE_DIR=$(mktemp -d)")
                print(
                    f"   kopia snapshot restore {snap_id} --config-file {config_file} $RESTORE_DIR"
                )
                print(f"   TAR_FILE=$(find $RESTORE_DIR -name '{vol}' -type f)")
                print(f"")
                print(f"   # 4. Extract into volume")
                print(
                    f"   docker run --rm -v {vol}:/target -v $TAR_FILE:/backup.tar:ro debian:bookworm-slim \\"
                )
                print(
                    f"     bash -c 'rm -rf /target/* /target/..?* /target/.[!.]* 2>/dev/null || true; \\"
                )
                print(
                    f"              tar -xpf /backup.tar --numeric-owner --xattrs --acls -C /target'"
                )
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

    def _detect_backup_format(self, snapshot: dict) -> str:
        """Detect backup format from snapshot tags.

        Args:
            snapshot: Snapshot metadata dict

        Returns:
            "direct" for v5.0+ direct snapshots, "tar" for legacy TAR backups
        """
        tags = snapshot.get("tags", {})
        backup_format = tags.get("backup_format")

        if backup_format == BACKUP_FORMAT_DIRECT:
            return BACKUP_FORMAT_DIRECT

        # Legacy backups (before v5.0) don't have backup_format tag
        return BACKUP_FORMAT_TAR

    def _execute_volume_restore(
        self, vol: str, unit: str, snap_id: str, config_file: str, snapshot: dict = None, data_safety_handler: DataSafetyHandler = None
    ) -> bool:
        """Execute volume restore with automatic format detection.

        Dispatcher that routes to the appropriate restore method based on
        the backup format tag in the snapshot.

        Args:
            vol: Volume name
            unit: Unit name
            snap_id: Snapshot ID
            config_file: Kopia config file path
            snapshot: Snapshot metadata dict (optional, for format detection)
            data_safety_handler: Data safety handler for emergency cleanup

        Returns:
            True if restore successful, False otherwise
        """
        # Detect backup format
        if snapshot:
            backup_format = self._detect_backup_format(snapshot)
        else:
            # Fallback: assume TAR for backwards compatibility
            backup_format = BACKUP_FORMAT_TAR

        logger.info(
            f"Restoring volume {vol} using {backup_format} format",
            extra={"volume": vol, "backup_format": backup_format},
        )

        if backup_format == BACKUP_FORMAT_DIRECT:
            return self._execute_volume_restore_direct(vol, unit, snap_id, config_file, data_safety_handler)
        else:
            return self._execute_volume_restore_tar(vol, unit, snap_id, config_file, data_safety_handler)

    def _execute_volume_restore_direct(
        self, vol: str, unit: str, snap_id: str, config_file: str, data_safety_handler: DataSafetyHandler = None
    ) -> bool:
        """Execute volume restore for direct Kopia snapshots (v5.0+).

        Direct snapshots contain the actual file structure, not a TAR archive.
        We restore directly to a temp directory, then rsync to the volume.

        Args:
            vol: Volume name
            unit: Unit name
            snap_id: Snapshot ID
            config_file: Kopia config file path
            data_safety_handler: Data safety handler for emergency cleanup

        Returns:
            True if restore successful, False otherwise
        """

        @contextmanager
        def temp_restore_dir():
            """Context manager for guaranteed cleanup."""
            restore_dir = Path(tempfile.mkdtemp(prefix="kopia-restore-direct-"))
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
            result = run_command(
                ["docker", "ps", "-q", "--filter", f"volume={vol}"],
                "Finding containers using volume",
                timeout=10,
            )
            stopped_ids = [s for s in result.stdout.strip().split() if s]

            if stopped_ids:
                run_command(
                    ["docker", "stop"] + stopped_ids,
                    f"Stopping {len(stopped_ids)} container(s)",
                    timeout=60,
                )
                print(f"      ✓ Stopped {len(stopped_ids)} container(s)")
                # Register stopped containers with DataSafetyHandler (keep stopped on abort)
                if data_safety_handler:
                    for container_id in stopped_ids:
                        data_safety_handler.register_stopped_container(container_id)
            else:
                print("      ℹ No running containers using this volume")

            # 2. Safety backup
            print("\n   2️⃣ Creating safety backup...")
            backup_name = f"{vol}-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"

            run_command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol}:/src",
                    "-v",
                    "/tmp:/backup",
                    "alpine",
                    "sh",
                    "-c",
                    f"tar -czf /backup/{backup_name} -C /src . 2>/dev/null || true",
                ],
                "Creating safety backup",
                timeout=300,
                check=False,
            )

            backup_path = Path(f"/tmp/{backup_name}")
            if backup_path.exists():
                print(f"      ✓ Backup: {backup_path}")
                logger.info(f"Safety backup created: {backup_path}")
            else:
                print("      ⚠ No backup created (volume might be empty)")

            # 3. Restore from Kopia (direct format)
            print("\n   3️⃣ Restoring from Kopia (direct format)...")
            print("      (This may take a while...)")

            with temp_restore_dir() as restore_dir:
                # Restore snapshot directly
                run_command(
                    [
                        "kopia",
                        "snapshot",
                        "restore",
                        snap_id,
                        "--config-file",
                        config_file,
                        str(restore_dir),
                    ],
                    "Restoring snapshot from Kopia",
                    show_output=True,
                )

                # Count restored files
                file_count = sum(1 for _ in restore_dir.rglob("*") if _.is_file())
                print(f"      ✓ Restored {file_count} files")

                # Get Docker volume mountpoint
                result = run_command(
                    ["docker", "volume", "inspect", vol, "--format", "{{.Mountpoint}}"],
                    f"Getting mountpoint for {vol}",
                    timeout=10,
                )
                volume_mountpoint = result.stdout.strip()

                if not volume_mountpoint:
                    print(f"      ❌ Could not determine volume mountpoint")
                    return False

                # Clear existing volume content and copy new files
                print("      ℹ Copying files to volume...")

                # Use rsync for efficient copy with permissions preserved
                rsync_result = run_command(
                    [
                        "rsync",
                        "-a",
                        "--delete",
                        "--numeric-ids",
                        f"{restore_dir}/",
                        f"{volume_mountpoint}/",
                    ],
                    "Syncing files to volume",
                    timeout=600,
                    check=False,
                )

                if rsync_result.returncode != 0:
                    # Fallback to cp if rsync not available
                    logger.warning("rsync failed, falling back to cp")
                    # shell=True required for glob patterns - see Phase 0 analysis
                    subprocess.run(
                        f"rm -rf {volume_mountpoint}/* {volume_mountpoint}/.[!.]* {volume_mountpoint}/..?* 2>/dev/null || true",
                        shell=True,
                    )
                    run_command(
                        ["cp", "-a", f"{restore_dir}/.", f"{volume_mountpoint}/"],
                        "Copying files to volume",
                        timeout=600,
                    )

                print("      ✓ Volume restored (direct format)")

            # 4. Restart containers
            print("\n   4️⃣ Restarting containers...")
            result = run_command(
                ["docker", "ps", "-a", "-q", "--filter", f"volume={vol}"],
                "Finding containers to restart",
                timeout=10,
            )
            container_ids = [c for c in result.stdout.strip().split() if c]

            if container_ids:
                run_command(
                    ["docker", "start"] + container_ids,
                    f"Starting {len(container_ids)} container(s)",
                    timeout=60,
                )
                print(f"      ✓ Restarted {len(container_ids)} container(s)")
            else:
                print("      ℹ No containers to restart")

            # 5. Cleanup old safety backups
            self.cleanup_old_safety_backups(keep_last=3)

            return True

        except SubprocessError as e:
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

    def _execute_volume_restore_tar(
        self, vol: str, unit: str, snap_id: str, config_file: str, data_safety_handler: DataSafetyHandler = None
    ) -> bool:
        """Execute volume restore for TAR-based backups (legacy).

        TAR backups contain a single TAR archive that needs to be extracted.

        Args:
            vol: Volume name
            unit: Unit name
            snap_id: Snapshot ID
            config_file: Kopia config file path
            data_safety_handler: Data safety handler for emergency cleanup

        Returns:
            True if restore successful, False otherwise
        """

        @contextmanager
        def temp_restore_dir():
            """Context manager for guaranteed cleanup."""
            restore_dir = Path(tempfile.mkdtemp(prefix="kopia-restore-tar-"))
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
            result = run_command(
                ["docker", "ps", "-q", "--filter", f"volume={vol}"],
                "Finding containers using volume",
                timeout=10,
            )
            stopped_ids = [s for s in result.stdout.strip().split() if s]

            if stopped_ids:
                run_command(
                    ["docker", "stop"] + stopped_ids,
                    f"Stopping {len(stopped_ids)} container(s)",
                    timeout=60,
                )
                print(f"      ✓ Stopped {len(stopped_ids)} container(s)")
                # Register stopped containers with DataSafetyHandler (keep stopped on abort)
                if data_safety_handler:
                    for container_id in stopped_ids:
                        data_safety_handler.register_stopped_container(container_id)
            else:
                print("      ℹ No running containers using this volume")

            # 2. Safety backup
            print("\n   2️⃣ Creating safety backup...")
            backup_name = f"{vol}-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"

            run_command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol}:/src",
                    "-v",
                    "/tmp:/backup",
                    "alpine",
                    "sh",
                    "-c",
                    f"tar -czf /backup/{backup_name} -C /src . 2>/dev/null || true",
                ],
                "Creating safety backup",
                timeout=300,
                check=False,
            )

            backup_path = Path(f"/tmp/{backup_name}")
            if backup_path.exists():
                print(f"      ✓ Backup: {backup_path}")
                logger.info(f"Safety backup created: {backup_path}")
            else:
                print("      ⚠ No backup created (volume might be empty)")

            # 3. Restore from Kopia (TAR format)
            print("\n   3️⃣ Restoring from Kopia (tar format)...")
            print("      (This may take a while...)")

            with temp_restore_dir() as restore_dir:
                # CREATE directory structure BEFORE restore!
                volume_path = restore_dir / "volumes" / unit
                volume_path.mkdir(parents=True, exist_ok=True)

                # Restore snapshot
                run_command(
                    [
                        "kopia",
                        "snapshot",
                        "restore",
                        snap_id,
                        "--config-file",
                        config_file,
                        str(restore_dir),
                    ],
                    "Restoring snapshot from Kopia",
                    show_output=True,
                )

                # Find tar file
                tar_file = restore_dir / "volumes" / unit / vol

                if not tar_file.exists():
                    print(f"      ❌ Volume tar file not found: {tar_file}")
                    return False

                # Verify it's a tar
                file_check = run_command(
                    ["file", str(tar_file)],
                    "Checking file type",
                    timeout=10,
                    check=False,
                )

                if "tar archive" not in file_check.stdout.lower():
                    print(f"      ❌ Restored file is not a tar archive")
                    return False

                size_mb = tar_file.stat().st_size / 1024 / 1024
                print(f"      ✓ Found tar archive ({size_mb:.1f} MB)")

                # Extract tar into volume
                print("      ℹ Extracting into volume...")
                docker_proc = run_command(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-v",
                        f"{vol}:/target",
                        "-v",
                        f"{tar_file}:/backup.tar:ro",
                        "debian:bookworm-slim",
                        "bash",
                        "-c",
                        "rm -rf /target/* /target/..?* /target/.[!.]* 2>/dev/null || true; "
                        "tar -xpf /backup.tar --numeric-owner --xattrs --acls -C /target",
                    ],
                    "Extracting tar to volume",
                    timeout=600,
                    check=False,
                )

                if docker_proc.returncode != 0:
                    print(f"      ❌ Tar extract failed: {docker_proc.stderr}")
                    return False

                print("      ✓ Volume restored (tar format)")

            # 4. Restart containers
            print("\n   4️⃣ Restarting containers...")
            result = run_command(
                ["docker", "ps", "-a", "-q", "--filter", f"volume={vol}"],
                "Finding containers to restart",
                timeout=10,
            )
            container_ids = [c for c in result.stdout.strip().split() if c]

            if container_ids:
                run_command(
                    ["docker", "start"] + container_ids,
                    f"Starting {len(container_ids)} container(s)",
                    timeout=60,
                )
                print(f"      ✓ Restarted {len(container_ids)} container(s)")
            else:
                print("      ℹ No containers to restart")

            # 5. Cleanup old safety backups to prevent /tmp from filling up
            self.cleanup_old_safety_backups(keep_last=3)

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

    def _get_real_user_ids(self) -> tuple:
        """
        Get real user IDs when running with sudo.

        Returns:
            (uid, gid, username) tuple
        """
        uid = int(os.environ.get("SUDO_UID", os.getuid()))
        gid = int(os.environ.get("SUDO_GID", os.getgid()))
        user = os.environ.get("SUDO_USER", "root")
        return uid, gid, user

    def _copy_with_permissions(
        self, source_path: Path, target_dir: Path, uid: int, gid: int
    ) -> int:
        """
        Copy files from source to target with proper permissions.

        Args:
            source_path: Source file or directory
            target_dir: Target directory
            uid: User ID for ownership
            gid: Group ID for ownership

        Returns:
            Number of files copied
        """
        count = 0

        if source_path.is_file():
            # Copy single file
            target_file = target_dir / source_path.name
            shutil.copy2(source_path, target_file)
            os.chown(target_file, uid, gid)
            os.chmod(target_file, 0o644)
            count = 1
            logger.debug(
                f"Copied {source_path.name} with permissions", extra={"target": str(target_file)}
            )
        elif source_path.is_dir():
            # Copy all files from directory
            for item in source_path.iterdir():
                if item.is_file():
                    target_file = target_dir / item.name
                    shutil.copy2(item, target_file)
                    os.chown(target_file, uid, gid)
                    os.chmod(target_file, 0o644)
                    count += 1
                    logger.debug(
                        f"Copied {item.name} with permissions", extra={"target": str(target_file)}
                    )

        return count

    def _interactive_copy_configs(self, recipe_dir: Path, unit_name: str) -> None:
        """
        Interactively copy configuration files to deployment directory.
        With conflict handling and VPS-optimized backups (Phase 2).

        Args:
            recipe_dir: Path to recipes directory
            unit_name: Name of the backup unit
        """
        console = Console()

        # Step 1: Collect files
        compose_order_file = recipe_dir / "compose_order.json"
        project_files_dir = recipe_dir / "project-files"

        files_to_copy = []

        # Add compose files (from compose_order.json if available, else fallback)
        if compose_order_file.exists():
            try:
                compose_files = json.loads(compose_order_file.read_text())
                for cf in compose_files:
                    cf_path = recipe_dir / cf
                    if cf_path.exists():
                        files_to_copy.append(cf_path)
            except Exception:
                pass

        # Fallback: old-style single docker-compose.yml
        if not files_to_copy:
            compose_file = recipe_dir / "docker-compose.yml"
            if compose_file.exists():
                files_to_copy.append(compose_file)

        # Add project files (.env, configs, etc.)
        if project_files_dir.exists():
            files_to_copy.extend([f for f in project_files_dir.glob("*") if f.is_file()])

        if not files_to_copy:
            logger.debug("No config files to copy")
            return

        # Step 2: Display files
        console.print("\n📁 [bold]Restored configuration files:[/bold]")
        for file in files_to_copy:
            console.print(f"   • {file.name}")

        # Step 3: Ask user - Copy?
        if self.non_interactive:
            copy = "yes"
            console.print("\n✓ Auto-copying files to deployment directory (--yes mode)")
        else:
            while True:
                copy = (
                    input("\n🎯 Copy files to deployment directory? [yes/no/q] (yes): ")
                    .strip()
                    .lower()
                )
                if not copy:
                    copy = "yes"
                # Normalize input
                if copy in ("y", "yes"):
                    copy = "yes"
                    break
                elif copy in ("n", "no"):
                    copy = "no"
                    break
                elif copy == "q":
                    break
                else:
                    console.print("[yellow]Please enter 'yes', 'no', or 'q'[/yellow]")

            if copy == "q":
                return

            if copy == "no":
                self._show_manual_instructions(recipe_dir)
                return

        # Step 4: Loop for directory selection with conflict handling
        default_target = f"/opt/stacks/{unit_name}"

        while True:
            # Get target directory
            if self.non_interactive:
                target = default_target
                console.print(f"\n📂 Using default target: {target} (--yes mode)")
            else:
                target = Prompt.ask(f"\n📂 Target directory", default=default_target)
            target_path = Path(target).expanduser()

            # Check write permissions (skip if running with sudo)
            running_with_sudo = os.environ.get("SUDO_USER") is not None

            if not running_with_sudo:
                parent_dir = target_path.parent if not target_path.exists() else target_path
                if not os.access(parent_dir, os.W_OK):
                    console.print(f"[red]✗ No write permission for {parent_dir}[/red]")
                    if self.non_interactive:
                        console.print(
                            "[red]✗ Cannot continue in non-interactive mode without write permission[/red]"
                        )
                        logger.error(
                            f"No write permission for {parent_dir} in non-interactive mode"
                        )
                        return
                    console.print("Try running with sudo or choose different directory.")
                    retry = Prompt.ask(
                        "Try different directory?", choices=["yes", "no"], default="yes"
                    )
                    if retry == "no":
                        return
                    continue

            # Create directory if needed
            try:
                target_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                console.print(f"[red]✗ Cannot create directory: {e}[/red]")
                if self.non_interactive:
                    logger.error(f"Cannot create directory {target_path}: {e}")
                    return
                continue

            # Check for conflicts using helper function
            conflicts = check_file_conflicts(target_path, files_to_copy)

            if not conflicts:
                # No conflicts, proceed to copy
                console.print(f"✓ Target directory is ready")
                break

            # Conflicts found - show them
            console.print("\n⚠️  [bold yellow]Existing files detected:[/bold yellow]")
            for conflict in conflicts:
                console.print(f"   • {conflict.name}")

            if self.non_interactive:
                # Non-interactive: auto-create backups (safest option)
                choice = "2"
                console.print("\n✓ Auto-creating backups before overwrite (--yes mode)")
            else:
                console.print("\n[bold]What do you want to do?[/bold]")
                console.print("1. Overwrite existing files")
                console.print("2. Create backup first (recommended)")
                console.print("3. Choose different directory")
                console.print("4. Skip copying (manual restore)")

                choice = Prompt.ask("Your choice", choices=["1", "2", "3", "4"], default="2")

            if choice == "1":
                # Overwrite without backup
                console.print("\n⚠️  [yellow]Overwriting files without backup...[/yellow]")
                break

            elif choice == "2":
                # Create backups using helper function
                console.print("\n📦 Creating backups (existing .bak files will be overwritten)...")
                backup_files = []
                try:
                    for conflict in conflicts:
                        backup = create_file_backup(conflict)
                        backup_files.append(backup)
                        console.print(f"   ✓ {conflict.name} → {backup.name}")
                except Exception as e:
                    console.print(f"\n[red]✗ Backup failed: {e}[/red]")
                    console.print("Aborting copy operation.")
                    return

                console.print(f"\n✓ Created {len(backup_files)} backup(s)")
                console.print("💡 Previous .bak files were overwritten (only last backup is kept)")
                break

            elif choice == "3":
                # Different directory - loop continues
                continue

            elif choice == "4":
                # Skip copying
                console.print("\n[yellow]Skipping copy operation.[/yellow]")
                self._show_manual_instructions(recipe_dir)
                return

        # Step 5: Copy with rollback using helper function
        success, copied_files = copy_with_rollback(files_to_copy, target_path, console)

        if success:
            console.print(f"\n✓ [bold green]Files copied to: {target_path}[/bold green]")

            # Step 6: Fix ownership (wenn mit sudo gestartet)
            uid, gid, username = self._get_real_user_ids()
            if uid != 0:  # Nur wenn mit sudo gestartet (nicht als root direkt)
                try:
                    run_command(
                        ["chown", "-R", f"{username}:{username}", str(target_path)],
                        f"Fixing ownership to {username}",
                        timeout=60,
                    )
                    console.print(f"✓ Fixed ownership: [cyan]{username}:{username}[/cyan]")
                    logger.info(
                        f"Changed ownership to {username}:{username}",
                        extra={"path": str(target_path)},
                    )
                except SubprocessError as e:
                    console.print(f"[yellow]⚠️  Could not fix ownership: {e.stderr}[/yellow]")
                    logger.warning(f"Ownership change failed: {e}")

            console.print(f"\n📄 Copied files:")
            for file in files_to_copy:
                console.print(f"   • {file.name}")
            console.print(f"\n💡 [bold]To start:[/bold] cd {target_path} && docker compose up -d")
        else:
            console.print("\n[red]Copy operation failed. See logs for details.[/red]")
            self._show_manual_instructions(recipe_dir)

    def _show_manual_instructions(self, recipe_dir: Path) -> None:
        """
        Show manual copy instructions when user declines or copy fails.

        Args:
            recipe_dir: Path to recipes directory
        """
        console = Console()
        console.print("\n📋 [bold]Manual restore instructions:[/bold]")
        console.print(f"\n1. Copy files to your deployment directory:")
        console.print(f"   sudo cp -r {recipe_dir}/* /path/to/your/project/")
        console.print(f"\n2. Fix permissions:")
        console.print(f"   sudo chown -R $USER:$USER /path/to/your/project/")
        console.print(f"\n3. Start containers:")
        console.print(f"   cd /path/to/your/project && docker compose up -d")

    def show_docker_config(self, snapshot_id: str) -> bool:
        """
        Extract and display docker_config snapshot for manual restore.

        This command extracts Docker daemon configuration from a FULL scope backup
        to a temporary location and shows step-by-step instructions for manual
        restore. Auto-restoring daemon.json is intentionally NOT supported to
        prevent accidental production breakage.

        Args:
            snapshot_id: Snapshot ID to extract

        Returns:
            True if extraction successful, False otherwise
        """
        console = Console()

        try:
            # Create temp directory for extraction
            temp_dir = Path(tempfile.mkdtemp(prefix="kopia-docker-config-"))

            console.print(
                Panel.fit(
                    "[bold cyan]Docker Config Manual Restore[/bold cyan]\n\n"
                    "[yellow]⚠️  Safety Notice:[/yellow]\n"
                    "Docker daemon configuration is NOT automatically restored.\n"
                    "You must manually review and apply changes to avoid production issues.",
                    border_style="cyan",
                )
            )
            console.print()

            # Extract snapshot
            console.print(f"[cyan]📥 Extracting docker_config snapshot...[/cyan]")
            console.print(f"   Snapshot ID: {snapshot_id[:12]}...")
            console.print(f"   Target: {temp_dir}")
            console.print()

            try:
                self.repo.restore_snapshot(snapshot_id, str(temp_dir))
            except Exception as e:
                console.print(f"[red]✗ Failed to restore snapshot: {e}[/red]")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return False

            # Check what was extracted
            extracted_files = list(temp_dir.rglob("*"))
            config_files = [f for f in extracted_files if f.is_file()]

            if not config_files:
                console.print("[yellow]⚠️  No files found in snapshot[/yellow]")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return False

            # Display extracted files
            console.print("[bold green]✓ Extracted files:[/bold green]")
            for file in config_files:
                rel_path = file.relative_to(temp_dir)
                size_kb = file.stat().st_size / 1024
                console.print(f"   • {rel_path} ({size_kb:.1f} KB)")
            console.print()

            # Show file contents (if small enough)
            daemon_json = temp_dir / "daemon.json"
            if daemon_json.exists() and daemon_json.stat().st_size < 10240:  # <10KB
                console.print("[bold]📄 daemon.json contents:[/bold]")
                console.print(Panel(
                    daemon_json.read_text(),
                    border_style="dim",
                    expand=False,
                ))
                console.print()

            # Show manual restore instructions
            console.print(
                Panel.fit(
                    "[bold]🔧 Manual Restore Instructions[/bold]\n\n"
                    "[yellow]⚠️  WARNING: Applying wrong Docker config can break Docker entirely![/yellow]\n"
                    "Only proceed if you understand these settings.\n\n"
                    "[bold]Step 1: Review extracted files[/bold]\n"
                    f"   cd {temp_dir}\n"
                    f"   ls -lah\n"
                    f"   cat daemon.json  # Review configuration\n\n"
                    "[bold]Step 2: Backup current config (if exists)[/bold]\n"
                    "   sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak\n\n"
                    "[bold]Step 3: Apply configuration (CAREFULLY!)[/bold]\n"
                    f"   sudo cp {temp_dir}/daemon.json /etc/docker/daemon.json\n\n"
                    "[bold]Step 4: Systemd overrides (if present)[/bold]\n"
                    f"   # If docker.service.d/ was extracted:\n"
                    f"   sudo cp -r {temp_dir}/docker.service.d/ /etc/systemd/system/\n"
                    "   sudo systemctl daemon-reload\n\n"
                    "[bold]Step 5: Restart Docker daemon[/bold]\n"
                    "   sudo systemctl restart docker\n\n"
                    "[bold]Step 6: Verify Docker is working[/bold]\n"
                    "   docker ps\n"
                    "   docker info\n\n"
                    "[dim]Note: Files will remain in temp directory for review.[/dim]\n"
                    f"[dim]Cleanup when done: rm -rf {temp_dir}[/dim]",
                    border_style="yellow",
                    title="[bold yellow]⚠️  Manual Restore Required[/bold yellow]",
                )
            )
            console.print()

            console.print(f"[bold green]✓ Extraction complete![/bold green]")
            console.print(f"   Files location: [cyan]{temp_dir}[/cyan]")
            console.print()
            console.print(
                "[dim]💡 Tip: Test configuration changes on a non-production system first.[/dim]"
            )
            console.print()

            logger.info(
                f"Docker config snapshot extracted",
                extra={"snapshot_id": snapshot_id, "temp_dir": str(temp_dir)},
            )

            return True

        except KeyboardInterrupt:
            console.print("\n[yellow]⚠️  Extraction cancelled[/yellow]")
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            return False
        except Exception as e:
            console.print(f"\n[red]✗ Unexpected error: {e}[/red]")
            logger.error(f"Docker config extraction failed: {e}")
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            return False

    def _display_restart_instructions(self, recipe_dir: Path):
        """Show modern docker compose restart steps with override support."""
        compose_order_file = recipe_dir / "compose_order.json"
        compose_file = recipe_dir / "docker-compose.yml"

        print("\n   🐳 Service Restart:")
        print("   " + "-" * 40)

        # Try to read compose order (new format with overrides)
        compose_files = []
        if compose_order_file.exists():
            try:
                compose_files = json.loads(compose_order_file.read_text())
            except Exception:
                pass

        if compose_files:
            # Build dynamic -f flags for all compose files
            f_flags = " ".join(f"-f {f}" for f in compose_files)
            print(f"")
            print(f"   💡 After copying files to your target directory:")
            print(f"      cd /your/target/directory")
            print(f"      docker compose {f_flags} up -d")
            if len(compose_files) > 1:
                print(f"")
                print(f"   📋 Compose files (in order):")
                for f in compose_files:
                    print(f"      • {f}")
            print(f"")
        elif compose_file.exists():
            # Fallback for old backups without compose_order.json
            print(f"")
            print(f"   💡 After copying files to your target directory:")
            print(f"      cd /your/target/directory")
            print(f"      docker compose up -d")
            print(f"")
        else:
            print(f"   ⚠️  No docker-compose.yml found in backup")
            print(f"   Review the inspect files in: {recipe_dir}")
            print(f"   Recreate containers with appropriate 'docker run' options")
