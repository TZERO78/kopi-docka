"""Backup and restore commands."""

from pathlib import Path
from typing import Optional, List

import typer

from ..helpers import Config, get_logger
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
        typer.echo("Run: kopi-docka new-config")
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
):
    """Run a cold backup for selected units (or all)."""
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
    """Register all backup commands."""
    
    app.command("list")(
        lambda ctx,
               units=typer.Option(True, "--units", help="List discovered backup units"),
               snapshots=typer.Option(False, "--snapshots", help="List repository snapshots"):
            cmd_list(ctx, units, snapshots)
    )
    
    app.command("backup")(
        lambda ctx,
               unit=typer.Option(None, "--unit", "-u", help="Backup only these units"),
               dry_run=typer.Option(False, "--dry-run", help="Simulate backup"),
               update_recovery_bundle=typer.Option(None, "--update-recovery/--no-update-recovery"):
            cmd_backup(ctx, unit, dry_run, update_recovery_bundle)
    )
    
    app.command("restore")(cmd_restore)