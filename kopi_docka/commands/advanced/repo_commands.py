################################################################################
# KOPI-DOCKA
#
# @file:        repo_commands.py
# @module:      kopi_docka.commands.advanced
# @description: Repository management commands (admin repo subgroup) - WRAPPER
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.4.1
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Repository management commands under 'admin repo'.

This is a thin wrapper that delegates to the legacy repository_commands module.
All business logic resides in kopi_docka.commands.repository_commands.

Commands:
- admin repo init           - Initialize repository
- admin repo status         - Show repository status
- admin repo init-path      - Create repository at specific path
- admin repo selftest       - Run repository self-test
- admin repo maintenance    - Run repository maintenance
- admin repo which-config   - Show which config file is used
- admin repo set-default    - Set as default Kopia config
- admin repo change-password - Change repository password
"""

from pathlib import Path
from typing import Optional

import typer

# Import from legacy repository_commands - Single Source of Truth
from ..repository_commands import (
    cmd_init,
    cmd_repo_status,
    cmd_repo_which_config,
    cmd_repo_set_default,
    cmd_repo_init_path,
    cmd_repo_selftest,
    cmd_repo_maintenance,
    cmd_change_password,
)

# Create repo subcommand group
repo_app = typer.Typer(
    name="repo",
    help="Repository management commands.",
    no_args_is_help=True,
)


# -------------------------
# Registration (wrappers)
# -------------------------


def register(app: typer.Typer):
    """Register repository commands under 'admin repo'."""

    @repo_app.command("init")
    def _repo_init_cmd(ctx: typer.Context):
        """Initialize (or connect to) the Kopia repository."""
        cmd_init(ctx)

    @repo_app.command("status")
    def _repo_status_cmd(ctx: typer.Context):
        """Show Kopia repository status and statistics."""
        cmd_repo_status(ctx)

    @repo_app.command("which-config")
    def _repo_which_config_cmd(ctx: typer.Context):
        """Show which Kopia config file is used."""
        cmd_repo_which_config(ctx)

    @repo_app.command("set-default")
    def _repo_set_default_cmd(ctx: typer.Context):
        """Point default Kopia config at current profile."""
        cmd_repo_set_default(ctx)

    @repo_app.command("init-path")
    def _repo_init_path_cmd(
        ctx: typer.Context,
        path: Path = typer.Argument(..., help="Repository path"),
        profile: Optional[str] = typer.Option(None, "--profile", help="Profile name"),
        set_default: bool = typer.Option(False, "--set-default/--no-set-default"),
        password: Optional[str] = typer.Option(None, "--password"),
    ):
        """Create a Kopia filesystem repository at PATH."""
        cmd_repo_init_path(ctx, path, profile, set_default, password)

    @repo_app.command("selftest")
    def _repo_selftest_cmd(
        tmpdir: Path = typer.Option(Path("/tmp"), "--tmpdir"),
        keep: bool = typer.Option(False, "--keep/--no-keep"),
        password: Optional[str] = typer.Option(None, "--password"),
    ):
        """Create ephemeral test repository."""
        cmd_repo_selftest(tmpdir, keep, password)

    @repo_app.command("maintenance")
    def _repo_maintenance_cmd(ctx: typer.Context):
        """Run Kopia repository maintenance."""
        cmd_repo_maintenance(ctx)

    @repo_app.command("change-password")
    def _change_password_cmd(
        ctx: typer.Context,
        new_password: Optional[str] = typer.Option(
            None, "--new-password", help="New password (will prompt if not provided)"
        ),
        use_file: bool = typer.Option(
            True, "--file/--inline", help="Store in external file (default) or inline in config"
        ),
    ):
        """Change Kopia repository password."""
        cmd_change_password(ctx, new_password, use_file)

    # Add repo subgroup to admin app
    app.add_typer(repo_app, name="repo", help="Repository management commands")
