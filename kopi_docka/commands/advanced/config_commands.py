################################################################################
# KOPI-DOCKA
#
# @file:        config_commands.py
# @module:      kopi_docka.commands.advanced
# @description: Configuration management commands (admin config subgroup)
#               Thin wrapper around legacy config_commands.py
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.5.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Configuration management commands under 'admin config'.

This module is a thin wrapper that delegates to config_commands.py.
All business logic is in the legacy module to avoid code duplication.

Commands:
- admin config show            - Show current configuration
- admin config new             - Create new configuration
- admin config edit            - Edit configuration file
- admin config reset           - Reset configuration (DANGEROUS)
- admin config status          - Show repository storage status
- admin config change-password - Change repository password
"""

from pathlib import Path
from typing import Optional

import typer

# Import from legacy config_commands - Single Source of Truth
from ..config_commands import (
    cmd_config,  # show
    cmd_new_config,  # new (FIXED: detect_repository_type, terminology)
    cmd_edit_config,  # edit
    cmd_reset_config,  # reset
    cmd_status,  # status (FIXED: dead code removed)
    cmd_change_password,  # change-password
)

# Create config subcommand group
config_app = typer.Typer(
    name="config",
    help="Configuration management commands.",
    no_args_is_help=True,
)


# -------------------------
# Registration
# -------------------------


def register(app: typer.Typer):
    """Register configuration commands under 'admin config'."""

    @config_app.command("show")
    def _config_show_cmd(ctx: typer.Context):
        """Show current configuration."""
        cmd_config(ctx, show=True)

    @config_app.command("new")
    def _config_new_cmd(
        force: bool = typer.Option(
            False, "--force", "-f", help="Overwrite existing config (with warnings)"
        ),
        edit: bool = typer.Option(True, "--edit/--no-edit", help="Open in editor after creation"),
        path: Optional[Path] = typer.Option(None, "--path", help="Custom config path"),
    ):
        """Create new configuration file with interactive setup wizard."""
        cmd_new_config(force=force, edit=edit, path=path)

    @config_app.command("edit")
    def _config_edit_cmd(
        ctx: typer.Context,
        editor: Optional[str] = typer.Option(None, "--editor", help="Specify editor to use"),
    ):
        """Edit existing configuration file."""
        cmd_edit_config(ctx, editor)

    @config_app.command("reset")
    def _config_reset_cmd(
        path: Optional[Path] = typer.Option(None, "--path", help="Custom config path"),
    ):
        """Reset configuration completely (DANGEROUS - creates new password!)."""
        cmd_reset_config(path)

    @config_app.command("status")
    def _config_status_cmd(ctx: typer.Context):
        """Show detailed repository storage status."""
        cmd_status(ctx)

    @config_app.command("change-password")
    def _config_change_password_cmd(ctx: typer.Context):
        """Change repository encryption password."""
        cmd_change_password(ctx)

    # Add config subgroup to admin app
    app.add_typer(config_app, name="config", help="Configuration management commands")
