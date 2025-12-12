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
- admin snapshot list         - List backup units or repository snapshots
- admin snapshot estimate-size - Estimate total backup size
"""

from typing import Optional

import typer

# Note: From advanced/ we need ...helpers (go up two levels)
from ...helpers import Config, get_logger
from ...cores import KopiaRepository, DockerDiscovery

logger = get_logger(__name__)

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
        typer.echo("No configuration found")
        typer.echo("Run: kopi-docka admin config new")
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
        typer.echo("Discovering Docker backup units...")
        try:
            discovery = DockerDiscovery()
            found = discovery.discover_backup_units()
            if not found:
                typer.echo("No units found.")
            else:
                typer.echo("")
                typer.echo("=" * 70)
                typer.echo(f"DISCOVERED BACKUP UNITS ({len(found)} total)")
                typer.echo("=" * 70)

                # Separate stacks and standalone
                stacks = [u for u in found if u.type == "stack"]
                standalone = [u for u in found if u.type == "standalone"]

                if stacks:
                    typer.echo("\nDocker Compose Stacks:")
                    for unit in stacks:
                        running = len(unit.running_containers)
                        total = len(unit.containers)
                        status = "[running]" if running == total else "[partial]" if running > 0 else "[stopped]"

                        typer.echo(f"\n  {status} {unit.name}")
                        typer.echo(f"     Type: {unit.type}")
                        typer.echo(f"     Containers: {running}/{total} running")
                        typer.echo(f"     Volumes: {len(unit.volumes)}")

                        if unit.compose_file:
                            typer.echo(f"     Compose: {unit.compose_file}")

                        if unit.containers:
                            container_names = [c.name for c in unit.containers[:3]]
                            if len(unit.containers) > 3:
                                container_names.append(f"... and {len(unit.containers) - 3} more")
                            typer.echo(f"     Services: {', '.join(container_names)}")

                if standalone:
                    typer.echo("\nStandalone Containers:")
                    for unit in standalone:
                        container = unit.containers[0]
                        status = "[running]" if container.is_running else "[stopped]"

                        typer.echo(f"\n  {status} {unit.name}")
                        typer.echo(f"     Type: {unit.type}")
                        typer.echo(f"     Image: {container.image}")
                        typer.echo(f"     Status: {'Running' if container.is_running else 'Stopped'}")
                        typer.echo(f"     Volumes: {len(unit.volumes)}")

                typer.echo("\n" + "=" * 70)
                typer.echo(f"Total: {len(stacks)} stacks, {len(standalone)} standalone")
                typer.echo("=" * 70)
        except Exception as e:
            typer.echo(f"Discovery failed: {e}")
            raise typer.Exit(code=1)

    if snapshots:
        typer.echo("\nListing snapshots...")
        try:
            repo = KopiaRepository(cfg)
            snaps = repo.list_snapshots()
            if not snaps:
                typer.echo("No snapshots found.")
            else:
                typer.echo("")
                typer.echo("=" * 70)
                typer.echo(f"REPOSITORY SNAPSHOTS ({len(snaps)} total)")
                typer.echo("=" * 70)
                for s in snaps:
                    unit = s.get("tags", {}).get("unit", "-")
                    ts = s.get("timestamp", "-")
                    sid = s.get("id", "")
                    typer.echo(f"  {sid[:12]}... | unit={unit} | {ts}")
                typer.echo("=" * 70)
        except Exception as e:
            typer.echo(f"Unable to list snapshots: {e}")
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

    typer.echo("Calculating backup size estimates...")
    typer.echo("")

    try:
        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()
    except Exception as e:
        typer.echo(f"Failed to discover units: {e}")
        raise typer.Exit(code=1)

    if not units:
        typer.echo("No backup units found")
        raise typer.Exit(code=0)

    from ...helpers.system_utils import SystemUtils
    utils = SystemUtils()

    typer.echo("=" * 70)
    typer.echo("BACKUP SIZE ESTIMATES")
    typer.echo("=" * 70)

    total_size = 0

    for unit in units:
        unit_size = unit.total_volume_size
        total_size += unit_size

        if unit_size > 0:
            typer.echo(f"\n  {unit.name}")
            typer.echo(f"   Volumes: {len(unit.volumes)}")
            typer.echo(f"   Raw Size: {utils.format_bytes(unit_size)}")
            typer.echo(f"   Estimated (compressed): {utils.format_bytes(int(unit_size * 0.5))}")

    typer.echo("\n" + "=" * 70)
    typer.echo(f"Total Raw Size: {utils.format_bytes(total_size)}")
    typer.echo(f"Estimated Compressed: {utils.format_bytes(int(total_size * 0.5))}")
    typer.echo("=" * 70)

    # Check available space
    kopia_params = cfg.get('kopia', 'kopia_params', fallback='')

    try:
        if kopia_params and 'filesystem' in kopia_params and '--path' in kopia_params:
            import shlex
            parts = shlex.split(kopia_params)
            try:
                path_idx = parts.index('--path') + 1
                if path_idx < len(parts):
                    repo_path_str = parts[path_idx]
                    from pathlib import Path
                    space_gb = utils.get_available_disk_space(str(Path(repo_path_str).parent))
                    space_bytes = int(space_gb * (1024**3))

                    typer.echo(f"\nAvailable Space: {utils.format_bytes(space_bytes)}")

                    required = int(total_size * 0.5)
                    if space_bytes < required:
                        typer.echo("WARNING: Insufficient disk space!")
                        typer.echo(f"   Need: {utils.format_bytes(required)}")
                        typer.echo(f"   Have: {utils.format_bytes(space_bytes)}")
                        typer.echo(f"   Short: {utils.format_bytes(required - space_bytes)}")
                    else:
                        remaining = space_bytes - required
                        typer.echo(f"Sufficient space (remaining: {utils.format_bytes(remaining)})")
            except (ValueError, IndexError):
                pass
    except Exception as e:
        logger.debug(f"Could not check disk space: {e}")

    typer.echo("\nNote: These are estimates. Actual size depends on:")
    typer.echo("  - Compression efficiency")
    typer.echo("  - Kopia deduplication")
    typer.echo("  - File types (text compresses well, media files don't)")


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

    # Add snapshot subgroup to admin app
    app.add_typer(snapshot_app, name="snapshot", help="Snapshot and backup unit management")
