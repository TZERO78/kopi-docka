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

# Import from helpers
from .helpers import Config, get_logger, log_manager
from .helpers.constants import VERSION

# Import top-level command modules
from .commands import (
    setup_commands,
    backup_commands,
    dry_run_commands,
    disaster_recovery_commands,
    doctor_commands,
)

# Import admin app from advanced module
from .commands.advanced import admin_app

app = typer.Typer(
    add_completion=False,
    help="Kopi-Docka – Backup & Restore for Docker using Kopia."
)
logger = get_logger(__name__)

# Commands that can run without root privileges
# Note: 'admin' is a group, so we check individual subcommands via ctx.invoked_subcommand
SAFE_COMMANDS = {"version", "doctor", "admin"}


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
            typer.echo("Kopi-Docka requires root privileges", err=True)
            typer.echo("\nRun commands with sudo:", err=True)
            cmd = " ".join(sys.argv)
            typer.echo(f"  sudo {cmd}", err=True)
            raise typer.Exit(code=13)  # EACCES

    # Set up logging
    try:
        log_manager.configure(level=log_level.upper())
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
setup_commands.register(app)           # 1. setup
backup_commands.register(app)          # 2. backup, 3. restore
dry_run_commands.register(app)         # 4. dry-run
disaster_recovery_commands.register(app)  # 5. disaster-recovery
doctor_commands.register(app)          # 6. doctor


# -------------------------
# Mount Admin Subcommand
# -------------------------

app.add_typer(
    admin_app,
    name="admin",
    help="Advanced administration tools for power users."
)


# -------------------------
# Version Command
# -------------------------

@app.command("version")
def cmd_version():
    """Show Kopi-Docka version."""
    typer.echo(f"Kopi-Docka {VERSION}")


# -------------------------
# Entrypoint
# -------------------------

def main():
    """
    Main entry point for the application.

    Note: Typer handles unknown commands itself with a nice box-formatted error.
    Root privileges are checked in initialize_context() for non-safe commands.
    We only handle:
    - KeyboardInterrupt: Clean exit
    - Unexpected errors: Show debug tip
    """
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("\nInterrupted.")
        sys.exit(130)
    except typer.Exit:
        # Re-raise typer exits (already handled)
        raise
    except Exception as e:
        # Unexpected error - show and exit
        logger.error(f"Unexpected error: {e}", exc_info=True)
        typer.echo(f"Unexpected error: {e}", err=True)
        typer.echo("\nFor details, check logs or run with --log-level=DEBUG", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
