################################################################################
# KOPI-DOCKA
#
# @file:        dry_run_commands.py
# @module:      kopi_docka.commands
# @description: Dry run commands for backup simulation
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Dry run commands for backup simulation."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from ..helpers import Config, get_logger, extract_filesystem_path
from ..helpers.ui_utils import (
    print_error,
    print_warning,
    print_error_panel,
    print_next_steps,
)
from ..cores import DockerDiscovery
from ..cores.dry_run_manager import DryRunReport

logger = get_logger(__name__)
console = Console()


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


def cmd_dry_run(
    ctx: typer.Context,
    unit: Optional[str] = None,
    update_recovery: bool = False,
):
    """
    Simulate backup without making changes.

    Shows what would happen during a backup:
    - Which containers would be stopped
    - Which volumes would be backed up
    - Time and space estimates
    - Configuration review
    """
    cfg = ensure_config(ctx)

    console.print("[cyan]Analyzing Docker environment...[/cyan]")
    console.print()

    # Discover backup units
    try:
        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()
    except Exception as e:
        print_error_panel(
            f"Failed to discover Docker environment: {e}\n\n"
            "[bold]Make sure:[/bold]\n"
            "  • Docker is running\n"
            "  • You have permission to access Docker socket\n"
            "  • At least one container is running"
        )
        raise typer.Exit(code=1)

    if not units:
        console.print(
            Panel.fit(
                "[yellow]No backup units found[/yellow]\n\n"
                "[bold]This means:[/bold]\n"
                "  • No running Docker containers detected\n"
                "  • Or Docker socket is not accessible\n\n"
                "[dim]Start some containers first:[/dim]\n"
                "  [cyan]docker run -d --name test nginx[/cyan]",
                title="[bold yellow]Warning[/bold yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(code=0)

    # Filter to specific unit if requested
    if unit:
        units = [u for u in units if u.name == unit]
        if not units:
            print_error(f"Backup unit '{unit}' not found")
            console.print()
            console.print("[bold]Available units:[/bold]")
            discovery = DockerDiscovery()
            all_units = discovery.create_backup_units(
                discovery.discover_containers(), discovery.discover_volumes()
            )
            for u in all_units:
                console.print(f"  [cyan]•[/cyan] {u.name} [dim]({u.type})[/dim]")
            raise typer.Exit(code=1)

        console.print(f"[cyan]Dry run for unit:[/cyan] [bold]{unit}[/bold]")
    else:
        console.print(f"[cyan]Dry run for all units[/cyan] [dim]({len(units)} total)[/dim]")

    # Generate report
    try:
        dry_run = DryRunReport(cfg)
        dry_run.generate(units, update_recovery_bundle=update_recovery)
    except Exception as e:
        print_error_panel(f"Failed to generate dry run report: {e}")
        logger.exception("Dry run failed")
        raise typer.Exit(code=1)


def cmd_list_units(ctx: typer.Context):
    """
    List all discoverable backup units.

    Shows:
    - Stack name or container name
    - Type (stack or standalone)
    - Number of containers
    - Number of volumes
    - Running status
    """
    ensure_config(ctx)

    console.print("[cyan]Discovering backup units...[/cyan]")
    console.print()

    try:
        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()
    except Exception as e:
        print_error_panel(f"Failed to discover units: {e}")
        raise typer.Exit(code=1)

    if not units:
        console.print(
            Panel.fit(
                "[yellow]No backup units found[/yellow]\n\n" "Start some Docker containers first.",
                title="[bold yellow]Warning[/bold yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(code=0)

    # Separate stacks and standalone
    stacks = [u for u in units if u.type == "stack"]
    standalone = [u for u in units if u.type == "standalone"]

    # Create table for stacks
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

    # Create table for standalone containers
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
            status = "[green]Running[/green]" if container.is_running else "[red]Stopped[/red]"

            standalone_table.add_row(status, unit.name, container.image, str(len(unit.volumes)))

        console.print(standalone_table)
        console.print()

    # Summary
    console.print(
        Panel.fit(
            f"[bold]Total:[/bold] {len(stacks)} stacks, {len(standalone)} standalone containers",
            border_style="dim",
        )
    )

    print_next_steps(
        [
            "Dry run all: [cyan]kopi-docka dry-run[/cyan]",
            "Dry run one: [cyan]kopi-docka dry-run --unit <name>[/cyan]",
            "Real backup: [cyan]kopi-docka backup[/cyan]",
        ]
    )


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

    from ..helpers.system_utils import SystemUtils

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


# -------------------------
# Registration
# -------------------------


def register(app: typer.Typer):
    """Register dry-run command (top-level).

    Note: The 'estimate-size' command has been moved to 'admin snapshot estimate-size'.
    """

    @app.command("dry-run")
    def _dry_run_cmd(
        ctx: typer.Context,
        unit: Optional[str] = typer.Option(
            None, "--unit", "-u", help="Run dry-run for specific unit only"
        ),
        update_recovery: bool = typer.Option(
            False, "--update-recovery", help="Include recovery bundle update in simulation"
        ),
    ):
        """Simulate backup without making changes (preview what will happen)."""
        cmd_dry_run(ctx, unit, update_recovery)
