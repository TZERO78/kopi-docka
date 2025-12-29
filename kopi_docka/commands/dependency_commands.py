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
from rich.console import Console

from ..helpers import Config, get_logger
from ..helpers.ui_utils import (
    print_success,
    print_error,
    print_error_panel,
)
from ..cores import KopiaRepository
from ..cores import DependencyManager

logger = get_logger(__name__)
console = Console()


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


def _override_config(ctx: typer.Context, config: Optional[Path]):
    """Override config in context when command-level --config is used."""
    if not config:
        return
    try:
        cfg = Config(config)
        ctx.obj["config"] = cfg
        ctx.obj["config_path"] = config
    except Exception as e:
        print_error_panel(f"Failed to load config: {e}")
        raise typer.Exit(code=1)


# -------------------------
# Commands
# -------------------------


def cmd_check(
    ctx: typer.Context,
    verbose: bool = False,
    config: Optional[Path] = None,
):
    """Check system requirements and dependencies."""
    _override_config(ctx, config)
    deps = DependencyManager()
    deps.print_status(verbose=verbose)

    # Check repository if config exists
    cfg = get_config(ctx)
    if cfg:
        try:
            repo = KopiaRepository(cfg)
            if repo.is_connected():
                print_success("Kopia repository is connected")
                console.print(f"  [cyan]Profile:[/cyan] {repo.profile_name}")
                console.print(f"  [cyan]Repository:[/cyan] {repo.repo_path}")
                if verbose:
                    snapshots = repo.list_snapshots()
                    console.print(f"  [cyan]Snapshots:[/cyan] {len(snapshots)}")
                    units = repo.list_backup_units()
                    console.print(f"  [cyan]Backup units:[/cyan] {len(units)}")
            else:
                print_error("Kopia repository not connected")
                console.print("  [dim]Run:[/dim] [cyan]kopi-docka init[/cyan]")
        except Exception:
            print_error("No configuration found")
            console.print("  [dim]Run:[/dim] [cyan]kopi-docka advanced config new[/cyan]")
    else:
        print_error("No configuration found")
        console.print("  [dim]Run:[/dim] [cyan]kopi-docka advanced config new[/cyan]")




# -------------------------
# Registration
# -------------------------


def register(app: typer.Typer, hidden: bool = False):
    """Register all dependency commands."""

    @app.command("check", hidden=hidden)
    def _check_cmd(
        ctx: typer.Context,
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
        config: Optional[Path] = typer.Option(
            None,
            "--config",
            help="Path to configuration file",
        ),
    ):
        """Check system requirements and dependencies."""
        cmd_check(ctx, verbose, config)
