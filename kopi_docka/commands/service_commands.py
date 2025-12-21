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
        console.print(Panel.fit(
            "[red]Root-Rechte erforderlich[/red]\n\n"
            "Dieser Befehl benötigt Root-Rechte für systemctl-Operationen.\n"
            "Bitte mit sudo ausführen:\n\n"
            "[cyan]sudo kopi-docka admin service manage[/cyan]",
            title="[bold red]Keine Berechtigung[/bold red]",
            border_style="red"
        ))
        console.print()
        raise typer.Exit(code=13)

    # Initialize ServiceHelper
    helper = ServiceHelper()

    # Check if units exist, offer to create if missing
    if not helper.units_exist():
        console.print()
        console.print(Panel.fit(
            "[yellow]Systemd-Units nicht gefunden[/yellow]\n\n"
            "Die kopi-docka systemd-Units sind noch nicht installiert.\n"
            "Sollen sie jetzt erstellt werden?",
            title="[bold yellow]Installation erforderlich[/bold yellow]",
            border_style="yellow"
        ))
        console.print()

        response = console.input("[cyan]Units erstellen? [J/n]:[/cyan] ").strip().lower()
        if response in ("", "j", "ja", "y", "yes"):
            try:
                write_systemd_units()
                console.print("[green]✓[/green] Units erfolgreich erstellt")
                console.print()
                # Reload systemd
                if helper.reload_daemon():
                    console.print("[green]✓[/green] Systemd neu geladen")
                console.print()
            except Exception as e:
                console.print(f"[red]✗[/red] Fehler beim Erstellen: {e}")
                raise typer.Exit(code=1)
        else:
            console.print("[yellow]Abgebrochen.[/yellow]")
            raise typer.Exit(code=0)

    # Main menu loop
    while True:
        console.print()
        console.print(Panel.fit(
            "[bold cyan]KOPI-DOCKA SERVICE MANAGEMENT[/bold cyan]\n\n"
            "[1] Status anzeigen\n"
            "[2] Timer konfigurieren\n"
            "[3] Logs anzeigen\n"
            "[4] Service steuern\n"
            "[0] Beenden",
            border_style="cyan"
        ))
        console.print()

        choice = console.input("[cyan]Auswahl:[/cyan] ").strip()

        if choice == "0":
            console.print("[cyan]Auf Wiedersehen![/cyan]")
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
            console.print("[yellow]Ungültige Auswahl. Bitte wählen Sie 0-4.[/yellow]")


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

    # Service/Timer status table
    status_table = Table(box=box.SIMPLE, show_header=True)
    status_table.add_column("Component", style="cyan", width=20)
    status_table.add_column("Active", width=12)
    status_table.add_column("Enabled", width=12)
    status_table.add_column("Status", style="dim")

    # Service row
    service_active = "[green]Aktiv[/green]" if service_status.active else "[dim]Inaktiv[/dim]"
    service_enabled = "[green]Aktiviert[/green]" if service_status.enabled else "[dim]Deaktiviert[/dim]"
    service_extra = "[red]Failed[/red]" if service_status.failed else ""
    status_table.add_row("kopi-docka.service", service_active, service_enabled, service_extra)

    # Timer row
    timer_active = "[green]Aktiv[/green]" if timer_status.active else "[dim]Inaktiv[/dim]"
    timer_enabled = "[green]Aktiviert[/green]" if timer_status.enabled else "[dim]Deaktiviert[/dim]"
    status_table.add_row("kopi-docka.timer", timer_active, timer_enabled, "")

    console.print(status_table)
    console.print()

    # Next backup time
    if timer_status.next_run:
        console.print(Panel.fit(
            f"[bold]Nächstes Backup:[/bold] {timer_status.next_run}\n"
            f"[dim]Zeit bis zum Backup:[/dim] {timer_status.left or 'Unbekannt'}",
            title="[cyan]Timer Info[/cyan]",
            border_style="cyan"
        ))
        console.print()

    # Current schedule
    current_schedule = helper.get_current_schedule()
    if current_schedule:
        console.print(f"[bold]Aktueller Zeitplan:[/bold] {current_schedule}")
        console.print()

    # Last backup info
    if backup_info.timestamp:
        status_color = "green" if backup_info.status == "success" else "red" if backup_info.status == "failed" else "yellow"
        status_text = "Erfolgreich" if backup_info.status == "success" else "Fehlgeschlagen" if backup_info.status == "failed" else "Unbekannt"

        console.print(Panel.fit(
            f"[bold]Letztes Backup:[/bold] {backup_info.timestamp}\n"
            f"[bold]Status:[/bold] [{status_color}]{status_text}[/{status_color}]",
            title="[cyan]Backup Info[/cyan]",
            border_style="cyan"
        ))
        console.print()

    # Lock file status
    if lock_status["exists"]:
        if lock_status["process_running"]:
            console.print(f"[yellow]⚠[/yellow]  Lock-Datei aktiv (PID: {lock_status['pid']})")
        else:
            console.print(f"[dim]Lock-Datei vorhanden, aber Prozess läuft nicht (PID: {lock_status['pid']})[/dim]")
        console.print()

    console.input("[dim]Drücken Sie Enter zum Fortfahren...[/dim]")


