################################################################################
# KOPI-DOCKA
#
# @file:        main.py
# @module:      kopi_docka.main
# @description: Typer-based CLI entry point orchestrating Kopi-Docka operations.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Implements commands for version, init, list, backup, restore, and maintenance
# - Centralizes config loading via _load_config helper
# - Integrates service helpers to manage systemd daemon and unit files
################################################################################

"""
Kopi-Docka — main CLI

English CLI that exposes backup, restore, listing, repo maintenance,
and integrates the systemd-friendly daemon (service.py).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, List

import typer

from .constants import VERSION
from .config import Config
from .logging import get_logger, log_manager
from .discovery import DockerDiscovery
from .backup import BackupManager
from .restore import RestoreManager
from .repository import KopiaRepository
from .dry_run import DryRunReport
from .service import (
    KopiDockaService,
    ServiceConfig,
    write_systemd_units,
)

app = typer.Typer(
    add_completion=False, help="Kopi-Docka – Backup & Restore for Docker using Kopia."
)
logger = get_logger(__name__)


# -------------------------
# Helpers
# -------------------------


def _load_config(config_path: Optional[Path]) -> Config:
    # If your Config supports an explicit path, use it; otherwise rely on its defaults.
    if config_path:
        return Config(config_path)
    return Config()


def _filter_units(all_units, names: Optional[List[str]]):
    if not names:
        return all_units
    wanted = set(names)
    return [u for u in all_units if u.name in wanted]


# -------------------------
# Global options via callback
# -------------------------


@app.callback()
def _entry(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to configuration file."
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Log level (DEBUG, INFO, WARNING, ERROR)."
    ),
):
    """
    Initialize logging and configuration before running a subcommand.
    """
    # Configure logging early
    try:
        log_manager.configure(level=log_level.upper())
    except Exception:
        # Fallback if custom manager errors
        pass

    ctx.obj = {"config": _load_config(config)}


# -------------------------
# Commands
# -------------------------


@app.command("version")
def cmd_version():
    """Show Kopi-Docka version."""
    typer.echo(f"Kopi-Docka {VERSION}")


@app.command("init")
def cmd_init(ctx: typer.Context):
    """
    Initialize (or connect to) the Kopia repository.
    """
    cfg: Config = ctx.obj["config"]
    repo = KopiaRepository(cfg)

    if repo.is_initialized():
        typer.echo("Repository already initialized. Connecting…")
        try:
            repo.connect()
            typer.echo("Connected to repository.")
        except Exception as e:
            typer.echo(f"Failed to connect: {e}")
            raise typer.Exit(code=1)
        return

    typer.echo("Initializing repository…")
    try:
        repo.initialize()
        typer.echo("Repository initialized successfully.")
    except Exception as e:
        typer.echo(f"Failed to initialize repository: {e}")
        raise typer.Exit(code=1)


@app.command("list")
def cmd_list(
    ctx: typer.Context,
    units: bool = typer.Option(True, "--units", help="List discovered backup units."),
    snapshots: bool = typer.Option(False, "--snapshots", help="List recent snapshots."),
):
    """
    List backup units or repository snapshots.
    """
    cfg: Config = ctx.obj["config"]
    if not (units or snapshots):
        units = True  # default behavior

    if units:
        typer.echo("Discovering Docker backup units…")
        try:
            discovery = DockerDiscovery()
            found = discovery.discover_backup_units()
            if not found:
                typer.echo("No units found.")
            else:
                for u in found:
                    typer.echo(
                        f"- {u.name} ({u.type}): {len(u.containers)} containers, {len(u.volumes)} volumes"
                    )
        except Exception as e:
            typer.echo(f"Discovery failed: {e}")
            raise typer.Exit(code=1)

    if snapshots:
        typer.echo("\nListing snapshots (repository)…")
        try:
            repo = KopiaRepository(cfg)
            snaps = repo.list_snapshots()
            if not snaps:
                typer.echo("No snapshots found.")
            else:
                for s in snaps:
                    unit = s.get("tags", {}).get("unit", "-")
                    ts = s.get("timestamp", "-")
                    sid = s.get("id", "")
                    typer.echo(
                        f"- {sid} | unit={unit} | {ts} | path={s.get('path','')}"
                    )
        except Exception as e:
            typer.echo(f"Unable to list snapshots: {e}")
            raise typer.Exit(code=1)


@app.command("backup")
def cmd_backup(
    ctx: typer.Context,
    unit: List[str] = typer.Option(
        None, "--unit", "-u", help="Backup only these units (repeatable)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Simulate backup without making changes."
    ),
    update_recovery_bundle: Optional[bool] = typer.Option(
        None,
        "--update-recovery/--no-update-recovery",
        help="Override config: update disaster recovery bundle after backup.",
    ),
):
    """
    Run a cold backup for selected units (or all).
    """
    cfg: Config = ctx.obj["config"]

    try:
        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()
        selected = _filter_units(units, unit)
        if not selected:
            typer.echo("Nothing to back up (no units selected/found).")
            raise typer.Exit(code=0)

        if dry_run:
            report = DryRunReport(cfg)
            report.generate(selected, update_recovery_bundle)
            raise typer.Exit(code=0)

        bm = BackupManager(cfg)
        overall_ok = True

        for u in selected:
            typer.echo(f"==> Backing up unit: {u.name}")
            meta = bm.backup_unit(u, update_recovery_bundle=update_recovery_bundle)
            if meta.success:
                typer.echo(f"✓ {u.name} completed in {int(meta.duration_seconds)}s")
                if meta.kopia_snapshot_ids:
                    typer.echo(f"   Snapshots: {', '.join(meta.kopia_snapshot_ids)}")
            else:
                overall_ok = False
                typer.echo(
                    f"✗ {u.name} finished with errors in {int(meta.duration_seconds)}s"
                )
                for err in meta.errors or (
                    [] if meta.error_message is None else [meta.error_message]
                ):
                    typer.echo(f"   - {err}")

        raise typer.Exit(code=0 if overall_ok else 1)

    except Exception as e:
        typer.echo(f"Backup failed: {e}")
        raise typer.Exit(code=1)


@app.command("restore")
def cmd_restore(ctx: typer.Context):
    """
    Launch the interactive restore wizard.
    """
    cfg: Config = ctx.obj["config"]
    try:
        rm = RestoreManager(cfg)
        rm.interactive_restore()
    except Exception as e:
        typer.echo(f"Restore failed: {e}")
        raise typer.Exit(code=1)


@app.command("repo-maintenance")
def cmd_repo_maintenance(ctx: typer.Context):
    """
    Run Kopia repository maintenance.
    """
    cfg: Config = ctx.obj["config"]
    try:
        repo = KopiaRepository(cfg)
        repo.maintenance_run()
        typer.echo("Maintenance completed.")
    except Exception as e:
        typer.echo(f"Maintenance failed: {e}")
        raise typer.Exit(code=1)


# -------------------------
# Service / systemd helpers
# -------------------------


@app.command("daemon")
def cmd_daemon(
    interval_minutes: Optional[int] = typer.Option(
        None,
        "--interval-minutes",
        help="Run internal backup every N minutes (else idle; prefer systemd timer).",
    ),
    backup_cmd: str = typer.Option(
        "/usr/bin/env kopi-docka backup",
        "--backup-cmd",
        help="Command to start a backup run.",
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Log level used by the service."
    ),
):
    """
    Run the systemd-friendly daemon (service). Prefer using a systemd timer for scheduling.
    """
    cfg = ServiceConfig(
        backup_cmd=backup_cmd,
        interval_minutes=interval_minutes,
        log_level=log_level,
    )
    svc = KopiDockaService(cfg)
    rc = svc.start()
    raise typer.Exit(code=rc)


@app.command("write-units")
def cmd_write_units(
    output_dir: Path = typer.Option(
        Path("/etc/systemd/system"),
        "--output-dir",
        help="Where to write example systemd unit files.",
    )
):
    """
    Write example systemd service and timer units.
    """
    try:
        write_systemd_units(output_dir)
        typer.echo(f"Wrote unit files into: {output_dir}")
        typer.echo("Enable with:  sudo systemctl enable --now kopi-docka.timer")
    except Exception as e:
        typer.echo(f"Failed to write units: {e}")
        raise typer.Exit(code=1)


# -------------------------
# Entrypoint
# -------------------------


def main():
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("Interrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
