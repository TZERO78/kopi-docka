################################################################################
# KOPI-DOCKA
#
# @file:        service_commands.py
# @module:      kopi_docka.commands
# @description: Service management commands
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Service management commands."""

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ..helpers import get_logger
from ..cores import KopiDockaService, ServiceConfig, write_systemd_units, ServiceHelper

logger = get_logger(__name__)
console = Console()


# -------------------------
# Helper Functions
# -------------------------


def confirm_action(message: str, default_no: bool = True) -> bool:
    """
    Ask user for yes/no confirmation with clear options.

    Args:
        message: Question to ask
        default_no: If True, default is No (shown as [y/N])

    Returns:
        bool: True if user confirmed, False otherwise
    """
    if default_no:
        prompt = f"{message} [y/N]: "
    else:
        prompt = f"{message} [Y/n]: "

    response = console.input(f"[cyan]{prompt}[/cyan]").strip().lower()

    if response in ("y", "yes"):
        return True
    elif response in ("n", "no"):
        return False
    else:
        # Empty = use default
        return not default_no


# -------------------------
# Commands
# -------------------------


def cmd_daemon(
    interval_minutes: Optional[int] = None,
    backup_cmd: str = "/usr/bin/env kopi-docka backup",
    log_level: str = "INFO",
):
    """Run the systemd-friendly daemon (service)."""
    cfg = ServiceConfig(
        backup_cmd=backup_cmd,
        interval_minutes=interval_minutes,
        log_level=log_level,
    )
    svc = KopiDockaService(cfg)
    rc = svc.start()
    raise typer.Exit(code=rc)


def cmd_write_units(output_dir: Path = Path("/etc/systemd/system")):
    """Write example systemd service and timer units."""
    try:
        write_systemd_units(output_dir)
        typer.echo(f"✓ Unit files written to: {output_dir}")
        typer.echo("Enable with: sudo systemctl enable --now kopi-docka.timer")
    except Exception as e:
        typer.echo(f"Failed to write units: {e}")
        raise typer.Exit(code=1)


def cmd_manage():
    """Interactive service management wizard."""
    # Check root privileges
    if os.geteuid() != 0:
        console.print()
        console.print(
            Panel.fit(
                "[red]Root privileges required[/red]\n\n"
                "This command requires root privileges for systemctl operations.\n"
                "Please run with sudo:\n\n"
                "[cyan]sudo kopi-docka advanced service manage[/cyan]",
                title="[bold red]Permission Denied[/bold red]",
                border_style="red",
            )
        )
        console.print()
        raise typer.Exit(code=13)

    # Initialize ServiceHelper
    helper = ServiceHelper()

    # Check if units exist, offer to create if missing
    if not helper.units_exist():
        console.print()
        console.print(
            Panel.fit(
                "[yellow]Systemd units not found[/yellow]\n\n"
                "The kopi-docka systemd units are not yet installed.\n"
                "Would you like to create them now?",
                title="[bold yellow]Installation Required[/bold yellow]",
                border_style="yellow",
            )
        )
        console.print()

        if confirm_action("Create units?", default_no=False):
            try:
                write_systemd_units()
                console.print("[green]✓[/green] Units created successfully")
                console.print()
                # Reload systemd
                if helper.reload_daemon():
                    console.print("[green]✓[/green] Systemd reloaded")
                console.print()
            except Exception as e:
                console.print(f"[red]✗[/red] Error creating units: {e}")
                raise typer.Exit(code=1)
        else:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(code=0)

    # Main menu loop
    while True:
        console.print()
        console.print(
            Panel.fit(
                "[bold cyan]KOPI-DOCKA SERVICE MANAGEMENT[/bold cyan]\n\n"
                "[1] Show Status\n"
                "[2] Configure Timer\n"
                "[3] View Logs\n"
                "[4] Control Service\n"
                "[0] Exit",
                border_style="cyan",
            )
        )
        console.print()

        choice = console.input("[cyan]Selection:[/cyan] ").strip()

        if choice == "0":
            console.print("[cyan]Goodbye![/cyan]")
            break
        elif choice == "1":
            _show_status_dashboard(helper)
        elif choice == "2":
            _configure_timer(helper)
        elif choice == "3":
            _show_logs(helper)
        elif choice == "4":
            _control_service(helper)
        else:
            console.print("[yellow]Invalid selection. Please choose 0-4.[/yellow]")


def _show_status_dashboard(helper: ServiceHelper):
    """Show service status dashboard."""
    console.print()
    console.print("[bold]SERVICE STATUS[/bold]")
    console.print("-" * 60)

    # Get status information
    service_status = helper.get_service_status()
    timer_status = helper.get_timer_status()
    lock_status = helper.get_lock_status()
    backup_info = helper.get_last_backup_info()
    config_validation = helper.validate_service_configuration()

    # 1. Health Status Panel (Top Priority)
    health = config_validation["health"]
    health_message = config_validation["message"]

    if health == "healthy":
        health_icon = "✓"
        health_color = "green"
        border_color = "green"
    elif health == "warning":
        health_icon = "⚠"
        health_color = "yellow"
        border_color = "yellow"
    elif health == "error":
        health_icon = "✗"
        health_color = "red"
        border_color = "red"
    else:
        health_icon = "?"
        health_color = "dim"
        border_color = "dim"

    # Build health panel content
    health_content = f"[{health_color}]{health_icon} {health_message}[/{health_color}]"

    # Add timer mode info if healthy
    if health == "healthy":
        health_content += "\n[dim]Timer-triggered mode[/dim]"

    # Add next backup if available
    if timer_status.next_run:
        health_content += f"\n[bold]Next:[/bold] {timer_status.next_run}"

    console.print(
        Panel.fit(
            health_content,
            title=f"[bold {health_color}]System Health[/bold {health_color}]",
            border_style=border_color,
        )
    )
    console.print()

    # 2. Service/Timer Status Table with Notes
    status_table = Table(box=box.SIMPLE, show_header=True)
    status_table.add_column("Component", style="cyan", width=20)
    status_table.add_column("Active", width=10)
    status_table.add_column("Enabled", width=10)
    status_table.add_column("Notes", style="dim")

    # Service row with explanation
    service_active = "[green]Active[/green]" if service_status.active else "[dim]Inactive[/dim]"
    service_enabled = "[green]Enabled[/green]" if service_status.enabled else "[dim]Disabled[/dim]"

    # Service notes based on configuration
    if service_status.failed:
        service_notes = "[red]Failed[/red]"
    elif not config_validation["service_enabled"]:
        service_notes = "[green]✓ Correct (timer-triggered)[/green]"
    else:
        service_notes = "[yellow]⚠ Should be disabled[/yellow]"

    status_table.add_row("kopi-docka.service", service_active, service_enabled, service_notes)

    # Timer row with explanation
    timer_active = "[green]Active[/green]" if timer_status.active else "[dim]Inactive[/dim]"
    timer_enabled = "[green]Enabled[/green]" if timer_status.enabled else "[dim]Disabled[/dim]"

    # Timer notes based on configuration
    if config_validation["timer_enabled"]:
        timer_notes = "[green]✓ Correct[/green]"
    else:
        timer_notes = "[yellow]⚠ Should be enabled[/yellow]"

    status_table.add_row("kopi-docka.timer", timer_active, timer_enabled, timer_notes)

    console.print(status_table)
    console.print()

    # 3. Current Schedule
    current_schedule = helper.get_current_schedule()
    if current_schedule:
        console.print(f"[bold]Schedule:[/bold] {current_schedule}")
        console.print()

    # 4. Last Backup Info
    if backup_info.timestamp:
        status_color = (
            "green"
            if backup_info.status == "success"
            else "red" if backup_info.status == "failed" else "yellow"
        )
        status_text = (
            "Successful"
            if backup_info.status == "success"
            else "Failed" if backup_info.status == "failed" else "Unknown"
        )

        console.print(
            f"[bold]Last Backup:[/bold] {backup_info.timestamp} - [{status_color}]{status_text}[/{status_color}]"
        )
        console.print()

    # 5. Lock File Status
    if lock_status["exists"]:
        if lock_status["process_running"]:
            console.print(f"[yellow]⚠[/yellow] Lock file active (PID: {lock_status['pid']})")
        else:
            console.print(
                f"[dim]Stale lock file (PID: {lock_status['pid']}) - use Control Service to remove[/dim]"
            )
        console.print()

    # 6. Configuration Issues (if any)
    if config_validation["issues"]:
        console.print(
            Panel.fit(
                "[yellow]Configuration Issues:[/yellow]\n"
                + "\n".join([f"  • {issue}" for issue in config_validation["issues"]])
                + "\n\n[yellow]Recommendations:[/yellow]\n"
                + "\n".join([f"  • {rec}" for rec in config_validation["recommendations"]])
                + "\n\n[bold]Fix:[/bold] Control Service → [7] Fix Configuration",
                title="[yellow]⚠ Needs Attention[/yellow]",
                border_style="yellow",
            )
        )
        console.print()

    # 7. Always-Visible Explanation
    console.print(
        Panel.fit(
            "[bold]Timer-Triggered Mode[/bold] (Recommended)\n\n"
            "[cyan]Service:[/cyan] disabled = starts only when timer triggers it\n"
            "[cyan]Timer:[/cyan]   enabled  = schedules automatic backups\n\n"
            "[dim]This prevents restart loops and lock file issues.[/dim]",
            title="[cyan]ℹ️  How It Works[/cyan]",
            border_style="cyan",
        )
    )
    console.print()

    console.input("[dim]Press Enter to continue...[/dim]")


def _configure_timer(helper: ServiceHelper):
    """Configure timer schedule."""
    console.print()
    console.print("[bold]CONFIGURE TIMER[/bold]")
    console.print("-" * 60)

    # Show current schedule
    current = helper.get_current_schedule()
    if current:
        console.print(f"[bold]Current Schedule:[/bold] {current}")
        console.print()

    while True:
        console.print("[1] 02:00 (Default)")
        console.print("[2] 03:00")
        console.print("[3] 04:00")
        console.print("[4] 23:00")
        console.print("[5] Custom Time (HH:MM)")
        console.print("[6] Advanced (OnCalendar)")
        console.print("[0] Back")
        console.print()

        choice = console.input("[cyan]Selection:[/cyan] ").strip()

        new_schedule = None

        if choice == "0":
            break
        elif choice == "1":
            new_schedule = "*-*-* 02:00:00"
        elif choice == "2":
            new_schedule = "*-*-* 03:00:00"
        elif choice == "3":
            new_schedule = "*-*-* 04:00:00"
        elif choice == "4":
            new_schedule = "*-*-* 23:00:00"
        elif choice == "5":
            # Custom time input
            time_input = console.input("[cyan]Enter time (HH:MM):[/cyan] ").strip()
            if helper.validate_time_format(time_input):
                new_schedule = f"*-*-* {time_input}:00"
            else:
                console.print("[red]✗[/red] Invalid format. Please use HH:MM (e.g. 14:30)")
                continue
        elif choice == "6":
            # Advanced OnCalendar input
            console.print()
            console.print("[dim]Examples:[/dim]")
            console.print("[dim]  *-*-* 03:00:00              (Daily at 03:00)[/dim]")
            console.print("[dim]  Mon *-*-* 02:00:00          (Mondays at 02:00)[/dim]")
            console.print("[dim]  *-*-* 00,06,12,18:00:00     (Every 6 hours)[/dim]")
            console.print()
            calendar_input = console.input("[cyan]Enter OnCalendar:[/cyan] ").strip()
            if helper.validate_oncalendar(calendar_input):
                new_schedule = calendar_input
            else:
                console.print("[red]✗[/red] Invalid OnCalendar syntax")
                continue
        else:
            console.print("[yellow]Invalid selection[/yellow]")
            continue

        # Confirm changes
        if new_schedule:
            console.print()
            console.print(f"[bold]New Schedule:[/bold] {new_schedule}")
            console.print()

            if confirm_action("Apply changes?"):
                if helper.edit_timer_schedule(new_schedule):
                    console.print("[green]✓[/green] Timer updated successfully")

                    # Show next run time
                    timer_status = helper.get_timer_status()
                    if timer_status.next_run:
                        console.print(f"[green]✓[/green] Next run: {timer_status.next_run}")
                    console.print()
                    console.input("[dim]Press Enter to continue...[/dim]")
                    break
                else:
                    console.print("[red]✗[/red] Error updating timer")
                    console.print()
            else:
                console.print("[yellow]Changes cancelled[/yellow]")
                console.print()


def _show_logs(helper: ServiceHelper):
    """Show logs with various filters."""
    console.print()
    console.print("[bold]VIEW LOGS[/bold]")
    console.print("-" * 60)

    while True:
        console.print("[1] Last 20 Lines")
        console.print("[2] Last 50 Lines")
        console.print("[3] Last Hour")
        console.print("[4] Errors Only")
        console.print("[5] Today")
        console.print("[0] Back")
        console.print()

        choice = console.input("[cyan]Selection:[/cyan] ").strip()

        mode = None
        lines = 20

        if choice == "0":
            break
        elif choice == "1":
            mode = "last"
            lines = 20
        elif choice == "2":
            mode = "last"
            lines = 50
        elif choice == "3":
            mode = "hour"
        elif choice == "4":
            mode = "errors"
        elif choice == "5":
            mode = "today"
        else:
            console.print("[yellow]Invalid selection[/yellow]")
            continue

        # Get logs
        console.print()
        console.print(f"[bold cyan]Logs ({mode}):[/bold cyan]")
        console.print("-" * 60)

        log_lines = helper.get_logs(mode=mode, lines=lines)

        for line in log_lines:
            # Simple syntax highlighting
            if "ERROR" in line or "error" in line or "failed" in line:
                console.print(f"[red]{line}[/red]")
            elif "WARNING" in line or "warning" in line:
                console.print(f"[yellow]{line}[/yellow]")
            elif "SUCCESS" in line or "success" in line or "finished successfully" in line:
                console.print(f"[green]{line}[/green]")
            else:
                console.print(line)

        console.print()
        console.input("[dim]Press Enter to continue...[/dim]")
        break


def _control_service(helper: ServiceHelper):
    """Control service actions."""
    console.print()
    console.print("[bold]CONTROL SERVICE[/bold]")
    console.print("-" * 60)

    while True:
        console.print("[1] Start Backup Now")
        console.print("[2] Restart Service")
        console.print("[3] Stop Service")
        console.print("[4] Enable Timer")
        console.print("[5] Disable Timer")
        console.print("[6] Remove Stale Lock File")
        console.print("[7] Fix Configuration (Timer-Triggered Mode)")
        console.print("[0] Back")
        console.print()

        choice = console.input("[cyan]Selection:[/cyan] ").strip()

        action = None
        unit = "service"
        confirm_required = False
        confirm_msg = ""

        if choice == "0":
            break
        elif choice == "1":
            # Start backup now - use one-shot backup service
            console.print()
            console.print("[cyan]Starting backup...[/cyan]")
            console.print("[dim]Using kopi-docka-backup.service (one-shot)[/dim]")
            console.print()

            if helper.start_backup_now():
                console.print("[green]✓ Backup started successfully[/green]")
                console.print()
                console.print("[dim]View progress:[/dim]")
                console.print("  [cyan]journalctl -u kopi-docka-backup.service -f[/cyan]")
                console.print()

                # Wait briefly and check status
                console.print("[dim]Waiting for backup to complete (30s max)...[/dim]")
                import time

                for i in range(30):
                    time.sleep(1)
                    status = helper.get_backup_service_status()
                    if not status["active"]:
                        # Backup completed
                        if status["result"] == "success":
                            console.print("[green]✓ Backup completed successfully![/green]")
                        elif status["result"] == "failed":
                            console.print("[red]✗ Backup failed[/red]")
                            console.print("[yellow]Check logs for details:[/yellow]")
                            console.print("  [cyan]journalctl -u kopi-docka-backup.service[/cyan]")
                        break
                else:
                    # Still running after 30s
                    console.print("[yellow]⏳ Backup still running...[/yellow]")
                    console.print("[dim]It will continue in the background.[/dim]")

                console.print()
                console.input("[dim]Press Enter to continue...[/dim]")
            else:
                console.print("[red]✗ Error starting backup[/red]")
                console.print("[yellow]Check logs for details:[/yellow]")
                console.print("  [cyan]journalctl -u kopi-docka-backup.service[/cyan]")
                console.print()
                console.input("[dim]Press Enter to continue...[/dim]")
            continue  # Skip the rest of the action logic
        elif choice == "2":
            action = "restart"
            unit = "service"
        elif choice == "3":
            action = "stop"
            unit = "service"
            confirm_required = True
            confirm_msg = "Really stop service?"
        elif choice == "4":
            action = "enable"
            unit = "timer"
            # Also start the timer
            console.print("[cyan]Enabling timer...[/cyan]")
        elif choice == "5":
            action = "disable"
            unit = "timer"
            confirm_required = True
            confirm_msg = "Really disable timer?"
        elif choice == "6":
            # Remove stale lock file
            console.print()
            console.print("[cyan]Checking for stale lock file...[/cyan]")
            lock_status = helper.get_lock_status()

            if not lock_status["exists"]:
                console.print("[green]✓[/green] No lock file found")
                console.print()
                console.input("[dim]Press Enter to continue...[/dim]")
                continue

            if lock_status["process_running"]:
                console.print(
                    Panel.fit(
                        f"[red]Cannot Remove Active Lock[/red]\n\n"
                        f"The lock file belongs to a running process (PID: {lock_status['pid']}).\n\n"
                        f"[yellow]If you believe this is the daemon service, stop it first:[/yellow]\n"
                        f"  • Option [2] Restart Service, or\n"
                        f"  • Option [3] Stop Service\n\n"
                        f"[dim]Only stale locks from dead processes can be removed.[/dim]",
                        title="[red]Lock Active[/red]",
                        border_style="red",
                    )
                )
                console.print()
                console.input("[dim]Press Enter to continue...[/dim]")
                continue

            # Lock exists but process is not running - stale lock
            console.print(
                Panel.fit(
                    f"[yellow]Stale Lock Found[/yellow]\n\n"
                    f"PID: {lock_status['pid']} (process not running)\n\n"
                    f"[dim]This lock can be safely removed.[/dim]",
                    title="[yellow]Stale Lock[/yellow]",
                    border_style="yellow",
                )
            )
            console.print()

            if confirm_action("Remove stale lock file?", default_no=False):
                if helper.remove_stale_lock():
                    console.print("[green]✓[/green] Stale lock file removed")
                else:
                    console.print("[red]✗[/red] Failed to remove lock file")
                console.print()
                console.input("[dim]Press Enter to continue...[/dim]")
                continue
            else:
                console.print("[yellow]Cancelled[/yellow]")
                console.print()
                continue
        elif choice == "7":
            # Fix Configuration - Set up timer-triggered mode
            console.print()
            console.print("[cyan]Fix Configuration[/cyan]")
            console.print()

            # Check current configuration
            config_validation = helper.validate_service_configuration()

            if config_validation["health"] == "healthy":
                console.print("[green]✓[/green] Configuration is already correct!")
                console.print()
                console.print("Current setup:")
                console.print("  • Service: disabled (timer-triggered)")
                console.print("  • Timer: enabled (schedules backups)")
                console.print()
                console.input("[dim]Press Enter to continue...[/dim]")
                continue

            # Show what will be done
            console.print(
                Panel.fit(
                    "[bold]This will configure timer-triggered mode:[/bold]\n\n"
                    "  1. Stop kopi-docka.service (if running)\n"
                    "  2. Disable kopi-docka.service (prevents restart loops)\n"
                    "  3. Enable kopi-docka.timer (schedules backups)\n"
                    "  4. Start kopi-docka.timer (if not running)\n"
                    "  5. Remove stale lock files\n\n"
                    "[dim]This is the recommended configuration for automatic backups.[/dim]",
                    title="[cyan]Configuration Fix[/cyan]",
                    border_style="cyan",
                )
            )
            console.print()

            if confirm_action("Apply this configuration?", default_no=False):
                console.print()
                console.print("[cyan]Applying configuration...[/cyan]")

                if helper.fix_service_configuration():
                    console.print("[green]✓[/green] Configuration fixed successfully!")
                    console.print()

                    # Show new status
                    timer_status = helper.get_timer_status()
                    if timer_status.next_run:
                        console.print(f"[green]✓[/green] Next backup: {timer_status.next_run}")
                    console.print()

                    console.print("[bold]New configuration:[/bold]")
                    console.print("  • Service: disabled (timer-triggered)")
                    console.print("  • Timer: enabled (schedules backups)")
                else:
                    console.print("[red]✗[/red] Some configuration steps failed")
                    console.print("[yellow]Check logs for details[/yellow]")

                console.print()
                console.input("[dim]Press Enter to continue...[/dim]")
                continue
            else:
                console.print("[yellow]Cancelled[/yellow]")
                console.print()
                continue
        else:
            console.print("[yellow]Invalid selection[/yellow]")
            continue

        # Confirm if needed
        if confirm_required:
            console.print()
            if not confirm_action(confirm_msg):
                console.print("[yellow]Cancelled[/yellow]")
                console.print()
                continue

        # Execute action
        if action:
            if helper.control_service(action, unit):
                console.print(f"[green]✓[/green] {action} {unit} successful")

                # If enabling timer, also start it
                if action == "enable" and unit == "timer":
                    if helper.control_service("start", "timer"):
                        console.print("[green]✓[/green] Timer started")

                # Show updated status
                console.print()
                if unit == "service":
                    status = helper.get_service_status()
                    console.print(
                        f"Service Status: {'[green]Active[/green]' if status.active else '[dim]Inactive[/dim]'}"
                    )
                else:
                    status = helper.get_timer_status()
                    console.print(
                        f"Timer Status: {'[green]Active[/green]' if status.active else '[dim]Inactive[/dim]'}"
                    )

                console.print()
                console.input("[dim]Press Enter to continue...[/dim]")
                break
            else:
                console.print(f"[red]✗[/red] Error executing {action} {unit}")
                console.print("[dim]Check logs for details[/dim]")
                console.print()


# -------------------------
# Registration
# -------------------------


def register(app: typer.Typer):
    """Register all service commands."""

    @app.command("daemon")
    def _daemon_cmd(
        interval_minutes: Optional[int] = typer.Option(
            None, "--interval-minutes", help="Run backup every N minutes"
        ),
        backup_cmd: str = typer.Option("/usr/bin/env kopi-docka backup", "--backup-cmd"),
        log_level: str = typer.Option("INFO", "--log-level"),
    ):
        """Run the systemd-friendly daemon (service)."""
        cmd_daemon(interval_minutes, backup_cmd, log_level)

    @app.command("write-units")
    def _write_units_cmd(
        output_dir: Path = typer.Option(Path("/etc/systemd/system"), "--output-dir"),
    ):
        """Write example systemd service and timer units."""
        cmd_write_units(output_dir)
