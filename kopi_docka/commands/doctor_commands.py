################################################################################
# KOPI-DOCKA
#
# @file:        doctor_commands.py
# @module:      kopi_docka.commands
# @description: Doctor command - comprehensive system health check
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.4.1
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Doctor command - comprehensive system health check.

This command merges functionality from:
- check (dependency verification)
- status (backend status)
- repo-status (repository status)

Provides a single command to diagnose the entire Kopi-Docka setup.
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ..helpers import Config, get_logger
from ..cores import KopiaRepository, DependencyManager
from ..backends.local import LocalBackend
from ..backends.s3 import S3Backend
from ..backends.b2 import B2Backend
from ..backends.azure import AzureBackend
from ..backends.gcs import GCSBackend
from ..backends.sftp import SFTPBackend
from ..backends.tailscale import TailscaleBackend
from ..backends.rclone import RcloneBackend

logger = get_logger(__name__)
console = Console()

# Backend registry
BACKEND_MODULES = {
    'filesystem': LocalBackend,
    's3': S3Backend,
    'b2': B2Backend,
    'azure': AzureBackend,
    'gcs': GCSBackend,
    'sftp': SFTPBackend,
    'tailscale': TailscaleBackend,
    'rclone': RcloneBackend,
}


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


# -------------------------
# Commands
# -------------------------

