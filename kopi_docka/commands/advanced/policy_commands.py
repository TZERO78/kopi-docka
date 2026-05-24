################################################################################
# KOPI-DOCKA
#
# @file:        policy_commands.py
# @module:      kopi_docka.commands.advanced
# @description: Policy management commands (advanced policy subgroup)
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     7.1.2
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025-2026 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Policy management commands under 'advanced policy'.

Commands:
- advanced policy prune  - Delete legacy per-path Kopia retention policies
"""

import getpass
import socket
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from ...helpers import Config, get_logger
from ...helpers.constants import STAGING_BASE_DIR
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


# Prefixes kopi-docka has ever managed per-path policies under. Defense in
# depth: even with host+user matching, we'd rather skip a leftover policy
# than touch a custom one a user set themselves.
_OWNED_PREFIXES = (
    str(STAGING_BASE_DIR),         # /var/cache/kopi-docka/staging/...
    "/var/lib/docker/volumes/",    # direct-mode volume mountpoints
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
    """Delete legacy per-path Kopia retention policies.

    Plan 0028 made all per-path policies obsolete (global retention covers
    every snapshot via Kopia's inheritance tree). This command removes the
    leftovers from older kopi-docka versions. Whether a policy still has a
    matching snapshot is irrelevant — under Plan 0028 per-path policies
    are never needed.

    Cross-host restore safety (Plan 0024): we only touch policies on this
    host's hostname / username and under kopi-docka-managed path prefixes.
    A foreign host's policies on a shared repo are never deleted.
    """
    cfg = _ensure_config(ctx)

    repo = KopiaRepository(cfg)
    if not repo.is_connected():
        print_error_panel("Not connected to Kopia repository.")
        raise typer.Exit(code=1)

    policy_mgr = KopiaPolicyManager(repo)

    console.print("[cyan]Fetching policies…[/cyan]")

    try:
        policies = policy_mgr.list_policies()
    except Exception as e:
        print_error_panel(f"Failed to fetch policies from Kopia: {e}")
        raise typer.Exit(code=1)

    local_host = socket.gethostname()
    local_user = getpass.getuser()

    # Collect every per-path entry owned by this host/user under a
    # kopi-docka-managed prefix. Foreign or unowned-prefix entries are
    # listed separately so users can see them but stay untouched.
    legacy_entries: dict[str, dict] = {}
    skipped: list[tuple[str, str, str]] = []  # (path, host, reason)
    for pol in policies:
        target = pol.get("target", {})
        path = target.get("path", "")
        host = target.get("host", "")
        user = target.get("userName", "")
        if not path or path == "(global)":
            continue
        if host != local_host or user != local_user:
            skipped.append((path, host, f"foreign {user}@{host}"))
            continue
        if not path.startswith(_OWNED_PREFIXES):
            skipped.append((path, host, "unknown prefix"))
            continue
        legacy_entries[path] = target

    legacy_paths = sorted(legacy_entries)

    if not legacy_paths and not skipped:
        console.print(
            "[green]✓ No per-path policies found. "
            "Repository is already global-only.[/green]"
        )
        return

    if legacy_paths:
        t = Table(box=box.SIMPLE, show_header=True)
        t.add_column("#", style="dim", width=4)
        t.add_column("Legacy Policy Path", style="yellow")
        t.add_column("Host", style="dim")
        for i, path in enumerate(legacy_paths, 1):
            t.add_row(str(i), path, legacy_entries[path].get("host", ""))
        console.print(t)
        console.print(
            f"[bold]{len(legacy_paths)} legacy "
            f"{'policy' if len(legacy_paths) == 1 else 'policies'}[/bold] "
            "from older kopi-docka versions (Plan 0028 makes them obsolete)."
        )

    if skipped:
        st = Table(box=box.SIMPLE, show_header=True, title="Skipped (safety)")
        st.add_column("#", style="dim", width=4)
        st.add_column("Path", style="dim")
        st.add_column("Host", style="dim")
        st.add_column("Reason", style="dim")
        for i, (path, host, reason) in enumerate(skipped, 1):
            st.add_row(str(i), path, host, reason)
        console.print(st)
        console.print(
            f"[dim]{len(skipped)} policy/policies skipped — cross-host or "
            "outside kopi-docka prefixes.[/dim]"
        )

    if not legacy_paths:
        return

    if dry_run:
        console.print("\n[dim]Dry-run mode — no changes made.[/dim]")
        return

    if not force:
        confirm = typer.confirm(
            f"\nDelete {len(legacy_paths)} legacy per-path policies?",
            default=False,
        )
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(code=0)

    entries = [legacy_entries[p] for p in legacy_paths]
    console.print(
        f"[cyan]Deleting {len(entries)} policies in one batch call…[/cyan]"
    )

    ok = policy_mgr.delete_policies_batch(entries)

    console.print()
    if ok:
        console.print(
            f"[green]Done.[/green] {len(entries)} legacy "
            f"{'policy' if len(entries) == 1 else 'policies'} removed."
        )
        console.print(
            "[dim]Run [cyan]kopi-docka doctor[/cyan] to confirm clean state.[/dim]"
        )
        return

    console.print("[yellow]Batch delete failed.[/yellow] Retrying individually…")
    deleted = 0
    failed = 0
    for path in legacy_paths:
        target = legacy_entries[path]
        single_ok = policy_mgr.delete_policy(
            host=target.get("host", ""),
            username=target.get("userName", ""),
            path=path,
        )
        if single_ok:
            console.print(f"  [green]✓[/green] Deleted: {path}")
            deleted += 1
        else:
            console.print(f"  [red]✗[/red] Failed:  {path}")
            failed += 1
    console.print()
    if failed == 0:
        console.print(f"[green]Done.[/green] {deleted} policies removed.")
        console.print(
            "[dim]Run [cyan]kopi-docka doctor[/cyan] to confirm clean state.[/dim]"
        )
        return

    console.print(
        f"[yellow]Finished with errors.[/yellow] {deleted} deleted, {failed} failed."
    )
    raise typer.Exit(code=1)


def register(app: typer.Typer):
    """Register policy commands under 'advanced policy'."""

    @policy_app.command("prune")
    def _prune_cmd(
        ctx: typer.Context,
        dry_run: bool = typer.Option(
            False, "--dry-run",
            help="Show legacy per-path policies without deleting them",
        ),
        force: bool = typer.Option(
            False, "--force", "-f", help="Skip confirmation prompt"
        ),
    ):
        """Delete legacy per-path Kopia retention policies (Plan 0028 cleanup)."""
        cmd_prune(ctx, dry_run=dry_run, force=force)

    app.add_typer(policy_app, name="policy", help="Kopia retention policy management")