def _configure_timer(helper: ServiceHelper):
    """Configure timer schedule."""
    console.print()
    console.print("[bold]TIMER KONFIGURIEREN[/bold]")
    console.print("-" * 60)

    # Show current schedule
    current = helper.get_current_schedule()
    if current:
        console.print(f"[bold]Aktueller Zeitplan:[/bold] {current}")
        console.print()

    while True:
        console.print("[1] 02:00 (Standard)")
        console.print("[2] 03:00")
        console.print("[3] 04:00")
        console.print("[4] 23:00")
        console.print("[5] Eigene Zeit (HH:MM)")
        console.print("[6] Erweitert (OnCalendar)")
        console.print("[0] Zurück")
        console.print()

        choice = console.input("[cyan]Auswahl:[/cyan] ").strip()

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
            time_input = console.input("[cyan]Zeit eingeben (HH:MM):[/cyan] ").strip()
            if helper.validate_time_format(time_input):
                new_schedule = f"*-*-* {time_input}:00"
            else:
                console.print("[red]✗[/red] Ungültiges Format. Bitte HH:MM verwenden (z.B. 14:30)")
                continue
        elif choice == "6":
            # Advanced OnCalendar input
            console.print()
            console.print("[dim]Beispiele:[/dim]")
            console.print("[dim]  *-*-* 03:00:00              (Täglich um 03:00)[/dim]")
            console.print("[dim]  Mon *-*-* 02:00:00          (Montags um 02:00)[/dim]")
            console.print("[dim]  *-*-* 00,06,12,18:00:00     (Alle 6 Stunden)[/dim]")
            console.print()
            calendar_input = console.input("[cyan]OnCalendar eingeben:[/cyan] ").strip()
            if helper.validate_oncalendar(calendar_input):
                new_schedule = calendar_input
            else:
                console.print("[red]✗[/red] Ungültige OnCalendar-Syntax")
                continue
        else:
            console.print("[yellow]Ungültige Auswahl[/yellow]")
            continue

        # Confirm changes
        if new_schedule:
            console.print()
            console.print(f"[bold]Neuer Zeitplan:[/bold] {new_schedule}")
            console.print()
            confirm = console.input("[cyan]Übernehmen? [j/N]:[/cyan] ").strip().lower()

            if confirm in ("j", "ja", "y", "yes"):
                if helper.edit_timer_schedule(new_schedule):
                    console.print("[green]✓[/green] Timer erfolgreich aktualisiert")

                    # Show next run time
                    timer_status = helper.get_timer_status()
                    if timer_status.next_run:
                        console.print(f"[green]✓[/green] Nächster Lauf: {timer_status.next_run}")
                    console.print()
                    console.input("[dim]Drücken Sie Enter zum Fortfahren...[/dim]")
                    break
                else:
                    console.print("[red]✗[/red] Fehler beim Aktualisieren des Timers")
                    console.print()
            else:
                console.print("[yellow]Änderung abgebrochen[/yellow]")
                console.print()


