#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        __main__.py
# @module:      kopi_docka
# @description: CLI entry point - delegates to command modules
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.3
#
# ------------------------------------------------------------------------------ 
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Kopi-Docka — CLI Entry Point

Slim entry point that delegates to command modules.
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

# Import command registration functions
from .commands import (
    config_commands,
    dependency_commands,
    repository_commands,
    backup_commands,
    service_commands,
    dry_run_commands,
    setup_commands,
    disaster_recovery_commands,
)

app = typer.Typer(
    add_completion=False,
    help="Kopi-Docka – Backup & Restore for Docker using Kopia."
)
logger = get_logger(__name__)

# Commands that can run without root privileges
SAFE_COMMANDS = {"version", "show-deps", "show-config"}


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
    
    Also enforces root privileges for all commands except safe commands
    (version, show-deps, show-config).
    """
    # Root check for all commands except SAFE_COMMANDS
    if ctx.invoked_subcommand not in SAFE_COMMANDS:
        if os.geteuid() != 0:
            typer.echo("❌ Kopi-Docka benötigt Root-Rechte", err=True)
            typer.echo("\n💡 Führe alle Commands mit sudo aus:", err=True)
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
# Register Commands
# -------------------------

# Register all command modules
setup_commands.register(app)  # Master wizard first - most important!
config_commands.register(app)
dependency_commands.register(app)
repository_commands.register(app)
backup_commands.register(app)
service_commands.register(app)
dry_run_commands.register(app)
disaster_recovery_commands.register(app)



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
        logger.error(f"Unerwarteter Fehler: {e}", exc_info=True)
        typer.echo(f"❌ Unerwarteter Fehler: {e}", err=True)
        typer.echo("\n💡 Für Details siehe Logs oder führe mit --log-level=DEBUG aus", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
