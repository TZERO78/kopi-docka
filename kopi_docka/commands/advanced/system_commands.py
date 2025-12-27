################################################################################
# KOPI-DOCKA
#
# @file:        system_commands.py
# @module:      kopi_docka.commands.advanced
# @description: System dependency commands (admin system subgroup) - WRAPPER
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

This is a thin wrapper that delegates to the legacy dependency_commands module.
All business logic resides in kopi_docka.commands.dependency_commands.

Commands:
- admin system install-deps - Install missing system dependencies
- admin system show-deps    - Show dependency installation guide
"""

import typer

# Import from legacy dependency_commands - Single Source of Truth
from ..dependency_commands import (
    cmd_install_deps,
    cmd_deps,  # show-deps
)

# Create system subcommand group
system_app = typer.Typer(
    name="system",
    help="System dependency management commands.",
    no_args_is_help=True,
)


# -------------------------
# Registration (wrappers)
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
        cmd_deps()

    # Add system subgroup to admin app
    app.add_typer(system_app, name="system", help="System dependency management")
