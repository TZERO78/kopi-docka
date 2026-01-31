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
from rich.console import Console
from rich.panel import Panel

from ..helpers import Config, get_logger
from ..helpers.constants import (
    BACKUP_SCOPE_MINIMAL,
    BACKUP_SCOPE_STANDARD,
    BACKUP_SCOPE_FULL,
    BACKUP_SCOPES,
)
from ..helpers.ui_utils import (
    print_success,
    print_error,
    print_error_panel,
)
from ..cores import (
    KopiaRepository,
    DockerDiscovery,
    BackupManager,
    RestoreManager,
    DryRunReport,
)

logger = get_logger(__name__)
console = Console()


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


def ensure_config(ctx: typer.Context) -> Config:
    """Ensure config exists or exit."""
    cfg = get_config(ctx)
    if not cfg:
        print_error_panel(
            "No configuration found\n\n"
            "[dim]Run:[/dim] [cyan]kopi-docka advanced config new[/cyan]"
        )
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
        print_error_panel("Repository not available")
        raise typer.Exit(code=1)

    try:
        if repo.is_connected():
            return repo
    except Exception:
        pass

    console.print("[cyan]Connecting to Kopia repository...[/cyan]")
    try:
        repo.connect()
    except Exception as e:
        print_error(f"Connect failed: {e}")
        raise typer.Exit(code=1)

    if not repo.is_connected():
        print_error("Still not connected after connect().")
        raise typer.Exit(code=1)

    return repo


def _override_config(ctx: typer.Context, config_path: Optional[Path]):
    """Override config in context when command-level --config is used."""
    if not config_path:
        return
    try:
        cfg = Config(config_path)
        ctx.obj["config"] = cfg
        ctx.obj["config_path"] = config_path
    except Exception as e:
        print_error_panel(f"Failed to load config: {e}")
        raise typer.Exit(code=1)


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
    config_path: Optional[Path] = None,
):
    """List backup units or repository snapshots."""
    _override_config(ctx, config_path)
    cfg = ensure_config(ctx)

    if not (units or snapshots):
        units = True

    if units:
        console.print("[cyan]Discovering Docker backup units...[/cyan]")
        try:
            discovery = DockerDiscovery()
            found = discovery.discover_backup_units()
            if not found:
                console.print("[dim]No units found.[/dim]")
            else:
                for u in found:
                    console.print(
                        f"  [cyan]•[/cyan] {u.name} [dim]({u.type})[/dim]: "
                        f"{len(u.containers)} containers, {len(u.volumes)} volumes"
                    )
        except Exception as e:
            print_error(f"Discovery failed: {e}")
            raise typer.Exit(code=1)

    if snapshots:
        console.print("\n[cyan]Listing snapshots...[/cyan]")
        try:
            repo = KopiaRepository(cfg)
            snaps = repo.list_snapshots()
            if not snaps:
                console.print("[dim]No snapshots found.[/dim]")
            else:
                for s in snaps:
                    unit = s.get("tags", {}).get("unit", "-")
                    ts = s.get("timestamp", "-")
                    sid = s.get("id", "")
                    console.print(f"  [cyan]•[/cyan] {sid} | unit={unit} | {ts}")
        except Exception as e:
            print_error(f"Unable to list snapshots: {e}")
            raise typer.Exit(code=1)


def cmd_backup(
    ctx: typer.Context,
    unit: Optional[List[str]] = None,
    dry_run: bool = False,
    update_recovery_bundle: Optional[bool] = None,
    scope: str = BACKUP_SCOPE_STANDARD,
    config_path: Optional[Path] = None,
):
    """Run a cold backup for selected units (or all)."""
    _override_config(ctx, config_path)

    # ═══════════════════════════════════════════════════════════════════════════
    # GLOBAL LOCK: Prevent parallel backup execution (#61)
    # ═══════════════════════════════════════════════════════════════════════════
    from kopi_docka.helpers.process_lock import ProcessLock
    
    lock = ProcessLock()
    if not lock.acquire():
        holder_pid = lock.get_holder_pid()
        console.print(
            f"[yellow]⚠ Backup already running (PID: {holder_pid}), skipping.[/yellow]"
        )
        logger.warning(f"Backup skipped - lock held by PID {holder_pid}")
        # Exit 0 = not an error, just skipped
        raise typer.Exit(code=0)
    
    try:
        _run_backup(ctx, unit, dry_run, update_recovery_bundle, scope, config_path)
    finally:
        lock.release()


