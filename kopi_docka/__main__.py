#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        __main__.py
# @module:      kopi_docka
# @description: CLI entry point - delegates to command modules
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.4.1
#
# ------------------------------------------------------------------------------
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Kopi-Docka — CLI Entry Point

Slim entry point that delegates to command modules.

CLI Structure (v3.4.0):
=======================

Top-Level Commands ("The Big 6"):
  setup             - Complete setup wizard
  backup            - Run backup
  restore           - Launch restore wizard
  disaster-recovery - Create recovery bundle
  dry-run           - Simulate backup (preview)
  doctor            - System health check
  version           - Show version

Admin Commands (Advanced):
  admin config      - Configuration management
  admin repo        - Repository management
  admin service     - Systemd service management
  admin system      - System dependency management
  admin snapshot    - Snapshot/unit management
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

# Configure rich-click for beautiful --help output
# This must be done before any typer commands are defined
try:
    import rich_click as click

    click.rich_click.USE_RICH_MARKUP = True
    click.rich_click.USE_MARKDOWN = True
    click.rich_click.SHOW_ARGUMENTS = True
    click.rich_click.GROUP_ARGUMENTS_OPTIONS = True
    click.rich_click.STYLE_COMMANDS_TABLE = "bold cyan"
    click.rich_click.STYLE_OPTIONS_TABLE_LEADING = 1
    click.rich_click.STYLE_OPTIONS_TABLE_BOX = "SIMPLE"
except ImportError:
    pass  # Fallback to plain typer if rich-click not available

console = Console()
err_console = Console(stderr=True)

# Import from helpers
from .helpers import Config, get_logger, log_manager
from .helpers.constants import VERSION

# Import version for dynamic help header
from . import __version__

# Import top-level command modules
from .commands import (
    setup_commands,
    backup_commands,
    dry_run_commands,
    disaster_recovery_commands,
    doctor_commands,
    dependency_commands,
    repository_commands,
)
from .commands.service_commands import cmd_daemon

# Import admin app from advanced module
from .commands.advanced import admin_app

app = typer.Typer(
    add_completion=False,
    help=f"Kopi-Docka v{__version__} – Backup & Restore for Docker using Kopia.",
)
logger = get_logger(__name__)

# Commands that can run without root privileges
# Note: 'admin' is a group, so we check individual subcommands via ctx.invoked_subcommand
SAFE_COMMANDS = {"version", "doctor", "admin", "advanced", "check", "show-deps"}


# -------------------------
# Application Context Setup
# -------------------------


@app.callback()
def initialize_context(
    ctx: typer.Context,
    config_path: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to configuration file.",
        envvar="KOPI_DOCKA_CONFIG",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Log level (DEBUG, INFO, WARNING, ERROR).",
        envvar="KOPI_DOCKA_LOG_LEVEL",
    ),
):
    """
    Initialize application context before any command runs.
    Sets up logging and loads configuration once.

    Also enforces root privileges for all commands except safe commands.
    """
    # Root check for all commands except SAFE_COMMANDS
    if ctx.invoked_subcommand not in SAFE_COMMANDS:
        if os.geteuid() != 0:
            cmd = " ".join(sys.argv)
            err_console.print(
                Panel.fit(
                    "[red]Kopi-Docka requires root privileges[/red]\n"
                    "[red]Root-Rechte erforderlich (benötigt Root)[/red]\n\n"
                    "[bold]Run with sudo:[/bold]\n"
                    f"  [cyan]sudo {cmd}[/cyan]",
                    title="[bold red]Permission Denied[/bold red]",
                    border_style="red",
                )
            )
            raise typer.Exit(code=13)  # EACCES

    # Set up logging
    try:
        log_manager.setup(level=log_level.upper())
    except Exception:
        import logging

        logging.basicConfig(level=log_level.upper())

    # Initialize context
    ctx.ensure_object(dict)

    # Load configuration once
    try:
        if config_path and config_path.exists():
            cfg = Config(config_path)
        else:
            cfg = Config()
    except Exception:
        cfg = None

    ctx.obj["config"] = cfg
    ctx.obj["config_path"] = config_path


# -------------------------
# Register Top-Level Commands
# -------------------------

# "The Big 6" - Most commonly used commands
setup_commands.register(app)  # 1. setup
backup_commands.register(app)  # 2. backup, 3. restore
dry_run_commands.register(app)  # 4. dry-run
disaster_recovery_commands.register(app)  # 5. disaster-recovery
doctor_commands.register(app)  # 6. doctor
dependency_commands.register(app, hidden=True)  # Dependency management (hidden wrappers)
repository_commands.register(app, hidden=True)  # Repository management (hidden wrappers)


# -------------------------
# Mount Admin Subcommand
# -------------------------

app.add_typer(admin_app, name="advanced", help="Advanced tools (Config, Repo, System).")
# Legacy alias for backward compatibility (hidden from help)
app.add_typer(admin_app, name="admin", hidden=True)


# -------------------------
# Version Command
# -------------------------


@app.command("version")
def cmd_version():
    """Show Kopi-Docka version."""
    console.print(f"[bold cyan]Kopi-Docka[/bold cyan] [green]{VERSION}[/green] " "(compat 1.0.0)")


@app.command("daemon", hidden=True)
def cmd_daemon_alias(
    interval_minutes: int = typer.Option(
        60, "--interval-minutes", "-i", help="Run backups every N minutes"
    ),
    backup_cmd: Optional[str] = typer.Option(
        None,
        "--backup-cmd",
        help="Custom backup command to run (default: 'kopi-docka backup')",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Log level for daemon (DEBUG, INFO, WARNING, ERROR)",
    ),
):
    """Run the systemd-friendly daemon (alias for advanced service daemon)."""
    cmd_daemon(interval_minutes, backup_cmd, log_level)


# -------------------------
# Entrypoint
# -------------------------


def main():
    """
    Main entry point for the application.

    Note: Typer handles unknown commands itself with a nice box-formatted error.
    Root privileges are checked in initialize_context() for non-safe commands.
    We only handle:
    - KeyboardInterrupt: Clean exit (fallback - SafeExitManager handles signals)
    - Unexpected errors: Show debug tip
    """
    # Install SafeExitManager signal handlers for graceful shutdown (v5.5.0)
    # This ensures cleanup happens on SIGINT/SIGTERM (Ctrl+C, systemctl stop)
    from .cores.safe_exit_manager import SafeExitManager

    SafeExitManager.get_instance().install_handlers()

    try:
        app()
    except KeyboardInterrupt:
        # Fallback handler - SafeExitManager should handle SIGINT and exit with code 130
        # This path is reached if KeyboardInterrupt is raised before signal handler is active
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except typer.Exit:
        # Re-raise typer exits (already handled)
        raise
    except Exception as e:
        # Unexpected error - show and exit
        logger.error(f"Unexpected error: {e}", exc_info=True)
        err_console.print(
            Panel.fit(
                f"[red]Unexpected error:[/red]\n{e}\n\n"
                "[dim]For details, run with --log-level=DEBUG[/dim]",
                title="[bold red]Error[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
