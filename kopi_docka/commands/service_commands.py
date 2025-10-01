"""Service management commands."""

from pathlib import Path
from typing import Optional

import typer

from ..helpers import get_logger
from ..cores import KopiDockaService, ServiceConfig, write_systemd_units

logger = get_logger(__name__)


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
        typer.echo(f"✓ Unit files written to: {output_dir}")
        typer.echo("Enable with: sudo systemctl enable --now kopi-docka.timer")
    except Exception as e:
        typer.echo(f"Failed to write units: {e}")
        raise typer.Exit(code=1)


# -------------------------
# Registration
# -------------------------

def register(app: typer.Typer):
    """Register all service commands."""
    
    app.command("daemon")(
        lambda interval_minutes=typer.Option(None, "--interval-minutes", help="Run backup every N minutes"),
               backup_cmd=typer.Option("/usr/bin/env kopi-docka backup", "--backup-cmd"),
               log_level=typer.Option("INFO", "--log-level"):
            cmd_daemon(interval_minutes, backup_cmd, log_level)
    )
    
    app.command("write-units")(
        lambda output_dir=typer.Option(Path("/etc/systemd/system"), "--output-dir"):
            cmd_write_units(output_dir)
    )