def _run_backup(
    ctx: typer.Context,
    unit: Optional[List[str]] = None,
    dry_run: bool = False,
    update_recovery_bundle: Optional[bool] = None,
    scope: str = BACKUP_SCOPE_STANDARD,
    config_path: Optional[Path] = None,
):
    """Internal backup implementation (called with lock held)."""
    cfg = ensure_config(ctx)

    # HARD GATE: Check required dependencies (docker + kopia)
    from kopi_docka.cores.dependency_manager import DependencyManager
    dep_manager = DependencyManager()
    dep_manager.check_hard_gate()

    repo = ensure_repository(ctx)

    # Validate scope
    if scope not in BACKUP_SCOPES:
        print_error_panel(
            f"Invalid scope: {scope}\n\n"
            f"[dim]Valid scopes:[/dim] {', '.join(BACKUP_SCOPES.keys())}"
        )
        raise typer.Exit(code=1)

    # Display scope information
    scope_info = BACKUP_SCOPES[scope]
    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]Backup Scope: {scope_info['name']}[/bold cyan]\n\n"
            f"{scope_info['description']}\n\n"
            f"[dim]Includes:[/dim] {', '.join(scope_info['includes'])}",
            border_style="cyan",
        )
    )
    console.print()

    try:
        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()
        selected = _filter_units(units, unit)

        if not selected:
            console.print("[dim]Nothing to back up (no units found).[/dim]")
            return

        if dry_run:
            report = DryRunReport(cfg)
            report.generate(selected, update_recovery_bundle)
            return

        bm = BackupManager(cfg)
        overall_ok = True

        for u in selected:
            console.print(
                f"[bold cyan]==>[/bold cyan] Backing up unit: [bold]{u.name}[/bold] ({scope})"
            )
            meta = bm.backup_unit(
                u, backup_scope=scope, update_recovery_bundle=update_recovery_bundle
            )
            if meta.success:
                print_success(f"{u.name} completed in {int(meta.duration_seconds)}s")
                volumes_backed_up = getattr(meta, "volumes_backed_up", 0)
                console.print(f"   [dim]Volumes:[/dim] {volumes_backed_up}")

                try:
                    networks_backed_up = int(getattr(meta, "networks_backed_up", 0) or 0)
                except Exception:
                    networks_backed_up = 0

                if networks_backed_up > 0:
                    console.print(f"   [dim]Networks:[/dim] {networks_backed_up}")
                if meta.kopia_snapshot_ids:
                    console.print(f"   [dim]Snapshots:[/dim] {len(meta.kopia_snapshot_ids)}")
            else:
                overall_ok = False
                print_error(f"{u.name} failed in {int(meta.duration_seconds)}s")
                for err in meta.errors or [meta.error_message]:
                    if err:
                        console.print(f"   [red]- {err}[/red]")

        if not overall_ok:
            raise typer.Exit(code=1)

    except Exception as e:
        print_error_panel(f"Backup failed: {e}")
        raise typer.Exit(code=1)


def cmd_restore(
    ctx: typer.Context,
    yes: bool = False,
    advanced: bool = False,
    force_recreate_networks: bool = False,
    no_recreate_networks: bool = False,
    config_path: Optional[Path] = None,
):
    """Launch the interactive restore wizard.

    Args:
        ctx: Typer context
        yes: Non-interactive mode
        advanced: Enable cross-machine restore (show all machines in repository)
        force_recreate_networks: Force recreation of existing networks (non-interactive)
        no_recreate_networks: Never recreate existing networks
    """
    # HARD GATE: Check required dependencies (docker + kopia)
    from kopi_docka.cores.dependency_manager import DependencyManager
    dep_manager = DependencyManager()
    dep_manager.check_hard_gate()

    if force_recreate_networks and no_recreate_networks:
        raise typer.BadParameter(
            "Cannot use --force-recreate-networks and --no-recreate-networks together"
        )

    _override_config(ctx, config_path)
    cfg = ensure_config(ctx)
    repo = ensure_repository(ctx)

    try:
        rm = RestoreManager(
            cfg,
            non_interactive=yes,
            force_recreate_networks=force_recreate_networks,
            skip_network_recreation=no_recreate_networks,
        )
        if advanced:
            rm.advanced_interactive_restore()
        else:
            rm.interactive_restore()
    except Exception as e:
        print_error_panel(f"Restore failed: {e}")
        raise typer.Exit(code=1)


