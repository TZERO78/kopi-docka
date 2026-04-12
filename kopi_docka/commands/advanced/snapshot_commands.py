################################################################################
# KOPI-DOCKA
#
# @file:        snapshot_commands.py
# @module:      kopi_docka.commands.advanced
# @description: Snapshot management commands (admin snapshot subgroup)
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.4.1
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Snapshot management commands under 'admin snapshot'.

Commands:
- admin snapshot list              - List backup units or repository snapshots
- admin snapshot estimate-size     - Estimate total backup size
- admin snapshot manage            - Interactive management wizard
- admin snapshot maintenance       - Run repository maintenance
- admin snapshot prune-empty       - Expire snapshots per retention policy
- admin snapshot delete <id>       - Delete a specific snapshot
- admin snapshot pin <id>          - Pin a snapshot
- admin snapshot unpin <id>        - Unpin a snapshot
- admin snapshot retention show    - Show current retention policy
- admin snapshot retention set     - Update retention policy
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

# Note: From advanced/ we need ...helpers (go up two levels)
from ...helpers import Config, get_logger, extract_filesystem_path
from ...helpers.ui_utils import (
    print_warning,
    print_error_panel,
)
from ...cores import KopiaRepository, DockerDiscovery, SnapshotManager

logger = get_logger(__name__)
console = Console()

# Create snapshot subcommand group
snapshot_app = typer.Typer(
    name="snapshot",
    help="Snapshot and backup unit management commands.",
    no_args_is_help=True,
)


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


def ensure_config(ctx: typer.Context) -> Config:
    """Ensure config exists or exit."""
    cfg = get_config(ctx)
    if not cfg:
        print_error_panel(
            "No configuration found\n\n"
            "[dim]Run:[/dim] [cyan]kopi-docka advanced config new[/cyan]"
        )
        raise typer.Exit(code=1)
    return cfg


# -------------------------
# Commands
# -------------------------


def cmd_list(
    ctx: typer.Context,
    units: bool = True,
    snapshots: bool = False,
):
    """List backup units or repository snapshots."""
    cfg = ensure_config(ctx)

    if not (units or snapshots):
        units = True

    if units:
        console.print("[cyan]Discovering Docker backup units...[/cyan]")
        try:
            discovery = DockerDiscovery()
            found = discovery.discover_backup_units()
            if not found:
                console.print("[dim]No units found.[/dim]")
            else:
                console.print()

                # Separate stacks and standalone
                stacks = [u for u in found if u.type == "stack"]
                standalone = [u for u in found if u.type == "standalone"]

                if stacks:
                    stack_table = Table(
                        title="Docker Compose Stacks",
                        box=box.ROUNDED,
                        border_style="cyan",
                        title_style="bold cyan",
                    )
                    stack_table.add_column("Status", style="bold", width=8)
                    stack_table.add_column("Name", style="cyan")
                    stack_table.add_column("Containers", justify="center")
                    stack_table.add_column("Volumes", justify="center")
                    stack_table.add_column("Compose File", style="dim")

                    for unit in stacks:
                        running = len(unit.running_containers)
                        total = len(unit.containers)
                        if running == total:
                            status = "[green]Running[/green]"
                        elif running > 0:
                            status = "[yellow]Partial[/yellow]"
                        else:
                            status = "[red]Stopped[/red]"

                        compose = str(unit.compose_file) if unit.compose_file else "-"
                        stack_table.add_row(
                            status, unit.name, f"{running}/{total}", str(len(unit.volumes)), compose
                        )

                    console.print(stack_table)
                    console.print()

                if standalone:
                    standalone_table = Table(
                        title="Standalone Containers",
                        box=box.ROUNDED,
                        border_style="cyan",
                        title_style="bold cyan",
                    )
                    standalone_table.add_column("Status", style="bold", width=8)
                    standalone_table.add_column("Name", style="cyan")
                    standalone_table.add_column("Image")
                    standalone_table.add_column("Volumes", justify="center")

                    for unit in standalone:
                        container = unit.containers[0]
                        status = (
                            "[green]Running[/green]"
                            if container.is_running
                            else "[red]Stopped[/red]"
                        )

                        standalone_table.add_row(
                            status, unit.name, container.image, str(len(unit.volumes))
                        )

                    console.print(standalone_table)
                    console.print()

                # Summary
                console.print(
                    Panel.fit(
                        f"[bold]Total:[/bold] {len(stacks)} stacks, {len(standalone)} standalone containers",
                        border_style="dim",
                    )
                )

        except Exception as e:
            print_error_panel(f"Discovery failed: {e}")
            raise typer.Exit(code=1)

    if snapshots:
        console.print()
        console.print("[cyan]Listing snapshots...[/cyan]")
        try:
            repo = KopiaRepository(cfg)
            snaps = repo.list_snapshots()
            if not snaps:
                console.print("[dim]No snapshots found.[/dim]")
            else:
                console.print()
                snap_table = Table(
                    title=f"Repository Snapshots ({len(snaps)} total)",
                    box=box.ROUNDED,
                    border_style="cyan",
                    title_style="bold cyan",
                )
                snap_table.add_column("ID", style="dim")
                snap_table.add_column("Unit", style="cyan")
                snap_table.add_column("Timestamp")

                for s in snaps:
                    unit = s.get("tags", {}).get("unit", "-")
                    ts = s.get("timestamp", "-")
                    sid = s.get("id", "")
                    snap_table.add_row(f"{sid[:12]}...", unit, ts)

                console.print(snap_table)
        except Exception as e:
            print_error_panel(f"Unable to list snapshots: {e}")
            raise typer.Exit(code=1)


