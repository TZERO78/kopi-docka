################################################################################
# KOPI-DOCKA
#
# @file:        system_commands.py
# @module:      kopi_docka.commands.advanced
# @description: System dependency commands (admin system subgroup)
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.4.1
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
System dependency management commands under 'admin system'.

Commands:
- admin system install-deps - Install missing system dependencies
- admin system show-deps    - Show dependency installation guide
"""

from pathlib import Path

import typer

# Note: From advanced/ we need ...helpers (go up two levels)
from ...helpers import get_logger
from ...cores import DependencyManager

logger = get_logger(__name__)

# Create system subcommand group
system_app = typer.Typer(
    name="system",
    help="System dependency management commands.",
    no_args_is_help=True,
)


# -------------------------
# Commands
# -------------------------

def cmd_install_deps(force: bool = False, dry_run: bool = False):
    """Install missing system dependencies."""
    deps = DependencyManager()

    if dry_run:
        missing = deps.get_missing()
        if missing:
            deps.install_missing(dry_run=True)
        else:
            typer.echo("All dependencies already installed")
        return

    missing = deps.get_missing()
    if missing:
        success = deps.auto_install(force=force)
        if not success:
            raise typer.Exit(code=1)
        typer.echo(f"\nInstalled {len(missing)} dependencies")
    else:
        typer.echo("All required dependencies already installed")

    # Hint about config
    if not Path.home().joinpath(".config/kopi-docka/config.json").exists() and \
       not Path("/etc/kopi-docka.json").exists():
        typer.echo("\nTip: Create config with: kopi-docka admin config new")


def cmd_show_deps():
    """Show dependency installation guide."""
    deps = DependencyManager()
    deps.print_install_guide()


# -------------------------
# Registration
# -------------------------

def register(app: typer.Typer):
    """Register system commands under 'admin system'."""

    @system_app.command("install-deps")
    def _install_deps_cmd(
        force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be installed"),
    ):
        """Install missing system dependencies."""
        cmd_install_deps(force, dry_run)

    @system_app.command("show-deps")
    def _show_deps_cmd():
        """Show dependency installation guide."""
        cmd_show_deps()

    # Add system subgroup to admin app
    app.add_typer(system_app, name="system", help="System dependency management")
