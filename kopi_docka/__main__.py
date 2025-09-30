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
################################################################################

"""
Kopi-Docka — main CLI

Typer-based CLI following the "Werkzeugtisch" (tool bench) pattern:
- Configuration is loaded once at startup
- Commands retrieve tools from context instead of parameters
- No custom types in function signatures
"""

from __future__ import annotations

import sys
import shutil
import subprocess
import os
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
    add_completion=False, 
    help="Kopi-Docka – Backup & Restore for Docker using Kopia."
)
logger = get_logger(__name__)


# -------------------------
# Application Context
# -------------------------

@app.callback()
def initialize_context(
    ctx: typer.Context,
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to configuration file."
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Log level (DEBUG, INFO, WARNING, ERROR)."
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
# Helper Functions
# -------------------------

def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from the tool bench."""
    return ctx.obj.get("config")


def get_repository(ctx: typer.Context) -> Optional[KopiaRepository]:
    """Get or create repository from the tool bench."""
    if "repository" not in ctx.obj:
        cfg = get_config(ctx)
        if cfg:
            ctx.obj["repository"] = KopiaRepository(cfg)
    return ctx.obj.get("repository")


def ensure_config(ctx: typer.Context) -> Config:
    """Ensure config exists or exit."""
    cfg = get_config(ctx)
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka new-config")
        raise typer.Exit(code=1)
    return cfg


def ensure_dependencies():
    """Ensure all dependencies are installed or exit."""
    deps = DependencyManager()
    missing = deps.get_missing()
    if missing:
        typer.echo("⚠ Missing required dependencies:")
        for dep in missing:
            typer.echo(f"  - {dep}")
        typer.echo("\nRun: kopi-docka install-deps")
        raise typer.Exit(code=1)


def ensure_repository(ctx: typer.Context) -> KopiaRepository:
    """Ensure repository is initialized or exit."""
    repo = get_repository(ctx)
    if not repo:
        typer.echo("❌ Repository not available")
        raise typer.Exit(code=1)
    
    if not repo.is_initialized():
        typer.echo("✗ Kopia repository not initialized")
        typer.echo("Run: kopi-docka init")
        raise typer.Exit(code=1)
    
    return repo


def _filter_units(all_units, names: Optional[List[str]]):
    """Filter backup units by name."""
    if not names:
        return all_units
    wanted = set(names)
    return [u for u in all_units if u.name in wanted]


# -------------------------
# Version & Help
# -------------------------

@app.command("version")
def cmd_version():
    """Show Kopi-Docka version."""
    typer.echo(f"Kopi-Docka {VERSION}")


# -------------------------
# Dependency Management
# -------------------------

@app.command("check")
def cmd_check(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
):
    """Check system requirements and dependencies."""
    deps = DependencyManager()
    deps.print_status(verbose=verbose)
    
    # Check repository if config exists
    cfg = get_config(ctx)
    if cfg:
        try:
            repo = KopiaRepository(cfg)
            if repo.is_initialized():
                typer.echo("✓ Kopia repository is initialized")
                typer.echo(f"  Profile: {repo.profile_name}")
                typer.echo(f"  Repository: {repo.repo_path}")
                if verbose:
                    snapshots = repo.list_snapshots()
                    typer.echo(f"  Snapshots: {len(snapshots)}")
                    units = repo.list_backup_units()
                    typer.echo(f"  Backup units: {len(units)}")
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
    
    missing = deps.get_missing()
    if missing:
        success = deps.auto_install(force=force)
        if not success:
            raise typer.Exit(code=1)
        typer.echo(f"\n✓ Installed {len(missing)} dependencies")
    else:
        typer.echo("✓ All required dependencies already installed")
    
    # Hint about config
    if not Path.home().joinpath(".config/kopi-docka/config.conf").exists() and \
       not Path("/etc/kopi-docka.conf").exists():
        typer.echo("\n💡 Tip: Create config with: kopi-docka new-config")


@app.command("deps")
def cmd_deps():
    """Show dependency installation guide."""
    deps = DependencyManager()
    deps.print_install_guide()


# -------------------------
# Configuration Management
# -------------------------

@app.command("config")
def cmd_config(
    ctx: typer.Context,
    show: bool = typer.Option(True, "--show", help="Show current configuration"),
):
    """Show current configuration."""
    cfg = ensure_config(ctx)
    
    import configparser
    typer.echo(f"Configuration file: {cfg.config_file}")
    typer.echo("=" * 60)
    
    config = configparser.ConfigParser()
    config.read(cfg.config_file)
    
    for section in config.sections():
        typer.echo(f"\n[{section}]")
        for option, value in config.items(section):
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
    # Check if config exists
    existing_cfg = None
    try:
        if path:
            existing_cfg = Config(path)
        else:
            existing_cfg = Config()
    except:
        pass  # Config doesn't exist, that's fine
    
    if existing_cfg and existing_cfg.config_file.exists() and not force:
        typer.echo(f"⚠️ Config already exists at: {existing_cfg.config_file}")
        typer.echo("Use --force to overwrite or 'edit-config' to modify")
        raise typer.Exit(code=1)
    
    typer.echo("Creating new configuration...")
    created_path = create_default_config(path, force)
    typer.echo(f"✓ Config created at: {created_path}")
    
    if edit:
        editor = os.environ.get('EDITOR', 'nano')
        typer.echo(f"\nOpening in {editor} for initial setup...")
        typer.echo("Important settings to configure:")
        typer.echo("  • repository_path - Where to store backups")
        typer.echo("  • password - Strong password for encryption")
        typer.echo("  • backup paths - Adjust for your system")
        subprocess.call([editor, str(created_path)])


@app.command("edit-config")
def cmd_edit_config(
    ctx: typer.Context,
    editor: Optional[str] = typer.Option(None, "--editor", "-e", help="Specify editor to use"),
):
    """Edit existing configuration file."""
    cfg = ensure_config(ctx)
    
    if not editor:
        editor = os.environ.get('EDITOR', 'nano')
    
    typer.echo(f"Opening {cfg.config_file} in {editor}...")
    subprocess.call([editor, str(cfg.config_file)])
    
    # Validate after editing
    try:
        Config(cfg.config_file)
        typer.echo("✓ Configuration valid")
    except Exception as e:
        typer.echo(f"⚠️ Configuration might have issues: {e}")


# -------------------------
# Repository Operations
# -------------------------

@app.command("init")
def cmd_init(ctx: typer.Context):
    """Initialize (or connect to) the Kopia repository."""
    # Check Kopia first
    if not shutil.which("kopia"):
        typer.echo("❌ Kopia is not installed!")
        typer.echo("Install with: kopi-docka install-deps")
        raise typer.Exit(code=1)
    
    # Check dependencies
    ensure_dependencies()
    
    # Get config
    cfg = ensure_config(ctx)
    
    # Create repository
    repo = KopiaRepository(cfg)
    
    typer.echo(f"Using profile: {repo.profile_name}")
    typer.echo(f"Repository: {repo.repo_path}")

    if repo.is_initialized():
        typer.echo("Repository already initialized. Connecting…")
        try:
            repo.connect()
            typer.echo("✓ Connected to repository")
        except Exception as e:
            typer.echo(f"Failed to connect: {e}")
            raise typer.Exit(code=1)
        return

    typer.echo("Initializing repository…")
    try:
        repo.initialize()
        typer.echo("✓ Repository initialized successfully")
        typer.echo(f"✓ Profile '{repo.profile_name}' configured")
    except Exception as e:
        typer.echo(f"Failed to initialize repository: {e}")
        raise typer.Exit(code=1)


@app.command("repo-maintenance")
def cmd_repo_maintenance(ctx: typer.Context):
    """Run Kopia repository maintenance."""
    ensure_config(ctx)
    repo = ensure_repository(ctx)
    
    try:
        repo.maintenance_run()
        typer.echo("✓ Maintenance completed")
    except Exception as e:
        typer.echo(f"Maintenance failed: {e}")
        raise typer.Exit(code=1)
    
@app.command("repo-status")
def cmd_repo_status(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed repository info"),
):
    """Show Kopia repository status and statistics."""
    cfg = ensure_config(ctx)
    repo = ensure_repository(ctx)
    
    try:
        typer.echo("=" * 60)
        typer.echo("KOPIA REPOSITORY STATUS")
        typer.echo("=" * 60)
        
        # Basic repo info
        typer.echo(f"\nProfile: {repo.profile_name}")
        typer.echo(f"Repository: {repo.repo_path}")
        typer.echo(f"Connected: {'✓' if repo.is_initialized() else '✗'}")
        
        # Get snapshots
        snapshots = repo.list_snapshots()
        typer.echo(f"\nTotal Snapshots: {len(snapshots)}")
        
        # Get backup units
        units = repo.list_backup_units()
        typer.echo(f"Backup Units: {len(units)}")
        
        if verbose and snapshots:
            typer.echo("\n" + "-" * 60)
            typer.echo("RECENT SNAPSHOTS")
            typer.echo("-" * 60)
            
            # Show last 10 snapshots
            recent = snapshots[-10:] if len(snapshots) > 10 else snapshots
            for snap in reversed(recent):
                unit = snap.get("tags", {}).get("unit", "unknown")
                timestamp = snap.get("timestamp", "unknown")
                snap_id = snap.get("id", "")[:12]
                typer.echo(f"  {snap_id} | {unit:<20} | {timestamp}")
        
        if verbose and units:
            typer.echo("\n" + "-" * 60)
            typer.echo("BACKUP UNITS")
            typer.echo("-" * 60)
            for unit_name in units:
                typer.echo(f"  • {unit_name}")
        
        typer.echo("\n" + "=" * 60)
        
        # Call native kopia status for detailed info
        if verbose:
            typer.echo("\nDetailed Kopia Status:")
            typer.echo("-" * 60)
            repo.status()
        
    except Exception as e:
        typer.echo(f"✗ Failed to get repository status: {e}")
        raise typer.Exit(code=1)
    
# -------------------------
# Backup & Restore
# -------------------------

@app.command("list")
def cmd_list(
    ctx: typer.Context,
    units: bool = typer.Option(True, "--units", help="List discovered backup units"),
    snapshots: bool = typer.Option(False, "--snapshots", help="List repository snapshots"),
):
    """List backup units or repository snapshots."""
    cfg = ensure_config(ctx)
    
    if not (units or snapshots):
        units = True

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
        typer.echo("\nListing snapshots…")
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
                    typer.echo(f"- {sid} | unit={unit} | {ts}")
        except Exception as e:
            typer.echo(f"Unable to list snapshots: {e}")
            raise typer.Exit(code=1)


@app.command("backup")
def cmd_backup(
    ctx: typer.Context,
    unit: List[str] = typer.Option(None, "--unit", "-u", help="Backup only these units"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate backup"),
    update_recovery_bundle: Optional[bool] = typer.Option(
        None,
        "--update-recovery/--no-update-recovery",
        help="Override config: update disaster recovery bundle",
    ),
):
    """Run a cold backup for selected units (or all)."""
    # Ensure prerequisites
    ensure_dependencies()
    cfg = ensure_config(ctx)
    repo = ensure_repository(ctx)
    
    try:
        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()
        selected = _filter_units(units, unit)
        
        if not selected:
            typer.echo("Nothing to back up (no units found).")
            return

        if dry_run:
            report = DryRunReport(cfg)
            report.generate(selected, update_recovery_bundle)
            return

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
                typer.echo(f"✗ {u.name} failed in {int(meta.duration_seconds)}s")
                for err in meta.errors or [meta.error_message]:
                    if err:
                        typer.echo(f"   - {err}")

        if not overall_ok:
            raise typer.Exit(code=1)

    except Exception as e:
        typer.echo(f"Backup failed: {e}")
        raise typer.Exit(code=1)


@app.command("restore")
def cmd_restore(ctx: typer.Context):
    """Launch the interactive restore wizard."""
    cfg = ensure_config(ctx)
    repo = ensure_repository(ctx)
    
    try:
        rm = RestoreManager(cfg)
        rm.interactive_restore()
    except Exception as e:
        typer.echo(f"Restore failed: {e}")
        raise typer.Exit(code=1)


# -------------------------
# Service Management
# -------------------------

@app.command("daemon")
def cmd_daemon(
    interval_minutes: Optional[int] = typer.Option(
        None,
        "--interval-minutes",
        help="Run backup every N minutes (prefer systemd timer)",
    ),
    backup_cmd: str = typer.Option(
        "/usr/bin/env kopi-docka backup",
        "--backup-cmd",
        help="Command to start a backup run",
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Log level for service"
    ),
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


@app.command("write-units")
def cmd_write_units(
    output_dir: Path = typer.Option(
        Path("/etc/systemd/system"),
        "--output-dir",
        help="Where to write systemd unit files",
    )
):
    """Write example systemd service and timer units."""
    try:
        write_systemd_units(output_dir)
        typer.echo(f"✓ Unit files written to: {output_dir}")
        typer.echo("Enable with: sudo systemctl enable --now kopi-docka.timer")
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
        typer.echo("\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()