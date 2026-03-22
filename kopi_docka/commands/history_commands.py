################################################################################
# KOPI-DOCKA
#
# @file:        history_commands.py
# @module:      kopi_docka.commands
# @description: Backup history CLI command — shows past backups from metadata.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Backup history command — reads metadata JSONs and displays them."""

import json as json_mod
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from ..helpers import Config, get_logger
from ..helpers.metadata_reader import MetadataReader
from ..helpers.ui_utils import print_info, print_warning
from ..types import BackupMetadata

logger = get_logger(__name__)
console = Console()


def _get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config") if ctx.obj else None


def _format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m{secs:02d}s"


def _format_snapshot_ids(ids: list[str]) -> str:
    """Format snapshot IDs for table display."""
    if not ids:
        return "-"
    if len(ids) == 1:
        return ids[0][:12]
    return f"{ids[0][:12]} (+{len(ids) - 1})"


def _render_detail_panel(m: BackupMetadata) -> Panel:
    """Render a single BackupMetadata as a Rich Panel with all fields."""
    status = "[green]Success[/green]" if m.success else "[red]Failed[/red]"
    border = "green" if m.success else "red"

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Field", style="cyan", width=22)
    table.add_column("Value")

    table.add_row("Unit", m.unit_name)
    table.add_row("Timestamp", m.timestamp.strftime("%Y-%m-%d %H:%M:%S"))
    table.add_row("Backup ID", m.backup_id or "-")
    table.add_row("Status", status)
    table.add_row("Duration", _format_duration(m.duration_seconds))
    table.add_row("Scope", m.backup_scope)
    table.add_row("Format", m.backup_format)
    table.add_row("Volumes backed up", str(m.volumes_backed_up))
    table.add_row("Databases backed up", str(m.databases_backed_up))
    table.add_row("Networks backed up", str(m.networks_backed_up))
    table.add_row("Docker config", "Yes" if m.docker_config_backed_up else "No")
    table.add_row(
        "Snapshot IDs",
        ", ".join(m.kopia_snapshot_ids) if m.kopia_snapshot_ids else "-",
    )
    table.add_row(
        "Hooks executed",
        ", ".join(m.hooks_executed) if m.hooks_executed else "-",
    )
    if m.error_message:
        table.add_row("Error", f"[red]{m.error_message}[/red]")
    if m.errors:
        for i, err in enumerate(m.errors):
            label = "Errors" if i == 0 else ""
            table.add_row(label, f"[red]{err}[/red]")

    title = f"{m.unit_name} — {m.timestamp.strftime('%Y-%m-%d %H:%M')}"
    return Panel(table, title=f"[bold]{title}[/bold]", border_style=border)


def _render_stats_table(entries: List[BackupMetadata]) -> Table:
    """Build a stats table with avg/min/max duration per unit."""
    by_unit: Dict[str, List[float]] = defaultdict(list)
    success_count: Dict[str, int] = defaultdict(int)
    fail_count: Dict[str, int] = defaultdict(int)

    for m in entries:
        by_unit[m.unit_name].append(m.duration_seconds)
        if m.success:
            success_count[m.unit_name] += 1
        else:
            fail_count[m.unit_name] += 1

    table = Table(
        box=box.ROUNDED,
        title="Backup Statistics",
        title_style="bold cyan",
    )
    table.add_column("Unit", style="bold")
    table.add_column("Backups", justify="right")
    table.add_column("Success", justify="right", style="green")
    table.add_column("Failed", justify="right", style="red")
    table.add_column("Avg Duration", justify="right")
    table.add_column("Min Duration", justify="right")
    table.add_column("Max Duration", justify="right")

    for unit_name in sorted(by_unit.keys()):
        durations = by_unit[unit_name]
        total = len(durations)
        avg = sum(durations) / total
        table.add_row(
            unit_name,
            str(total),
            str(success_count[unit_name]),
            str(fail_count[unit_name]),
            _format_duration(avg),
            _format_duration(min(durations)),
            _format_duration(max(durations)),
        )

    return table


