#!/usr/bin/env python3
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
# - Uses DependencyManager for system requirement checks
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
from .config import Config, create_default_config
from .dependencies import DependencyManager
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


def _load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from path or defaults."""
    if config_path and config_path.exists():
        return Config(config_path)
    
    # Try default locations
    try:
        return Config()
    except:
        # No config exists yet
        return None


def _filter_units(all_units, names: Optional[List[str]]):
    """Filter backup units by name."""
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
        import logging
        logging.basicConfig(level=log_level.upper())

    ctx.obj = {"config_path": config}


# -------------------------
# Version Command
# -------------------------


@app.command("version")
def cmd_version():
    """Show Kopi-Docka version."""
    typer.echo(f"Kopi-Docka {VERSION}")


# -------------------------
# Dependency Management Commands
# -------------------------


@app.command("check")
def cmd_check(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
):
    """Check system requirements and dependencies."""
    deps = DependencyManager()
    deps.print_status(verbose=verbose)
    
    # Check repository status
    cfg = _load_config(ctx.obj.get("config_path"))
    if cfg:
        try:
            repo = KopiaRepository(cfg)
            if repo.is_initialized():
                typer.echo("✓ Kopia repository is initialized")
            else:
                typer.echo("✗ Kopia repository not initialized")
                typer.echo("  Run: kopi-docka init")
        except Exception as e:
            typer.echo(f"✗ Repository check failed: {e}")
    else:
        typer.echo("✗ No configuration found")
        typer.echo("  Run: kopi-docka new-config")


@app.command("install-deps")
def cmd_install_deps(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be installed"),
):
    """Install missing system dependencies."""
    deps = DependencyManager()
    
    if dry_run:
        missing = deps.get_missing()
        if missing:
            deps.install_missing(dry_run=True)
        else:
            typer.echo("✓ All dependencies already installed")
        return
    
    # Install missing dependencies
    missing = deps.get_missing()
    if missing:
        success = deps.auto_install(force=force)
        if not success:
            raise typer.Exit(code=1)
        typer.echo(f"\n✓ Installed {len(missing)} dependencies")
    else:
        typer.echo("✓ All required dependencies already installed")
    
    # Just hint about config, don't create/edit
    cfg = _load_config()
    if not cfg or not cfg.config_file.exists():
        typer.echo("\n💡 Tip: Create config with: kopi-docka new-config")


@app.command("deps")
def cmd_deps():
    """Show dependency installation guide."""
    deps = DependencyManager()
    deps.print_install_guide()


# -------------------------
# Configuration Commands
# -------------------------


@app.command("config")
def cmd_config(
    ctx: typer.Context,
    show: bool = typer.Option(True, "--show", help="Show current configuration"),
):
    """Show current configuration."""
    cfg = _load_config(ctx.obj.get("config_path"))
    
    if not cfg or not cfg.config_file.exists():
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka new-config")
        raise typer.Exit(code=1)
    
    # Display configuration
    import configparser
    typer.echo(f"Configuration file: {cfg.config_file}")
    typer.echo("=" * 60)
    
    config = configparser.ConfigParser()
    config.read(cfg.config_file)
    
    for section in config.sections():
        typer.echo(f"\n[{section}]")
        for option, value in config.items(section):
            # Mask sensitive values
            if 'password' in option.lower() or 'token' in option.lower():
                value = '***MASKED***'
            typer.echo(f"  {option} = {value}")


@app.command("new-config")
def cmd_new_config(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
    edit: bool = typer.Option(True, "--edit/--no-edit", help="Open in editor after creation"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Custom config path"),
):
    """Create new configuration file."""
    import subprocess
    import os
    
    # Check if exists
    cfg = _load_config(path)
    if cfg and cfg.config_file.exists() and not force:
        typer.echo(f"⚠️ Config already exists at: {cfg.config_file}")
        typer.echo("Use --force to overwrite or 'edit-config' to modify")
        raise typer.Exit(code=1)
    
    # Create config
    typer.echo("Creating new configuration...")
    create_default_config(path, force)  # Beide Parameter sind optional
    
    # Load to get path
    cfg = Config(path) if path else Config()
    typer.echo(f"✓ Config created at: {cfg.config_file}")
    
    if edit:
        editor = os.environ.get('EDITOR', 'nano')
        typer.echo(f"\nOpening in {editor} for initial setup...")
        typer.echo("Important settings to configure:")
        typer.echo("  • repository_path - Where to store backups")
        typer.echo("  • password - Strong password for encryption")
        typer.echo("  • backup paths - Adjust for your system")
        subprocess.call([editor, str(cfg.config_file)])


@app.command("edit-config")
def cmd_edit_config(
    ctx: typer.Context,
    editor: Optional[str] = typer.Option(None, "--editor", "-e", help="Specify editor to use"),
):
    """Edit existing configuration file."""
    import subprocess
    import os
    
    cfg = _load_config(ctx.obj.get("config_path"))
    
    if not cfg or not cfg.config_file.exists():
        typer.echo(f"❌ No config found")
        typer.echo("Run: kopi-docka new-config")
        raise typer.Exit(code=1)
    
    # Use specified editor or default
    if not editor:
        editor = os.environ.get('EDITOR', 'nano')
    
    typer.echo(f"Opening {cfg.config_file} in {editor}...")
    subprocess.call([editor, str(cfg.config_file)])
    
    # Validate after editing
    try:
        cfg_test = Config(cfg.config_file)
        typer.echo("✓ Configuration valid")
    except Exception as e:
        typer.echo(f"⚠️ Configuration might have issues: {e}")


# -------------------------
# Repository Commands
# -------------------------


@app.command("init")
def cmd_init(ctx: typer.Context):
    """
    Initialize (or connect to) the Kopia repository.
    """
    # Check dependencies first
    deps = DependencyManager()
    missing = deps.get_missing()
    
    if missing:
        typer.echo("⚠ Missing required dependencies:")
        for dep in missing:
            typer.echo(f"  - {dep}")
        typer.echo("\nRun: kopi-docka install-deps")
        raise typer.Exit(code=1)
    
    cfg = _load_config(ctx.obj.get("config_path"))
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka new-config")
        raise typer.Exit(code=1)
    
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


# -------------------------
# Backup/Restore Commands
# -------------------------


@app.command("list")
def cmd_list(
    ctx: typer.Context,
    units: bool = typer.Option(True, "--units", help="List discovered backup units."),
    snapshots: bool = typer.Option(False, "--snapshots", help="List recent snapshots."),
):
    """
    List backup units or repository snapshots.
    """
    cfg = _load_config(ctx.obj.get("config_path"))
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka new-config")
        raise typer.Exit(code=1)
    
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
    # Pre-flight dependency check
    deps = DependencyManager()
    missing = deps.get_missing()
    if missing:
        typer.echo("⚠ Missing required dependencies. Run: kopi-docka check")
        raise typer.Exit(code=1)
    
    cfg = _load_config(ctx.obj.get("config_path"))
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka new-config")
        raise typer.Exit(code=1)

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
    cfg = _load_config(ctx.obj.get("config_path"))
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka new-config")
        raise typer.Exit(code=1)
    
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
    cfg = _load_config(ctx.obj.get("config_path"))
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka new-config")
        raise typer.Exit(code=1)
    
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
    """Main entry point for the application."""
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("Interrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()