################################################################################
# KOPI-DOCKA
#
# @file:        backup_commands.py
# @module:      kopi_docka.commands
# @description: Backup and restore commands
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Backup and restore commands."""

from pathlib import Path
from typing import Optional, List

import typer

from ..helpers import Config, get_logger
from ..helpers.constants import (
    BACKUP_SCOPE_MINIMAL,
    BACKUP_SCOPE_STANDARD,
    BACKUP_SCOPE_FULL,
    BACKUP_SCOPES,
)
from ..cores import (
    KopiaRepository,
    DockerDiscovery,
    BackupManager,
    RestoreManager,
    DryRunReport,
)

logger = get_logger(__name__)


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


def ensure_config(ctx: typer.Context) -> Config:
    """Ensure config exists or exit."""
    cfg = get_config(ctx)
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka admin config new")
        raise typer.Exit(code=1)
    return cfg


def get_repository(ctx: typer.Context) -> Optional[KopiaRepository]:
    """Get or create repository from context."""
    if "repository" not in ctx.obj:
        cfg = get_config(ctx)
        if cfg:
            ctx.obj["repository"] = KopiaRepository(cfg)
    return ctx.obj.get("repository")


def ensure_repository(ctx: typer.Context) -> KopiaRepository:
    """Ensure repository is connected."""
    repo = get_repository(ctx)
    if not repo:
        typer.echo("❌ Repository not available")
        raise typer.Exit(code=1)

    try:
        if repo.is_connected():
            return repo
    except Exception:
        pass

    typer.echo("↻ Connecting to Kopia repository…")
    try:
        repo.connect()
    except Exception as e:
        typer.echo(f"✗ Connect failed: {e}")
        raise typer.Exit(code=1)

    if not repo.is_connected():
        typer.echo("✗ Still not connected after connect().")
        raise typer.Exit(code=1)

    return repo


def _filter_units(all_units, names: Optional[List[str]]):
    """Filter backup units by name."""
    if not names:
        return all_units
    wanted = set(names)
    return [u for u in all_units if u.name in wanted]


# -------------------------
# Commands
# -------------------------

def cmd_list(
    ctx: typer.Context,
    units: bool = True,
    snapshots: bool = False,
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


def cmd_backup(
    ctx: typer.Context,
    unit: Optional[List[str]] = None,
    dry_run: bool = False,
    update_recovery_bundle: Optional[bool] = None,
    scope: str = BACKUP_SCOPE_STANDARD,
):
    """Run a cold backup for selected units (or all)."""
    cfg = ensure_config(ctx)
    repo = ensure_repository(ctx)

    # Validate scope
    if scope not in BACKUP_SCOPES:
        typer.echo(f"❌ Invalid scope: {scope}")
        typer.echo(f"   Valid scopes: {', '.join(BACKUP_SCOPES.keys())}")
        raise typer.Exit(code=1)

    # Display scope information
    scope_info = BACKUP_SCOPES[scope]
    typer.echo(f"\n📦 Backup Scope: {scope_info['name']}")
    typer.echo(f"   {scope_info['description']}")
    typer.echo(f"   Includes: {', '.join(scope_info['includes'])}\n")

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
            typer.echo(f"==> Backing up unit: {u.name} ({scope})")
            meta = bm.backup_unit(
                u,
                backup_scope=scope,
                update_recovery_bundle=update_recovery_bundle
            )
            if meta.success:
                typer.echo(f"✓ {u.name} completed in {int(meta.duration_seconds)}s")
                typer.echo(f"   Volumes: {meta.volumes_backed_up}")
                if meta.networks_backed_up > 0:
                    typer.echo(f"   Networks: {meta.networks_backed_up}")
                if meta.kopia_snapshot_ids:
                    typer.echo(f"   Snapshots: {len(meta.kopia_snapshot_ids)}")
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
# Registration
# -------------------------

def register(app: typer.Typer):
    """Register backup and restore commands (top-level).

    Note: The 'list' command has been moved to 'admin snapshot list'.
    """

    @app.command("backup")
    def _backup_cmd(
        ctx: typer.Context,
        unit: Optional[List[str]] = typer.Option(None, "--unit", help="Backup only these units"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Simulate backup"),
        update_recovery_bundle: Optional[bool] = typer.Option(
            None, "--update-recovery/--no-update-recovery"
        ),
        scope: str = typer.Option(
            BACKUP_SCOPE_STANDARD,
            "--scope",
            help=f"Backup scope: {BACKUP_SCOPE_MINIMAL} (volumes only), {BACKUP_SCOPE_STANDARD} (volumes+recipes+networks), {BACKUP_SCOPE_FULL} (everything)"
        ),
    ):
        """Run a cold backup for selected units (or all)."""
        cmd_backup(ctx, unit, dry_run, update_recovery_bundle, scope)

    @app.command("restore")
    def _restore_cmd(ctx: typer.Context):
        """Launch the interactive restore wizard."""
        cmd_restore(ctx)