def cmd_doctor(ctx: typer.Context, verbose: bool = False):
    """
    Run comprehensive system health check.

    Checks:
    1. System dependencies (Kopia, Docker)
    2. Configuration status
    3. Backend connectivity
    4. Repository status
    """
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Kopi-Docka System Health Check[/bold cyan]",
        border_style="cyan"
    ))
    console.print()

    issues = []
    warnings = []

    # ═══════════════════════════════════════════
    # Section 1: Dependencies
    # ═══════════════════════════════════════════
    console.print("[bold]1. System Dependencies[/bold]")
    console.print("-" * 40)

    deps = DependencyManager()
    dep_status = deps.check_all()

    deps_table = Table(box=box.SIMPLE, show_header=False)
    deps_table.add_column("Component", style="cyan", width=20)
    deps_table.add_column("Status", width=15)
    deps_table.add_column("Details", style="dim")

    # Kopia
    if dep_status.get('kopia', False):
        deps_table.add_row("Kopia", "[green]Installed[/green]", "")
    else:
        deps_table.add_row("Kopia", "[red]Missing[/red]", "Run: kopi-docka admin system install-deps")
        issues.append("Kopia is not installed")

    # Docker
    if dep_status.get('docker', False):
        deps_table.add_row("Docker", "[green]Running[/green]", "")
    else:
        deps_table.add_row("Docker", "[red]Not Running[/red]", "Start Docker daemon")
        issues.append("Docker is not running")

    console.print(deps_table)
    console.print()

    # ═══════════════════════════════════════════
    # Section 2: Configuration
    # ═══════════════════════════════════════════
    console.print("[bold]2. Configuration[/bold]")
    console.print("-" * 40)

    cfg = get_config(ctx)

    config_table = Table(box=box.SIMPLE, show_header=False)
    config_table.add_column("Property", style="cyan", width=20)
    config_table.add_column("Status", width=15)
    config_table.add_column("Details", style="dim")

    if cfg:
        config_table.add_row("Config File", "[green]Found[/green]", str(cfg.config_file))

        # Check password
        try:
            password = cfg.get_password()
            if password and password not in ('kopi-docka', 'CHANGE_ME_TO_A_SECURE_PASSWORD', ''):
                config_table.add_row("Password", "[green]Configured[/green]", "")
            else:
                config_table.add_row("Password", "[yellow]Default/Missing[/yellow]", "Run: kopi-docka admin repo init")
                warnings.append("Password is default or missing")
        except Exception:
            config_table.add_row("Password", "[red]Error[/red]", "Could not read password")
            issues.append("Could not read password from config")

        # Check kopia_params
        kopia_params = cfg.get('kopia', 'kopia_params', fallback='')
        if kopia_params:
            config_table.add_row("Kopia Params", "[green]Configured[/green]", kopia_params[:50] + "..." if len(kopia_params) > 50 else kopia_params)
        else:
            config_table.add_row("Kopia Params", "[red]Missing[/red]", "Run: kopi-docka admin config new")
            issues.append("Kopia parameters not configured")
    else:
        config_table.add_row("Config File", "[red]Not Found[/red]", "Run: kopi-docka admin config new")
        issues.append("No configuration file found")

    console.print(config_table)
    console.print()

    # ═══════════════════════════════════════════
    # Section 3: Backend Status
    # ═══════════════════════════════════════════
    if cfg:
        console.print("[bold]3. Backend Status[/bold]")
        console.print("-" * 40)

        backend_type = cfg.get('backend', 'type', fallback='filesystem')

        backend_table = Table(box=box.SIMPLE, show_header=False)
        backend_table.add_column("Property", style="cyan", width=20)
        backend_table.add_column("Status", width=15)
        backend_table.add_column("Details", style="dim")

        backend_table.add_row("Backend Type", "", backend_type)

        backend_class = BACKEND_MODULES.get(backend_type)
        if backend_class:
            try:
                # Load backend config
                backend_config = {}
                kopia_params = cfg.get('kopia', 'kopia_params', fallback='')
                if kopia_params:
                    backend_config['kopia_params'] = kopia_params

                backend = backend_class(backend_config)
                status = backend.get_status()

                if status.get('available'):
                    backend_table.add_row("Connection", "[green]Available[/green]", "")
                else:
                    backend_table.add_row("Connection", "[red]Not Available[/red]", "Check backend configuration")
                    issues.append(f"Backend {backend_type} is not available")

                # Show backend-specific details
                details = status.get('details', {})
                if backend_type == 'filesystem':
                    if details.get('path'):
                        backend_table.add_row("Path", "", details['path'])
                    if details.get('disk_free_gb') is not None:
                        backend_table.add_row("Free Space", "", f"{details['disk_free_gb']:.1f} GB")
                elif backend_type == 'tailscale':
                    if status.get('hostname'):
                        backend_table.add_row("Hostname", "", status['hostname'])
                    if status.get('online'):
                        backend_table.add_row("Peer Status", "[green]Online[/green]", "")
                    else:
                        backend_table.add_row("Peer Status", "[red]Offline[/red]", "")
                        warnings.append("Tailscale peer is offline")

            except Exception as e:
                backend_table.add_row("Status", "[red]Error[/red]", str(e)[:50])
                issues.append(f"Backend check failed: {e}")
        else:
            backend_table.add_row("Status", "[yellow]Unknown Type[/yellow]", f"Backend '{backend_type}' not recognized")
            warnings.append(f"Unknown backend type: {backend_type}")

        console.print(backend_table)
        console.print()

    # ═══════════════════════════════════════════
    # Section 4: Repository Status
    # ═══════════════════════════════════════════
    if cfg:
        console.print("[bold]4. Repository Status[/bold]")
        console.print("-" * 40)

        repo_table = Table(box=box.SIMPLE, show_header=False)
        repo_table.add_column("Property", style="cyan", width=20)
        repo_table.add_column("Status", width=15)
        repo_table.add_column("Details", style="dim")

        try:
            repo = KopiaRepository(cfg)

            if repo.is_connected():
                repo_table.add_row("Connection", "[green]Connected[/green]", "")
                repo_table.add_row("Profile", "", repo.profile_name)

                # Get snapshot count
                try:
                    snapshots = repo.list_snapshots()
                    repo_table.add_row("Snapshots", "", str(len(snapshots)))
                except Exception:
                    repo_table.add_row("Snapshots", "[yellow]Unknown[/yellow]", "")

                # Get backup units count
                try:
                    units = repo.list_backup_units()
                    repo_table.add_row("Backup Units", "", str(len(units)))
                except Exception:
                    repo_table.add_row("Backup Units", "[yellow]Unknown[/yellow]", "")
            else:
                repo_table.add_row("Connection", "[yellow]Not Connected[/yellow]", "Run: kopi-docka admin repo init")
                warnings.append("Repository not connected")

        except Exception as e:
            repo_table.add_row("Status", "[red]Error[/red]", str(e)[:50])
            issues.append(f"Repository check failed: {e}")

        console.print(repo_table)
        console.print()

    # ═══════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════
    console.print("-" * 40)

    if not issues and not warnings:
        console.print(Panel.fit(
            "[green]All systems operational![/green]\n\n"
            "Kopi-Docka is ready to backup your Docker containers.",
            title="[bold green]Health Check Passed[/bold green]",
            border_style="green"
        ))
    elif issues:
        issue_list = "\n".join(f"  - {i}" for i in issues)
        warning_list = "\n".join(f"  - {w}" for w in warnings) if warnings else ""

        message = f"[red]Issues found ({len(issues)}):[/red]\n{issue_list}"
        if warnings:
            message += f"\n\n[yellow]Warnings ({len(warnings)}):[/yellow]\n{warning_list}"

        console.print(Panel.fit(
            message,
            title="[bold red]Health Check Failed[/bold red]",
            border_style="red"
        ))
    else:
        warning_list = "\n".join(f"  - {w}" for w in warnings)
        console.print(Panel.fit(
            f"[yellow]Warnings ({len(warnings)}):[/yellow]\n{warning_list}\n\n"
            "System is functional but may need attention.",
            title="[bold yellow]Health Check Warnings[/bold yellow]",
            border_style="yellow"
        ))

    console.print()

    # Verbose output
    if verbose:
        console.print("[bold]Detailed Dependency Status:[/bold]")
        deps.print_status(verbose=True)


# -------------------------
# Registration
# -------------------------

def register(app: typer.Typer):
    """Register doctor command."""

    @app.command("doctor")
    def _doctor_cmd(
        ctx: typer.Context,
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    ):
        """Run comprehensive system health check."""
        cmd_doctor(ctx, verbose)
