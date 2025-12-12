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

from ..helpers import Config, get_logger
from ..cores import DockerDiscovery
from ..cores.dry_run_manager import DryRunReport

logger = get_logger(__name__)


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


def ensure_config(ctx: typer.Context) -> Config:
    """Ensure config exists or exit."""
    cfg = get_config(ctx)
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka admin config new")
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
    
    typer.echo("🔍 Analyzing Docker environment...")
    typer.echo("")
    
    # Discover backup units
    try:
        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()
    except Exception as e:
        typer.echo(f"❌ Failed to discover Docker environment: {e}")
        typer.echo("")
        typer.echo("Make sure:")
        typer.echo("  • Docker is running")
        typer.echo("  • You have permission to access Docker socket")
        typer.echo("  • At least one container is running")
        raise typer.Exit(code=1)
    
    if not units:
        typer.echo("⚠️  No backup units found")
        typer.echo("")
        typer.echo("This means:")
        typer.echo("  • No running Docker containers detected")
        typer.echo("  • Or Docker socket is not accessible")
        typer.echo("")
        typer.echo("Start some containers first:")
        typer.echo("  docker run -d --name test nginx")
        raise typer.Exit(code=0)
    
    # Filter to specific unit if requested
    if unit:
        units = [u for u in units if u.name == unit]
        if not units:
            typer.echo(f"❌ Backup unit '{unit}' not found")
            typer.echo("")
            typer.echo("Available units:")
            discovery = DockerDiscovery()
            all_units = discovery.create_backup_units(
                discovery.discover_containers(),
                discovery.discover_volumes()
            )
            for u in all_units:
                typer.echo(f"  • {u.name} ({u.type})")
            raise typer.Exit(code=1)
        
        typer.echo(f"📦 Dry run for unit: {unit}")
    else:
        typer.echo(f"📦 Dry run for all units ({len(units)} total)")
    
    # Generate report
    try:
        dry_run = DryRunReport(cfg)
        dry_run.generate(units, update_recovery_bundle=update_recovery)
    except Exception as e:
        typer.echo(f"❌ Failed to generate dry run report: {e}")
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
    
    typer.echo("🔍 Discovering backup units...")
    typer.echo("")
    
    try:
        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()
    except Exception as e:
        typer.echo(f"❌ Failed to discover units: {e}")
        raise typer.Exit(code=1)
    
    if not units:
        typer.echo("⚠️  No backup units found")
        typer.echo("Start some Docker containers first.")
        raise typer.Exit(code=0)
    
    typer.echo("=" * 70)
    typer.echo(f"DISCOVERED BACKUP UNITS ({len(units)} total)")
    typer.echo("=" * 70)
    
    # Separate stacks and standalone
    stacks = [u for u in units if u.type == "stack"]
    standalone = [u for u in units if u.type == "standalone"]
    
    if stacks:
        typer.echo("\n📚 Docker Compose Stacks:")
        for unit in stacks:
            running = len(unit.running_containers)
            total = len(unit.containers)
            status = "🟢" if running == total else "🟡" if running > 0 else "🔴"
            
            typer.echo(f"\n  {status} {unit.name}")
            typer.echo(f"     Type: {unit.type}")
            typer.echo(f"     Containers: {running}/{total} running")
            typer.echo(f"     Volumes: {len(unit.volumes)}")
            
            if unit.compose_file:
                typer.echo(f"     Compose: {unit.compose_file}")
            
            # Show container names
            if unit.containers:
                container_names = [c.name for c in unit.containers[:3]]
                if len(unit.containers) > 3:
                    container_names.append(f"... and {len(unit.containers) - 3} more")
                typer.echo(f"     Services: {', '.join(container_names)}")
    
    if standalone:
        typer.echo("\n📦 Standalone Containers:")
        for unit in standalone:
            container = unit.containers[0]
            status = "🟢" if container.is_running else "🔴"
            
            typer.echo(f"\n  {status} {unit.name}")
            typer.echo(f"     Type: {unit.type}")
            typer.echo(f"     Image: {container.image}")
            typer.echo(f"     Status: {'Running' if container.is_running else 'Stopped'}")
            typer.echo(f"     Volumes: {len(unit.volumes)}")
    
    typer.echo("\n" + "=" * 70)
    typer.echo(f"Total: {len(stacks)} stacks, {len(standalone)} standalone")
    typer.echo("=" * 70)
    
    typer.echo("\n💡 Next steps:")
    typer.echo("  • Dry run all: kopi-docka dry-run")
    typer.echo("  • Dry run one: kopi-docka dry-run --unit <name>")
    typer.echo("  • Real backup: kopi-docka backup")


def cmd_estimate_size(ctx: typer.Context):
    """
    Estimate total backup size for all units.
    
    Useful for:
    - Planning storage capacity
    - Checking if enough disk space
    - Understanding data distribution
    """
    cfg = ensure_config(ctx)
    
    typer.echo("📊 Calculating backup size estimates...")
    typer.echo("")
    
    try:
        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()
    except Exception as e:
        typer.echo(f"❌ Failed to discover units: {e}")
        raise typer.Exit(code=1)
    
    if not units:
        typer.echo("⚠️  No backup units found")
        raise typer.Exit(code=0)
    
    from ..helpers.system_utils import SystemUtils
    utils = SystemUtils()
    
    typer.echo("=" * 70)
    typer.echo("BACKUP SIZE ESTIMATES")
    typer.echo("=" * 70)
    
    total_size = 0
    
    for unit in units:
        unit_size = unit.total_volume_size
        total_size += unit_size
        
        if unit_size > 0:
            typer.echo(f"\n📦 {unit.name}")
            typer.echo(f"   Volumes: {len(unit.volumes)}")
            typer.echo(f"   Raw Size: {utils.format_bytes(unit_size)}")
            typer.echo(f"   Estimated (compressed): {utils.format_bytes(int(unit_size * 0.5))}")
    
    typer.echo("\n" + "=" * 70)
    typer.echo(f"Total Raw Size: {utils.format_bytes(total_size)}")
    typer.echo(f"Estimated Compressed: {utils.format_bytes(int(total_size * 0.5))}")
    typer.echo("=" * 70)
    
    # Check available space
    # Get kopia_params
    kopia_params = cfg.get('kopia', 'kopia_params', fallback='')
    
    try:
        # Try to get disk space for local filesystem repos
        # Parse kopia_params for filesystem path
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
                        typer.echo("⚠️  WARNING: Insufficient disk space!")
                        typer.echo(f"   Need: {utils.format_bytes(required)}")
                        typer.echo(f"   Have: {utils.format_bytes(space_bytes)}")
                        typer.echo(f"   Short: {utils.format_bytes(required - space_bytes)}")
                    else:
                        remaining = space_bytes - required
                        typer.echo(f"✓ Sufficient space (remaining: {utils.format_bytes(remaining)})")
            except (ValueError, IndexError):
                pass
    except Exception as e:
        logger.debug(f"Could not check disk space: {e}")
    
    typer.echo("\n💡 Note: These are estimates. Actual size depends on:")
    typer.echo("  • Compression efficiency")
    typer.echo("  • Kopia deduplication")
    typer.echo("  • File types (text compresses well, media files don't)")


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
        unit: Optional[str] = typer.Option(None, "--unit", "-u", help="Run dry-run for specific unit only"),
        update_recovery: bool = typer.Option(False, "--update-recovery", help="Include recovery bundle update in simulation"),
    ):
        """Simulate backup without making changes (preview what will happen)."""
        cmd_dry_run(ctx, unit, update_recovery)
