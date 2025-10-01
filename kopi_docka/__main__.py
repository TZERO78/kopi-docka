#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        __main__.py
# @module:      kopi_docka
# @description: CLI entry point - delegates to command modules
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------ 
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Kopi-Docka — CLI Entry Point

Slim entry point that delegates to command modules.
"""

from __future__ import annotations

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
)

app = typer.Typer(
    add_completion=False,
    help="Kopi-Docka – Backup & Restore for Docker using Kopia."
)
logger = get_logger(__name__)


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
    """
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
config_commands.register(app)
dependency_commands.register(app)
repository_commands.register(app)
backup_commands.register(app)
service_commands.register(app)


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
    """Main entry point for the application."""
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()