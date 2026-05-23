################################################################################
# KOPI-DOCKA
#
# @file:        policy_commands.py
# @module:      kopi_docka.commands.advanced
# @description: Policy management commands (admin policy subgroup)
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     7.1.2
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025-2026 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Policy management commands under 'admin policy'.

Commands:
- admin policy prune  - Delete orphaned Kopia retention policies
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from ...helpers import Config, get_logger
from ...helpers.ui_utils import print_error_panel
from ...cores import KopiaRepository
from ...cores.kopia_policy_manager import KopiaPolicyManager

logger = get_logger(__name__)
console = Console()

policy_app = typer.Typer(
    name="policy",
    help="Kopia retention policy management.",
    no_args_is_help=True,
)


def _ensure_config(ctx: typer.Context) -> Config:
    cfg: Optional[Config] = ctx.obj.get("config") if ctx.obj else None
    if not cfg:
        print_error_panel(
            "No configuration found\n\n"
            "[dim]Run:[/dim] [cyan]kopi-docka advanced config new[/cyan]"
        )
        raise typer.Exit(code=1)
    return cfg


def cmd_prune(ctx: typer.Context, dry_run: bool, force: bool) -> None:
    """Delete orphaned Kopia retention policies (no matching snapshot sources)."""
    cfg = _ensure_config(ctx)

    repo = KopiaRepository(cfg)
    if not repo.is_connected():
        print_error_panel("Not connected to Kopia repository.")
        raise typer.Exit(code=1)

    policy_mgr = KopiaPolicyManager(repo)

    console.print("[cyan]Fetching policies and snapshot sources…[/cyan]")

    try:
        policies = policy_mgr.list_policies()
        snapshots = repo.list_snapshots()
    except Exception as e:
        print_error_panel(f"Failed to fetch data from Kopia: {e}")
        raise typer.Exit(code=1)

    # Build sets of paths
    policy_entries: dict[str, dict] = {}  # path → target dict
    for pol in policies:
        target = pol.get("target", {})
        path = target.get("path", "")
        if path and path != "(global)":
            policy_entries[path] = target

    snapshot_paths: set[str] = set()
    for snap in snapshots:
        path = snap.get("source", {}).get("path", "")
        if path:
            snapshot_paths.add(path)

    orphaned_paths = sorted(set(policy_entries) - snapshot_paths)

    if not orphaned_paths:
        console.print("[green]✓ No orphaned policies found. Nothing to do.[/green]")
        return

    # Show what will be removed
    t = Table(box=box.SIMPLE, show_header=True)
    t.add_column("#", style="dim", width=4)
    t.add_column("Orphaned Policy Path", style="yellow")
    t.add_column("Host", style="dim")

    for i, path in enumerate(orphaned_paths, 1):
        target = policy_entries[path]
        host = target.get("host", "")
        t.add_row(str(i), path, host)

    console.print(t)
    console.print(
        f"[bold]{len(orphaned_paths)} orphaned {'policy' if len(orphaned_paths) == 1 else 'policies'}[/bold] "
        f"with no matching snapshots."
    )

    if dry_run:
        console.print("\n[dim]Dry-run mode — no changes made.[/dim]")
        return

    if not force:
        confirm = typer.confirm(
            f"\nDelete {len(orphaned_paths)} orphaned policies?", default=False
        )
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(code=0)

    deleted = 0
    failed = 0
    for path in orphaned_paths:
        target = policy_entries[path]
        host = target.get("host", "")
        username = target.get("userName", "")
        ok = policy_mgr.delete_policy(host=host, username=username, path=path)
        if ok:
            console.print(f"  [green]✓[/green] Deleted: {path}")
            deleted += 1
        else:
            console.print(f"  [red]✗[/red] Failed:  {path}")
            failed += 1

    console.print()
    if failed == 0:
        console.print(
            f"[green]Done.[/green] {deleted} orphaned "
            f"{'policy' if deleted == 1 else 'policies'} removed."
        )
        console.print(
            "[dim]Run [cyan]kopi-docka doctor[/cyan] to confirm clean alignment.[/dim]"
        )
    else:
        console.print(
            f"[yellow]Finished with errors.[/yellow] "
            f"{deleted} deleted, {failed} failed."
        )
        raise typer.Exit(code=1)


def register(app: typer.Typer):
    """Register policy commands under 'admin policy'."""

    @policy_app.command("prune")
    def _prune_cmd(
        ctx: typer.Context,
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Show orphaned policies without deleting them"
        ),
        force: bool = typer.Option(
            False, "--force", "-f", help="Skip confirmation prompt"
        ),
    ):
        """Delete orphaned Kopia retention policies (no matching snapshot sources)."""
        cmd_prune(ctx, dry_run=dry_run, force=force)

    app.add_typer(policy_app, name="policy", help="Kopia retention policy management")