def _show_logs(helper: ServiceHelper):
    """Show logs with various filters."""
    console.print()
    console.print("[bold]LOGS ANZEIGEN[/bold]")
    console.print("-" * 60)

    while True:
        console.print("[1] Letzte 20 Zeilen")
        console.print("[2] Letzte 50 Zeilen")
        console.print("[3] Letzte Stunde")
        console.print("[4] Nur Fehler")
        console.print("[5] Heute")
        console.print("[0] Zurück")
        console.print()

        choice = console.input("[cyan]Auswahl:[/cyan] ").strip()

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
            console.print("[yellow]Ungültige Auswahl[/yellow]")
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
        console.input("[dim]Drücken Sie Enter zum Fortfahren...[/dim]")
        break


def _control_service(helper: ServiceHelper):
    """Control service actions."""
    console.print()
    console.print("[bold]SERVICE STEUERN[/bold]")
    console.print("-" * 60)

    while True:
        console.print("[1] Backup jetzt starten")
        console.print("[2] Service neustarten")
        console.print("[3] Service stoppen")
        console.print("[4] Timer aktivieren (enable)")
        console.print("[5] Timer deaktivieren (disable)")
        console.print("[0] Zurück")
        console.print()

        choice = console.input("[cyan]Auswahl:[/cyan] ").strip()

        action = None
        unit = "service"
        confirm_required = False
        confirm_msg = ""

        if choice == "0":
            break
        elif choice == "1":
            # Start backup now
            action = "start"
            unit = "service"
            console.print("[cyan]Starte Backup...[/cyan]")
        elif choice == "2":
            action = "restart"
            unit = "service"
        elif choice == "3":
            action = "stop"
            unit = "service"
            confirm_required = True
            confirm_msg = "Service wirklich stoppen?"
        elif choice == "4":
            action = "enable"
            unit = "timer"
            # Also start the timer
            console.print("[cyan]Aktiviere Timer...[/cyan]")
        elif choice == "5":
            action = "disable"
            unit = "timer"
            confirm_required = True
            confirm_msg = "Timer wirklich deaktivieren?"
        else:
            console.print("[yellow]Ungültige Auswahl[/yellow]")
            continue

        # Confirm if needed
        if confirm_required:
            console.print()
            confirm = console.input(f"[yellow]{confirm_msg} [j/N]:[/yellow] ").strip().lower()
            if confirm not in ("j", "ja", "y", "yes"):
                console.print("[yellow]Abgebrochen[/yellow]")
                console.print()
                continue

        # Execute action
        if action:
            if helper.control_service(action, unit):
                console.print(f"[green]✓[/green] {action} {unit} erfolgreich")

                # If enabling timer, also start it
                if action == "enable" and unit == "timer":
                    if helper.control_service("start", "timer"):
                        console.print("[green]✓[/green] Timer gestartet")

                # Show updated status
                console.print()
                if unit == "service":
                    status = helper.get_service_status()
                    console.print(f"Service Status: {'[green]Aktiv[/green]' if status.active else '[dim]Inaktiv[/dim]'}")
                else:
                    status = helper.get_timer_status()
                    console.print(f"Timer Status: {'[green]Aktiv[/green]' if status.active else '[dim]Inaktiv[/dim]'}")

                console.print()
                console.input("[dim]Drücken Sie Enter zum Fortfahren...[/dim]")
                break
            else:
                console.print(f"[red]✗[/red] Fehler beim Ausführen von {action} {unit}")
                console.print("[dim]Überprüfen Sie die Logs für Details[/dim]")
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
        backup_cmd: str = typer.Option(
            "/usr/bin/env kopi-docka backup", "--backup-cmd"
        ),
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
