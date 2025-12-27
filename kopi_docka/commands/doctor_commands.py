################################################################################
# KOPI-DOCKA
#
# @file:        doctor_commands.py
# @module:      kopi_docka.commands
# @description: Doctor command - comprehensive system health check
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.5.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Doctor command - comprehensive system health check.

Checks:
1. System dependencies (Kopia, Docker)
2. Configuration status
3. Repository status (Kopia connection - the single source of truth)

Note: Repository connection status IS the definitive check. If Kopia can
connect to the repository, the underlying storage (filesystem, rclone, s3, etc.)
is automatically working. No separate backend checks needed.
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ..helpers import Config, get_logger, detect_repository_type
from ..cores import KopiaRepository, DependencyManager

logger = get_logger(__name__)
console = Console()


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


def _extract_storage_info(kopia_params: str, repo_type: str) -> dict:
    """
    Extract storage-specific info from kopia_params for display purposes only.

    This is purely for informational display - NOT a connectivity check.
    The actual connectivity is verified by Kopia repository status.

    Args:
        kopia_params: The kopia_params string
        repo_type: Detected repository type

    Returns:
        Dict with extracted info (remote_path, bucket, etc.)
    """
    import shlex

    info = {}

    if not kopia_params:
        return info

    try:
        parts = shlex.split(kopia_params)

        if repo_type == "filesystem":
            # Extract --path
            for i, part in enumerate(parts):
                if part == "--path" and i + 1 < len(parts):
                    info["path"] = parts[i + 1]
                elif part.startswith("--path="):
                    info["path"] = part.split("=", 1)[1]

        elif repo_type == "rclone":
            # Extract --remote-path
            for part in parts:
                if part.startswith("--remote-path="):
                    info["remote"] = part.split("=", 1)[1]

        elif repo_type in ("s3", "b2", "gcs"):
            # Extract --bucket
            for i, part in enumerate(parts):
                if part == "--bucket" and i + 1 < len(parts):
                    info["bucket"] = parts[i + 1]
                elif part.startswith("--bucket="):
                    info["bucket"] = part.split("=", 1)[1]

        elif repo_type == "azure":
            # Extract --container
            for i, part in enumerate(parts):
                if part == "--container" and i + 1 < len(parts):
                    info["container"] = parts[i + 1]
                elif part.startswith("--container="):
                    info["container"] = part.split("=", 1)[1]

        elif repo_type == "sftp":
            # Extract --path (contains user@host:path)
            for i, part in enumerate(parts):
                if part == "--path" and i + 1 < len(parts):
                    info["target"] = parts[i + 1]
                elif part.startswith("--path="):
                    info["target"] = part.split("=", 1)[1]

    except Exception:
        pass

    return info


# -------------------------
# Commands
# -------------------------


def cmd_doctor(ctx: typer.Context, verbose: bool = False):
    """
    Run comprehensive system health check.

    Checks:
    1. System dependencies (Kopia, Docker)
    2. Configuration status
    3. Repository status (connection is the single source of truth)
    """
    console.print()
    console.print(
        Panel.fit("[bold cyan]Kopi-Docka System Health Check[/bold cyan]", border_style="cyan")
    )
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
    if dep_status.get("kopia", False):
        deps_table.add_row("Kopia", "[green]Installed[/green]", "")
    else:
        deps_table.add_row(
            "Kopia", "[red]Missing[/red]", "Run: kopi-docka advanced system install-deps"
        )
        issues.append("Kopia is not installed")

    # Docker
    if dep_status.get("docker", False):
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

    kopia_params = ""

    if cfg:
        config_table.add_row("Config File", "[green]Found[/green]", str(cfg.config_file))

        # Check password
        try:
            password = cfg.get_password()
            if password and password not in ("kopi-docka", "CHANGE_ME_TO_A_SECURE_PASSWORD", ""):
                config_table.add_row("Password", "[green]Configured[/green]", "")
            else:
                config_table.add_row(
                    "Password",
                    "[yellow]Default/Missing[/yellow]",
                    "Run: kopi-docka advanced repo init",
                )
                warnings.append("Password is default or missing")
        except Exception:
            config_table.add_row("Password", "[red]Error[/red]", "Could not read password")
            issues.append("Could not read password from config")

        # Check kopia_params
        kopia_params = cfg.get("kopia", "kopia_params", fallback="")
        if kopia_params:
            config_table.add_row(
                "Kopia Params",
                "[green]Configured[/green]",
                kopia_params[:50] + "..." if len(kopia_params) > 50 else kopia_params,
            )
        else:
            config_table.add_row(
                "Kopia Params", "[red]Missing[/red]", "Run: kopi-docka advanced config new"
            )
            issues.append("Kopia parameters not configured")
    else:
        config_table.add_row(
            "Config File", "[red]Not Found[/red]", "Run: kopi-docka advanced config new"
        )
        issues.append("No configuration file found")

    console.print(config_table)
    console.print()

    # ═══════════════════════════════════════════
    # Section 3: Repository Status
    # (Kopia connection is the SINGLE SOURCE OF TRUTH)
    # ═══════════════════════════════════════════
    if cfg:
        console.print("[bold]3. Repository Status[/bold]")
        console.print("-" * 40)

        repo_table = Table(box=box.SIMPLE, show_header=False)
        repo_table.add_column("Property", style="cyan", width=20)
        repo_table.add_column("Status", width=15)
        repo_table.add_column("Details", style="dim")

        # Show repository type (from config parsing, no API call needed)
        repo_type = detect_repository_type(kopia_params)
        repo_table.add_row("Repository Type", "", repo_type)

        # Show storage-specific info (parsed from config, no API call)
        storage_info = _extract_storage_info(kopia_params, repo_type)
        if storage_info:
            for key, value in storage_info.items():
                display_key = key.replace("_", " ").title()
                repo_table.add_row(display_key, "", value)

        # THE ACTUAL CHECK: Kopia repository connection
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
                repo_table.add_row("Connection", "[yellow]Not Connected[/yellow]", "")
                warnings.append("Repository not connected")

                # Helpful message based on repo type
                if repo_type == "unknown":
                    repo_table.add_row("", "", "Run: kopi-docka advanced config new")
                else:
                    repo_table.add_row("", "", "Run: kopi-docka advanced repo init")

        except Exception as e:
            repo_table.add_row("Connection", "[red]Error[/red]", str(e)[:50])
            issues.append(f"Repository check failed: {e}")

        console.print(repo_table)
        console.print()

    # ═══════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════
    console.print("-" * 40)

    if not issues and not warnings:
        console.print(
            Panel.fit(
                "[green]All systems operational![/green]\n\n"
                "Kopi-Docka is ready to backup your Docker containers.",
                title="[bold green]Health Check Passed[/bold green]",
                border_style="green",
            )
        )
    elif issues:
        issue_list = "\n".join(f"  - {i}" for i in issues)
        warning_list = "\n".join(f"  - {w}" for w in warnings) if warnings else ""

        message = f"[red]Issues found ({len(issues)}):[/red]\n{issue_list}"
        if warnings:
            message += f"\n\n[yellow]Warnings ({len(warnings)}):[/yellow]\n{warning_list}"

        console.print(
            Panel.fit(message, title="[bold red]Health Check Failed[/bold red]", border_style="red")
        )
    else:
        warning_list = "\n".join(f"  - {w}" for w in warnings)
        console.print(
            Panel.fit(
                f"[yellow]Warnings ({len(warnings)}):[/yellow]\n{warning_list}\n\n"
                "System is functional but may need attention.",
                title="[bold yellow]Health Check Warnings[/bold yellow]",
                border_style="yellow",
            )
        )

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
