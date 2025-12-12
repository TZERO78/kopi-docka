################################################################################
# KOPI-DOCKA
#
# @file:        service_commands.py
# @module:      kopi_docka.commands.advanced
# @description: Service management commands (admin service subgroup)
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

Commands:
- admin service daemon      - Run as systemd-friendly daemon
- admin service write-units - Write systemd unit files
"""

from pathlib import Path
from typing import Optional

import typer

# Note: From advanced/ we need ...helpers (go up two levels)
from ...helpers import get_logger
from ...cores import KopiDockaService, ServiceConfig, write_systemd_units

logger = get_logger(__name__)

# Create service subcommand group
service_app = typer.Typer(
    name="service",
    help="Systemd service management commands.",
    no_args_is_help=True,
)


# -------------------------
# Commands
# -------------------------

def cmd_daemon(
    interval_minutes: Optional[int] = None,
    backup_cmd: str = "/usr/bin/env kopi-docka backup",
    log_level: str = "INFO",
):
    """Run the systemd-friendly daemon (service)."""
    cfg = ServiceConfig(
        backup_cmd=backup_cmd,
        interval_minutes=interval_minutes,
        log_level=log_level,
    )
    svc = KopiDockaService(cfg)
    rc = svc.start()
    raise typer.Exit(code=rc)


def cmd_write_units(output_dir: Path = Path("/etc/systemd/system")):
    """Write example systemd service and timer units."""
    try:
        write_systemd_units(output_dir)
        typer.echo(f"Unit files written to: {output_dir}")
        typer.echo("Enable with: sudo systemctl enable --now kopi-docka.timer")
    except Exception as e:
        typer.echo(f"Failed to write units: {e}")
        raise typer.Exit(code=1)


# -------------------------
# Registration
# -------------------------

def register(app: typer.Typer):
    """Register service commands under 'admin service'."""

    @service_app.command("daemon")
    def _daemon_cmd(
        interval_minutes: Optional[int] = typer.Option(
            None, "--interval-minutes", help="Run backup every N minutes"
        ),
        backup_cmd: str = typer.Option(
            "/usr/bin/env kopi-docka backup", "--backup-cmd"
        ),
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

    # Add service subgroup to admin app
    app.add_typer(service_app, name="service", help="Systemd service management")