def cmd_estimate_size(ctx: typer.Context):
    """
    Estimate total backup size for all units.

    Useful for:
    - Planning storage capacity
    - Checking if enough disk space
    - Understanding data distribution
    """
    cfg = ensure_config(ctx)

    console.print("[cyan]Calculating backup size estimates...[/cyan]")
    console.print()

    try:
        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()
    except Exception as e:
        print_error_panel(f"Failed to discover units: {e}")
        raise typer.Exit(code=1)

    if not units:
        print_warning("No backup units found")
        raise typer.Exit(code=0)

    from ...helpers.system_utils import SystemUtils

    utils = SystemUtils()

    # Create table for size estimates
    size_table = Table(
        title="Backup Size Estimates", box=box.ROUNDED, border_style="cyan", title_style="bold cyan"
    )
    size_table.add_column("Unit", style="cyan")
    size_table.add_column("Volumes", justify="center")
    size_table.add_column("Raw Size", justify="right")
    size_table.add_column("Est. Compressed", justify="right", style="green")

    total_size = 0

    for unit in units:
        unit_size = unit.total_volume_size
        total_size += unit_size

        if unit_size > 0:
            size_table.add_row(
                unit.name,
                str(len(unit.volumes)),
                utils.format_bytes(unit_size),
                utils.format_bytes(int(unit_size * 0.5)),
            )

    console.print(size_table)
    console.print()

    # Summary panel
    summary_lines = [
        f"[bold]Total Raw Size:[/bold] {utils.format_bytes(total_size)}",
        f"[bold]Estimated Compressed:[/bold] [green]{utils.format_bytes(int(total_size * 0.5))}[/green]",
    ]

    # Check available space for filesystem repositories
    kopia_params = cfg.get("kopia", "kopia_params", fallback="")

    try:
        repo_path_str = extract_filesystem_path(kopia_params)
        if repo_path_str:
            space_gb = utils.get_available_disk_space(str(Path(repo_path_str).parent))
            space_bytes = int(space_gb * (1024**3))

            summary_lines.append(
                f"\n[bold]Available Space:[/bold] {utils.format_bytes(space_bytes)}"
            )

            required = int(total_size * 0.5)
            if space_bytes < required:
                summary_lines.append(
                    f"\n[red bold]Insufficient disk space![/red bold]\n"
                    f"  Need: {utils.format_bytes(required)}\n"
                    f"  Have: {utils.format_bytes(space_bytes)}\n"
                    f"  Short: {utils.format_bytes(required - space_bytes)}"
                )
            else:
                remaining = space_bytes - required
                summary_lines.append(
                    f"[green]Sufficient space[/green] (remaining: {utils.format_bytes(remaining)})"
                )
    except Exception as e:
        logger.debug(f"Could not check disk space: {e}")

    console.print(
        Panel.fit("\n".join(summary_lines), title="[bold]Summary[/bold]", border_style="cyan")
    )

    # Note about estimates
    console.print()
    console.print(
        Panel.fit(
            "[bold]Note:[/bold] These are estimates. Actual size depends on:\n"
            "  [dim]•[/dim] Compression efficiency\n"
            "  [dim]•[/dim] Kopia deduplication\n"
            "  [dim]•[/dim] File types (text compresses well, media files don't)",
            border_style="dim",
        )
    )