def register(app: typer.Typer):
    """Register history command."""

    @app.command("history")
    def cmd_history(
        ctx: typer.Context,
        unit: Optional[str] = typer.Option(
            None, "--unit", "-u", help="Filter by unit name"
        ),
        failed: bool = typer.Option(
            False, "--failed", "-f", help="Show only failed backups"
        ),
        last: int = typer.Option(
            20, "--last", "-n", help="Number of entries to show"
        ),
        since: Optional[str] = typer.Option(
            None, "--since", help="Show backups since date (YYYY-MM-DD)"
        ),
        detail: bool = typer.Option(
            False, "--detail", "-d", help="Show detailed view of each backup"
        ),
        backup_id: Optional[str] = typer.Option(
            None, "--id", help="Show detail for a specific backup ID"
        ),
        stats: bool = typer.Option(
            False, "--stats", help="Show duration statistics per unit"
        ),
        output_json: bool = typer.Option(
            False, "--json", help="Output as JSON (machine-readable)"
        ),
    ):
        """Show backup history from stored metadata."""
        cfg = _get_config(ctx)
        if not cfg:
            console.print(
                Panel.fit(
                    "[red]No configuration found[/red]\n\n"
                    "[dim]Run:[/dim] [cyan]kopi-docka advanced config new[/cyan]",
                    title="[bold red]Error[/bold red]",
                    border_style="red",
                )
            )
            raise typer.Exit(1)

        metadata_dir = cfg.backup_base_path / "metadata"
        reader = MetadataReader(metadata_dir)

        # Parse --since
        since_dt = None
        if since:
            try:
                since_dt = datetime.strptime(since, "%Y-%m-%d")
            except ValueError:
                console.print(f"[red]Invalid date format: {since}. Use YYYY-MM-DD.[/red]")
                raise typer.Exit(1)

        # --json: machine-readable output (suppress log warnings for clean output)
        if output_json:
            import logging
            md_logger = logging.getLogger("kopi-docka.kopi_docka.helpers.metadata_reader")
            prev_level = md_logger.level
            md_logger.setLevel(logging.ERROR)
            try:
                entries = reader.read_all(
                    unit_name=unit, only_failed=failed, since=since_dt, limit=last,
                )
            finally:
                md_logger.setLevel(prev_level)
            typer.echo(json_mod.dumps([m.to_dict() for m in entries], indent=2))
            return

        # --id: show single backup by ID
        if backup_id:
            all_entries = reader.read_all()
            match = [m for m in all_entries if m.backup_id == backup_id]
            if not match:
                console.print(f"[red]No backup found with ID: {backup_id}[/red]")
                raise typer.Exit(1)
            console.print()
            console.print(_render_detail_panel(match[0]))
            console.print()
            return

        # --stats: show duration statistics
        if stats:
            all_entries = reader.read_all(unit_name=unit, only_failed=failed, since=since_dt)
            if not all_entries:
                print_info("No backup history found.")
                return
            console.print()
            console.print(_render_stats_table(all_entries))
            console.print()
            return

        entries = reader.read_all(
            unit_name=unit,
            only_failed=failed,
            since=since_dt,
            limit=last,
        )

        if not entries:
            print_info("No backup history found.")
            if not metadata_dir.is_dir():
                print_warning(f"Metadata directory does not exist: {metadata_dir}")
            return

        # --detail: show panels instead of table
        if detail:
            console.print()
            for m in entries:
                console.print(_render_detail_panel(m))
                console.print()
            return

        # Count total (without limit) for footer
        total_entries = reader.read_all(
            unit_name=unit,
            only_failed=failed,
            since=since_dt,
        )
        total_count = len(total_entries)

        # Build table
        table = Table(
            box=box.ROUNDED,
            title="Backup History",
            title_style="bold cyan",
        )
        table.add_column("Timestamp", style="dim")
        table.add_column("Unit", style="bold")
        table.add_column("Duration", justify="right")
        table.add_column("Status", justify="center")
        table.add_column("Scope")
        table.add_column("Volumes", justify="right")
        table.add_column("Snapshots")

        for m in entries:
            status = "[green]✓[/green]" if m.success else "[red]✗[/red]"
            ts = m.timestamp.strftime("%Y-%m-%d %H:%M")
            duration = _format_duration(m.duration_seconds)
            snapshots = _format_snapshot_ids(m.kopia_snapshot_ids)
            unit_style = "" if m.success else "[red]"
            unit_end = "" if m.success else "[/red]"

            table.add_row(
                ts,
                f"{unit_style}{m.unit_name}{unit_end}",
                duration,
                status,
                m.backup_scope,
                str(m.volumes_backed_up),
                snapshots,
            )

        console.print()
        console.print(table)

        if total_count > len(entries):
            console.print(
                f"\n[dim]Showing {len(entries)} of {total_count} entries. "
                f"Use --last N to see more.[/dim]"
            )
        console.print()