def cmd_show_docker_config(
    ctx: typer.Context,
    snapshot_id: str,
    config_path: Optional[Path] = None,
):
    """Extract and show docker_config snapshot for manual restore.

    This command extracts Docker daemon configuration from a FULL scope backup
    and provides step-by-step instructions for manual restore.

    IMPORTANT: Docker daemon configuration is NOT automatically restored for safety.
    You must manually review and apply configuration changes.

    Args:
        ctx: Typer context
        snapshot_id: Snapshot ID to extract (docker_config type)
        config_path: Optional config file path
    """
    _override_config(ctx, config_path)
    cfg = ensure_config(ctx)
    repo = ensure_repository(ctx)

    try:
        rm = RestoreManager(cfg)
        success = rm.show_docker_config(snapshot_id)

        if not success:
            raise typer.Exit(code=1)
    except Exception as e:
        print_error_panel(f"Docker config extraction failed: {e}")
        raise typer.Exit(code=1)


# -------------------------
# Registration
# -------------------------


def register(app: typer.Typer):
    """Register backup and restore commands (top-level).

    Note: The 'list' command has been moved to 'admin snapshot list'.
    """

    @app.command("list")
    def _list_cmd(
        ctx: typer.Context,
        units: bool = typer.Option(
            True,
            "--units/--no-units",
            help="Show discovered backup units",
        ),
        snapshots: bool = typer.Option(
            False,
            "--snapshots",
            help="Show repository snapshots",
        ),
        config: Optional[Path] = typer.Option(
            None,
            "--config",
            help="Path to configuration file",
        ),
    ):
        """List backup units or snapshots (alias of 'admin snapshot list')."""
        cmd_list(ctx, units=units, snapshots=snapshots, config_path=config)

    @app.command("backup")
    def _backup_cmd(
        ctx: typer.Context,
        unit: Optional[List[str]] = typer.Option(None, "--unit", help="Backup only these units"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Simulate backup"),
        update_recovery_bundle: Optional[bool] = typer.Option(
            None, "--update-recovery/--no-update-recovery"
        ),
        config: Optional[Path] = typer.Option(
            None,
            "--config",
            help="Path to configuration file",
        ),
        scope: str = typer.Option(
            BACKUP_SCOPE_STANDARD,
            "--scope",
            help=f"Backup scope: {BACKUP_SCOPE_MINIMAL} (volumes only), {BACKUP_SCOPE_STANDARD} (volumes+recipes+networks), {BACKUP_SCOPE_FULL} (everything)",
        ),
    ):
        """Run a cold backup for selected units (or all)."""
        cmd_backup(ctx, unit, dry_run, update_recovery_bundle, scope, config_path=config)

    @app.command("restore")
    def _restore_cmd(
        ctx: typer.Context,
        yes: bool = typer.Option(
            False,
            "--yes",
            "-y",
            help="Non-interactive mode: auto-confirm all prompts (for CI/CD and scripts)",
        ),
        advanced: bool = typer.Option(
            False,
            "--advanced",
            help="Cross-machine restore: show backups from ALL machines in repository",
        ),
        force_recreate_networks: bool = typer.Option(
            False,
            "--force-recreate-networks",
            help=(
                "Always recreate existing networks (stop/restart attached containers automatically)"
            ),
        ),
        no_recreate_networks: bool = typer.Option(
            False,
            "--no-recreate-networks",
            help="Never recreate existing networks during restore",
        ),
        config: Optional[Path] = typer.Option(
            None,
            "--config",
            help="Path to configuration file",
        ),
    ):
        """Launch the interactive restore wizard.

        Use --advanced for cross-machine restore (e.g., restoring from a crashed server).
        """
        cmd_restore(
            ctx,
            yes=yes,
            advanced=advanced,
            force_recreate_networks=force_recreate_networks,
            no_recreate_networks=no_recreate_networks,
            config_path=config,
        )

    @app.command("show-docker-config")
    def _show_docker_config_cmd(
        ctx: typer.Context,
        snapshot_id: str = typer.Argument(
            ...,
            help="Snapshot ID of docker_config type to extract",
        ),
        config: Optional[Path] = typer.Option(
            None,
            "--config",
            help="Path to configuration file",
        ),
    ):
        """Extract Docker daemon config from FULL scope backup (manual restore).

        This command extracts docker_config snapshots to a temp directory and shows
        step-by-step instructions for manual restore.

        SAFETY: Docker daemon configuration is NOT automatically restored to prevent
        accidental production breakage. You must manually review and apply changes.

        Example:
            kopi-docka show-docker-config k1a2b3c4d5e6f7g8
        """
        cmd_show_docker_config(ctx, snapshot_id=snapshot_id, config_path=config)
