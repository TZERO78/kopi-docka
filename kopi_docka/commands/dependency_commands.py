################################################################################
# KOPI-DOCKA
#
# @file:        dependency_commands.py
# @module:      kopi_docka.commands
# @description: Dependency management commands
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Dependency management commands."""

from pathlib import Path
from typing import Optional

import typer

from ..helpers import Config, get_logger
from ..cores import KopiaRepository
from ..cores import DependencyManager
logger = get_logger(__name__)


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


# -------------------------
# Commands
# -------------------------

def cmd_check(ctx: typer.Context, verbose: bool = False):
    """Check system requirements and dependencies."""
    deps = DependencyManager()
    deps.print_status(verbose=verbose)

    # Check repository if config exists
    cfg = get_config(ctx)
    if cfg:
        try:
            repo = KopiaRepository(cfg)
            if repo.is_connected():
                typer.echo("✓ Kopia repository is connected")
                typer.echo(f"  Profile: {repo.profile_name}")
                typer.echo(f"  Repository: {repo.repo_path}")
                if verbose:
                    snapshots = repo.list_snapshots()
                    typer.echo(f"  Snapshots: {len(snapshots)}")
                    units = repo.list_backup_units()
                    typer.echo(f"  Backup units: {len(units)}")
            else:
                typer.echo("✗ Kopia repository not connected")
                typer.echo("  Run: kopi-docka init")
        except Exception as e:
            typer.echo(f"✗ Repository check failed: {e}")
    else:
        typer.echo("✗ No configuration found")
        typer.echo("  Run: kopi-docka admin config new")


def cmd_install_deps(force: bool = False, dry_run: bool = False):
    """Install missing system dependencies."""
    deps = DependencyManager()

    if dry_run:
        missing = deps.get_missing()
        if missing:
            deps.install_missing(dry_run=True)
        else:
            typer.echo("✓ All dependencies already installed")
        return

    missing = deps.get_missing()
    if missing:
        success = deps.auto_install(force=force)
        if not success:
            raise typer.Exit(code=1)
        typer.echo(f"\n✓ Installed {len(missing)} dependencies")
    else:
        typer.echo("✓ All required dependencies already installed")

    # Hint about config
    if not Path.home().joinpath(".config/kopi-docka/config.json").exists() and \
       not Path("/etc/kopi-docka.json").exists():
        typer.echo("\n💡 Tip: Create config with: kopi-docka admin config new")


def cmd_deps():
    """Show dependency installation guide."""
    deps = DependencyManager()
    deps.print_install_guide()


# -------------------------
# Registration
# -------------------------

def register(app: typer.Typer):
    """Register all dependency commands."""
    
    @app.command("check")
    def _check_cmd(
        ctx: typer.Context,
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    ):
        """Check system requirements and dependencies."""
        cmd_check(ctx, verbose)
    
    @app.command("install-deps")
    def _install_deps_cmd(
        force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be installed"),
    ):
        """Install missing system dependencies."""
        cmd_install_deps(force, dry_run)
    
    @app.command("show-deps")
    def _deps_cmd():
        """Show dependency installation guide."""
        cmd_deps()
