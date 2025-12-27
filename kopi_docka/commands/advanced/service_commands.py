################################################################################
# KOPI-DOCKA
#
# @file:        service_commands.py
# @module:      kopi_docka.commands.advanced
# @description: Service management commands (admin service subgroup) - WRAPPER
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.4.1
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Service management commands under 'admin service'.

This is a thin wrapper that delegates to the legacy service_commands module.
All business logic resides in kopi_docka.commands.service_commands.

Commands:
- admin service daemon      - Run as systemd-friendly daemon
- admin service write-units - Write systemd unit files
"""

from pathlib import Path
from typing import Optional

import typer

# Import from legacy service_commands - Single Source of Truth
from ..service_commands import (
    cmd_daemon,
    cmd_write_units,
    cmd_manage,
)

# Create service subcommand group
service_app = typer.Typer(
    name="service",
    help="Systemd service management commands.",
    no_args_is_help=True,
)


# -------------------------
# Registration (wrappers)
# -------------------------


def register(app: typer.Typer):
    """Register service commands under 'admin service'."""

    @service_app.command("daemon")
    def _daemon_cmd(
        interval_minutes: Optional[int] = typer.Option(
            None, "--interval-minutes", help="Run backup every N minutes"
        ),
        backup_cmd: str = typer.Option("/usr/bin/env kopi-docka backup", "--backup-cmd"),
        log_level: str = typer.Option("INFO", "--log-level"),
    ):
        """Run the systemd-friendly daemon (service)."""
        cmd_daemon(interval_minutes, backup_cmd, log_level)

    @service_app.command("write-units")
    def _write_units_cmd(
        output_dir: Path = typer.Option(Path("/etc/systemd/system"), "--output-dir"),
    ):
        """Write example systemd service and timer units."""
        cmd_write_units(output_dir)

    @service_app.command("manage")
    def _manage_cmd():
        """Interactive service management wizard (requires root)."""
        cmd_manage()

    # Add service subgroup to admin app
    app.add_typer(service_app, name="service", help="Systemd service management")