# Retention sub-group
retention_app = typer.Typer(
    name="retention",
    help="View or update retention policy.",
    no_args_is_help=True,
)


def cmd_manage(ctx: typer.Context) -> None:
    """Launch interactive snapshot management wizard."""
    cfg = ensure_config(ctx)
    mgr = SnapshotManager(cfg)
    mgr.interactive_manage()


def cmd_maintenance(
    ctx: typer.Context,
    full: bool = typer.Option(False, "--full", help="Run full maintenance (default: quick)"),
) -> None:
    """Run Kopia repository maintenance."""
    cfg = ensure_config(ctx)
    mgr = SnapshotManager(cfg)
    mgr.cmd_maintenance(full=full)


def cmd_prune_empty(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only, do not delete"),
) -> None:
    """Apply retention policy and expire old snapshots."""
    cfg = ensure_config(ctx)
    mgr = SnapshotManager(cfg)
    mgr.cmd_prune_empty(dry_run=dry_run)


def cmd_delete(
    ctx: typer.Context,
    snapshot_id: str = typer.Argument(..., help="Snapshot ID to delete"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompt"),
) -> None:
    """Delete a specific snapshot."""
    cfg = ensure_config(ctx)
    mgr = SnapshotManager(cfg)
    mgr.cmd_delete(snapshot_id, force=force)


def cmd_pin(
    ctx: typer.Context,
    snapshot_id: str = typer.Argument(..., help="Snapshot ID to pin"),
) -> None:
    """Pin a snapshot to protect it from retention cleanup."""
    cfg = ensure_config(ctx)
    mgr = SnapshotManager(cfg)
    mgr.cmd_pin(snapshot_id)


def cmd_unpin(
    ctx: typer.Context,
    snapshot_id: str = typer.Argument(..., help="Snapshot ID to unpin"),
) -> None:
    """Remove pin from a snapshot."""
    cfg = ensure_config(ctx)
    mgr = SnapshotManager(cfg)
    mgr.cmd_unpin(snapshot_id)


def cmd_retention_show(ctx: typer.Context) -> None:
    """Show current retention policy (config + Kopia global policy)."""
    cfg = ensure_config(ctx)
    mgr = SnapshotManager(cfg)
    mgr.cmd_retention_show()


def cmd_retention_set(
    ctx: typer.Context,
    latest: int = typer.Option(10, "--latest", help="Keep N latest snapshots"),
    hourly: int = typer.Option(0, "--hourly", help="Keep N hourly snapshots"),
    daily: int = typer.Option(7, "--daily", help="Keep N daily snapshots"),
    weekly: int = typer.Option(4, "--weekly", help="Keep N weekly snapshots"),
    monthly: int = typer.Option(12, "--monthly", help="Keep N monthly snapshots"),
    annual: int = typer.Option(3, "--annual", help="Keep N annual snapshots"),
) -> None:
    """Update retention policy in Kopia and config file."""
    cfg = ensure_config(ctx)
    mgr = SnapshotManager(cfg)
    mgr.cmd_retention_set(latest, hourly, daily, weekly, monthly, annual)


# -------------------------
# Registration
# -------------------------


def register(app: typer.Typer):
    """Register snapshot commands under 'admin snapshot'."""

    @snapshot_app.command("list")
    def _list_cmd(
        ctx: typer.Context,
        units: bool = typer.Option(True, "--units/--no-units", help="List discovered backup units"),
        snapshots: bool = typer.Option(False, "--snapshots", help="List repository snapshots"),
    ):
        """List backup units or repository snapshots."""
        cmd_list(ctx, units, snapshots)

    @snapshot_app.command("estimate-size")
    def _estimate_size_cmd(ctx: typer.Context):
        """Estimate total backup size for all units."""
        cmd_estimate_size(ctx)

    @snapshot_app.command("manage")
    def _manage_cmd(ctx: typer.Context):
        """Interactive snapshot management wizard."""
        cmd_manage(ctx)

    @snapshot_app.command("maintenance")
    def _maintenance_cmd(
        ctx: typer.Context,
        full: bool = typer.Option(False, "--full", help="Run full maintenance (default: quick)"),
    ):
        """Run Kopia repository maintenance."""
        cmd_maintenance(ctx, full=full)

    @snapshot_app.command("prune-empty")
    def _prune_empty_cmd(
        ctx: typer.Context,
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview only, do not delete"),
    ):
        """Apply retention policy and expire old snapshots."""
        cmd_prune_empty(ctx, dry_run=dry_run)

    @snapshot_app.command("delete")
    def _delete_cmd(
        ctx: typer.Context,
        snapshot_id: str = typer.Argument(..., help="Snapshot ID to delete"),
        force: bool = typer.Option(False, "--force", help="Skip confirmation prompt"),
    ):
        """Delete a specific snapshot."""
        cmd_delete(ctx, snapshot_id, force=force)

    @snapshot_app.command("pin")
    def _pin_cmd(
        ctx: typer.Context,
        snapshot_id: str = typer.Argument(..., help="Snapshot ID to pin"),
    ):
        """Pin a snapshot to protect it from retention cleanup."""
        cmd_pin(ctx, snapshot_id)

    @snapshot_app.command("unpin")
    def _unpin_cmd(
        ctx: typer.Context,
        snapshot_id: str = typer.Argument(..., help="Snapshot ID to unpin"),
    ):
        """Remove pin from a snapshot."""
        cmd_unpin(ctx, snapshot_id)

    # Retention sub-group
    @retention_app.command("show")
    def _retention_show_cmd(ctx: typer.Context):
        """Show current retention policy."""
        cmd_retention_show(ctx)

    @retention_app.command("set")
    def _retention_set_cmd(
        ctx: typer.Context,
        latest: int = typer.Option(10, "--latest", help="Keep N latest snapshots"),
        hourly: int = typer.Option(0, "--hourly", help="Keep N hourly snapshots"),
        daily: int = typer.Option(7, "--daily", help="Keep N daily snapshots"),
        weekly: int = typer.Option(4, "--weekly", help="Keep N weekly snapshots"),
        monthly: int = typer.Option(12, "--monthly", help="Keep N monthly snapshots"),
        annual: int = typer.Option(3, "--annual", help="Keep N annual snapshots"),
    ):
        """Update retention policy in Kopia and config file."""
        cmd_retention_set(ctx, latest, hourly, daily, weekly, monthly, annual)

    snapshot_app.add_typer(retention_app, name="retention", help="View or update retention policy")

    # Add snapshot subgroup to admin app
    app.add_typer(snapshot_app, name="snapshot", help="Snapshot and backup unit management")
