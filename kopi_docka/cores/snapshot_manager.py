#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        snapshot_manager.py
# @module:      kopi_docka.cores.snapshot_manager
# @description: Interactive snapshot management wizard (manage, delete, pin, retention)
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Interactive snapshot management wizard for Kopi-Docka.

Provides a menu-driven interface for managing Kopia snapshots:
delete, pin/unpin, retention adjustment, prune empty sessions,
and maintenance. Follows the same UX pattern as RestoreManager.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from ..helpers.logging import get_logger
from ..helpers.config import Config
from ..helpers.ui_utils import (
    print_header,
    print_success,
    print_error,
    print_info,
    print_warning,
)
from ..cores.repository_manager import KopiaRepository
from ..cores.kopia_policy_manager import KopiaPolicyManager

logger = get_logger(__name__)
console = Console()


class SnapshotManager:
    """Interactive snapshot management wizard."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.repo = KopiaRepository(config)
        self.policy = KopiaPolicyManager(self.repo)

    # =========================================================================
    # Public entry points
    # =========================================================================

    def interactive_manage(self) -> None:
        """Main entry point: show management menu and dispatch to sub-wizards."""
        print_header("Kopi-Docka Snapshot Manager", "")

        if not self.repo.is_connected():
            print_error("Repository not connected. Run 'kopi-docka setup' first.")
            return

        self._show_main_menu()

    def cmd_delete(self, snapshot_id: str, force: bool = False) -> None:
        """Non-interactive delete: used by 'admin snapshot delete <id>'."""
        if not force:
            confirm = input(f"Delete snapshot {snapshot_id}? (yes/no): ").strip().lower()
            if confirm != "yes":
                print_info("Aborted.")
                return
        try:
            self.repo.delete_snapshot(snapshot_id)
            print_success(f"Snapshot {snapshot_id} deleted.")
        except Exception as e:
            print_error(f"Delete failed: {e}")

    def cmd_pin(self, snapshot_id: str) -> None:
        """Non-interactive pin."""
        if self.repo.pin_snapshot(snapshot_id):
            print_success(f"Snapshot {snapshot_id} pinned.")
        else:
            print_error(f"Failed to pin snapshot {snapshot_id}.")

    def cmd_unpin(self, snapshot_id: str) -> None:
        """Non-interactive unpin."""
        if self.repo.unpin_snapshot(snapshot_id):
            print_success(f"Snapshot {snapshot_id} unpinned.")
        else:
            print_error(f"Failed to unpin snapshot {snapshot_id}.")

    def cmd_retention_show(self) -> None:
        """Show current retention from Kopia global policy + local config."""
        self._display_retention()

    def cmd_retention_set(
        self,
        latest: int,
        hourly: int,
        daily: int,
        weekly: int,
        monthly: int,
        annual: int,
    ) -> None:
        """Non-interactive retention update (Kopia policy + config file)."""
        ok = self.policy.update_global_retention(latest, hourly, daily, weekly, monthly, annual)
        if ok:
            self.config.update_retention(latest, hourly, daily, weekly, monthly, annual)
            print_success("Retention policy updated in Kopia and config.")
        else:
            print_error("Failed to update Kopia retention policy.")

    def cmd_prune_empty(self, dry_run: bool = False) -> None:
        """Expire snapshots (apply retention) with optional dry-run preview."""
        if dry_run:
            print_info("Dry-run: the following snapshots would be expired by current retention.")
            snaps = self.repo.list_snapshots()
            self._print_snapshot_table(snaps, title="All snapshots (dry-run view)")
            print_info("Run without --dry-run to apply retention and remove expired snapshots.")
            return
        if self.repo.expire_snapshots():
            print_success("Expired snapshots pruned.")
        else:
            print_error("Expiration failed or nothing to prune.")

    def cmd_maintenance(self, full: bool = False) -> None:
        """Run Kopia maintenance."""
        mode = "full" if full else "quick"
        print_info(f"Running {mode} maintenance…")
        try:
            self.repo.maintenance_run(full=full)
            print_success(f"Maintenance ({mode}) completed.")
        except Exception as e:
            print_error(f"Maintenance failed: {e}")

    # =========================================================================
    # Interactive menu
    # =========================================================================

    def _show_main_menu(self) -> None:
        while True:
            console.print()
            console.print(
                Panel.fit(
                    "[bold cyan]What would you like to do?[/bold cyan]\n\n"
                    "  [cyan]1[/cyan]  List snapshots\n"
                    "  [cyan]2[/cyan]  Delete a snapshot\n"
                    "  [cyan]3[/cyan]  Pin a snapshot\n"
                    "  [cyan]4[/cyan]  Unpin a snapshot\n"
                    "  [cyan]5[/cyan]  View / change retention policy\n"
                    "  [cyan]6[/cyan]  Prune expired snapshots\n"
                    "  [cyan]7[/cyan]  Run maintenance\n"
                    "  [cyan]q[/cyan]  Quit",
                    title="Snapshot Manager",
                    border_style="cyan",
                )
            )

            choice = input("\nSelect option (1-7, q): ").strip().lower()

            if choice == "q":
                print_info("Exiting snapshot manager.")
                return
            elif choice == "1":
                self._wizard_list()
            elif choice == "2":
                self._wizard_delete()
            elif choice == "3":
                self._wizard_pin()
            elif choice == "4":
                self._wizard_unpin()
            elif choice == "5":
                self._wizard_retention()
            elif choice == "6":
                self._wizard_prune_empty()
            elif choice == "7":
                self._wizard_maintenance()
            else:
                print_warning("Invalid choice. Enter 1-7 or 'q'.")

    # =========================================================================
    # Sub-wizards
    # =========================================================================

    def _wizard_list(self) -> None:
        print_info("Loading snapshots…")
        snaps = self.repo.list_snapshots()
        if not snaps:
            print_warning("No snapshots found in repository.")
            return
        self._print_snapshot_table(snaps)

    def _wizard_delete(self) -> None:
        print_info("Loading snapshots…")
        snaps = self.repo.list_snapshots()
        if not snaps:
            print_warning("No snapshots found.")
            return

        self._print_snapshot_table(snaps)

        choice = input("\nEnter snapshot number to delete (or 'q' to cancel): ").strip().lower()
        if choice == "q":
            return

        snap = self._pick_snapshot(snaps, choice)
        if snap is None:
            return

        sid = snap["id"]
        confirm = input(
            f"\nDelete snapshot [bold]{sid[:16]}…[/bold]? This cannot be undone. (yes/no): "
        ).strip().lower()
        if confirm != "yes":
            print_info("Aborted.")
            return

        try:
            self.repo.delete_snapshot(sid)
            print_success(f"Snapshot {sid[:16]}… deleted.")
        except Exception as e:
            print_error(f"Delete failed: {e}")

    def _wizard_pin(self) -> None:
        print_info("Loading snapshots…")
        snaps = self.repo.list_snapshots()
        if not snaps:
            print_warning("No snapshots found.")
            return

        self._print_snapshot_table(snaps)

        choice = input("\nEnter snapshot number to pin (or 'q' to cancel): ").strip().lower()
        if choice == "q":
            return

        snap = self._pick_snapshot(snaps, choice)
        if snap is None:
            return

        if self.repo.pin_snapshot(snap["id"]):
            print_success(f"Snapshot {snap['id'][:16]}… pinned.")
        else:
            print_error("Pin failed.")

    def _wizard_unpin(self) -> None:
        print_info("Loading snapshots…")
        snaps = self.repo.list_snapshots()
        if not snaps:
            print_warning("No snapshots found.")
            return

        self._print_snapshot_table(snaps)

        choice = input("\nEnter snapshot number to unpin (or 'q' to cancel): ").strip().lower()
        if choice == "q":
            return

        snap = self._pick_snapshot(snaps, choice)
        if snap is None:
            return

        if self.repo.unpin_snapshot(snap["id"]):
            print_success(f"Snapshot {snap['id'][:16]}… unpinned.")
        else:
            print_error("Unpin failed.")

    def _wizard_retention(self) -> None:
        self._display_retention()

        change = input("\nChange retention? (yes/no): ").strip().lower()
        if change != "yes":
            return

        print_info("Enter new values (press Enter to keep current).")
        current = self._current_retention_from_config()

        def _ask(label: str, key: str) -> int:
            cur = current.get(key, 0)
            raw = input(f"  {label} [{cur}]: ").strip()
            if not raw:
                return cur
            try:
                return int(raw)
            except ValueError:
                print_warning(f"Invalid value, keeping {cur}.")
                return cur

        latest = _ask("Latest", "latest")
        hourly = _ask("Hourly", "hourly")
        daily = _ask("Daily", "daily")
        weekly = _ask("Weekly", "weekly")
        monthly = _ask("Monthly", "monthly")
        annual = _ask("Annual", "annual")

        console.print()
        console.print(
            Panel.fit(
                f"  latest: {latest}  hourly: {hourly}  daily: {daily}\n"
                f"  weekly: {weekly}  monthly: {monthly}  annual: {annual}",
                title="New retention policy",
                border_style="yellow",
            )
        )
        confirm = input("Apply? (yes/no): ").strip().lower()
        if confirm != "yes":
            print_info("Aborted.")
            return

        ok = self.policy.update_global_retention(latest, hourly, daily, weekly, monthly, annual)
        if ok:
            self.config.update_retention(latest, hourly, daily, weekly, monthly, annual)
            print_success("Retention policy updated.")
        else:
            print_error("Failed to update Kopia retention policy.")

    def _wizard_prune_empty(self) -> None:
        print_info("Applying retention policy and expiring old snapshots…")
        confirm = input("Proceed? (yes/no): ").strip().lower()
        if confirm != "yes":
            print_info("Aborted.")
            return
        if self.repo.expire_snapshots():
            print_success("Expired snapshots pruned.")
        else:
            print_error("Expiration failed or nothing to prune.")

    def _wizard_maintenance(self) -> None:
        full = input("Run full maintenance? (yes/no, default: no): ").strip().lower()
        full_flag = full == "yes"
        mode = "full" if full_flag else "quick"
        print_info(f"Running {mode} maintenance…")
        try:
            self.repo.maintenance_run(full=full_flag)
            print_success(f"Maintenance ({mode}) completed.")
        except Exception as e:
            print_error(f"Maintenance failed: {e}")

    # =========================================================================
    # Display helpers
    # =========================================================================

    def _print_snapshot_table(
        self,
        snaps: List[Dict[str, Any]],
        title: str = "Repository Snapshots",
    ) -> None:
        table = Table(
            title=title,
            box=box.ROUNDED,
            border_style="cyan",
            title_style="bold cyan",
            show_lines=False,
        )
        table.add_column("#", justify="right", style="dim", width=4)
        table.add_column("ID (short)", style="cyan", width=18)
        table.add_column("Timestamp", width=20)
        table.add_column("Path")
        table.add_column("Size", justify="right", width=10)
        table.add_column("Tags", style="dim")

        for i, snap in enumerate(snaps, start=1):
            ts = self._fmt_timestamp(snap.get("timestamp", ""))
            size = self._fmt_size(snap.get("size", 0))
            sid = snap.get("id", "")[:16] + "…"
            path = snap.get("path", "-")
            tags_str = ", ".join(
                f"{k}={v}" for k, v in (snap.get("tags") or {}).items()
            ) or "-"
            table.add_row(str(i), sid, ts, path, size, tags_str)

        console.print()
        console.print(table)

    def _display_retention(self) -> None:
        current = self._current_retention_from_config()
        kopia_policy = self.policy.get_global_policy()
        kopia_ret = (kopia_policy.get("retentionPolicy") or {})

        panel_lines = (
            "[bold]Config file:[/bold]\n"
            f"  latest={current.get('latest', '?')}  "
            f"hourly={current.get('hourly', '?')}  "
            f"daily={current.get('daily', '?')}\n"
            f"  weekly={current.get('weekly', '?')}  "
            f"monthly={current.get('monthly', '?')}  "
            f"annual={current.get('annual', '?')}\n"
        )
        if kopia_ret:
            panel_lines += (
                "\n[bold]Kopia global policy:[/bold]\n"
                f"  keepLatest={kopia_ret.get('keepLatest', '?')}  "
                f"keepHourly={kopia_ret.get('keepHourly', '?')}  "
                f"keepDaily={kopia_ret.get('keepDaily', '?')}\n"
                f"  keepWeekly={kopia_ret.get('keepWeekly', '?')}  "
                f"keepMonthly={kopia_ret.get('keepMonthly', '?')}  "
                f"keepAnnual={kopia_ret.get('keepAnnual', '?')}"
            )
        else:
            panel_lines += "\n[dim]Kopia policy unavailable (repository not connected?)[/dim]"

        console.print()
        console.print(
            Panel(panel_lines, title="Retention Policy", border_style="cyan", expand=False)
        )

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _pick_snapshot(
        self, snaps: List[Dict[str, Any]], raw_choice: str
    ) -> Optional[Dict[str, Any]]:
        try:
            idx = int(raw_choice) - 1
            if 0 <= idx < len(snaps):
                return snaps[idx]
        except ValueError:
            pass
        print_error(f"Invalid selection: '{raw_choice}'. Enter a number from the list.")
        return None

    def _current_retention_from_config(self) -> Dict[str, int]:
        return {
            "latest": self.config.getint("retention", "latest", 10),
            "hourly": self.config.getint("retention", "hourly", 0),
            "daily": self.config.getint("retention", "daily", 7),
            "weekly": self.config.getint("retention", "weekly", 4),
            "monthly": self.config.getint("retention", "monthly", 12),
            "annual": self.config.getint("retention", "annual", 3),
        }

    @staticmethod
    def _fmt_timestamp(ts: str) -> str:
        if not ts:
            return "-"
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return ts[:19]

    @staticmethod
    def _fmt_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "-"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"
