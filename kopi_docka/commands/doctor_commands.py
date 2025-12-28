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
1. System Information
2. Core Dependencies (with categories)
3. Systemd Integration
4. Backend Dependencies
5. Configuration status
6. Repository status (Kopia connection - the single source of truth)

Note: Repository connection status IS the definitive check. If Kopia can
connect to the repository, the underlying storage (filesystem, rclone, s3, etc.)
is automatically working. No separate backend checks needed.
"""

from typing import Optional
import platform

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ..helpers import Config, get_logger, detect_repository_type
from ..helpers.dependency_helper import DependencyHelper
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
# Helper Functions for Sections
# -------------------------


def _show_system_info():
    """Display simplified system information."""
    import kopi_docka

    console.print("[bold]1. System Information[/bold]")
    console.print("-" * 40)

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value", style="white")

    table.add_row("OS", platform.system())
    table.add_row("Python Version", platform.python_version())
    table.add_row("Kopi-Docka Version", kopi_docka.__version__)

    console.print(table)
    console.print()


def _show_core_dependencies(dep_manager: DependencyManager):
    """Display core dependency status with categories."""
    console.print("[bold]2. Core Dependencies[/bold]")
    console.print("-" * 40)

    table = Table(box=box.SIMPLE)
    table.add_column("Tool", style="cyan", width=15)
    table.add_column("Category", style="magenta", width=12)
    table.add_column("Status", width=12)
    table.add_column("Version", style="yellow", width=15)
    table.add_column("Path", style="dim")

    for dep_name, dep_info in dep_manager.dependencies.items():
        tool_info = DependencyHelper.check(dep_name)

        category = str(dep_info.get("category", "UNKNOWN")).replace("DependencyCategory.", "")

        if tool_info.installed:
            status = "[green]✓ Installed[/green]"
            version = tool_info.version or "N/A"
            path = tool_info.path or "N/A"
        else:
            status = "[red]✗ Missing[/red]"
            version = "—"
            path = "—"

        table.add_row(dep_name, category, status, version, path)

    console.print(table)
    console.print()


def _show_systemd_status():
    """Display systemd integration status."""
    console.print("[bold]3. Systemd Integration[/bold]")
    console.print("-" * 40)

    systemd_tools = ["systemctl", "journalctl"]
    tool_status = DependencyHelper.check_all(systemd_tools)

    table = Table(box=box.SIMPLE)
    table.add_column("Tool", style="cyan", width=15)
    table.add_column("Status", width=15)
    table.add_column("Version", style="yellow")

    for tool_name, tool_info in tool_status.items():
        if tool_info.installed:
            status = "[green]✓ Available[/green]"
            version = tool_info.version or "N/A"
        else:
            status = "[yellow]○ Missing[/yellow]"
            version = "—"

        table.add_row(tool_name, status, version)

    console.print(table)

    if not all(t.installed for t in tool_status.values()):
        console.print("[yellow]⚠ Some features may be limited without systemd[/yellow]")

    console.print()


def _show_backend_dependencies(cfg: Optional[Config]):
    """Display backend-specific dependencies."""
    console.print("[bold]4. Backend Dependencies[/bold]")
    console.print("-" * 40)

    if not cfg:
        console.print("[dim]No configuration - backends not loaded[/dim]")
        console.print()
        return

    # Get backend type from config
    kopia_params = cfg.get("kopia", "kopia_params", fallback="")
    repo_type = detect_repository_type(kopia_params)

    if repo_type == "unknown":
        console.print("[dim]No backend configured[/dim]")
        console.print()
        return

    # Try to load the backend and check dependencies
    try:
        from ..backends import get_backend_class

        backend_class = get_backend_class(repo_type)
        if backend_class and hasattr(backend_class, 'REQUIRED_TOOLS'):
            backend = backend_class(cfg.to_dict())

            table = Table(box=box.SIMPLE)
            table.add_column("Backend", style="cyan", width=15)
            table.add_column("Tool", style="white", width=15)
            table.add_column("Status", width=15)
            table.add_column("Version", style="yellow")

            if hasattr(backend, 'get_dependency_status'):
                dep_status = backend.get_dependency_status()

                for tool_name, tool_info in dep_status.items():
                    if tool_info.installed:
                        status = "[green]✓[/green]"
                        version = tool_info.version or "N/A"
                    else:
                        status = "[red]✗ Missing[/red]"
                        version = "—"

                    table.add_row(repo_type.upper(), tool_name, status, version)

                console.print(table)
            else:
                console.print(f"[dim]Backend {repo_type} does not support dependency checking[/dim]")
        else:
            console.print(f"[dim]Backend {repo_type} has no dependency requirements[/dim]")
    except Exception as e:
        console.print(f"[yellow]Could not check backend dependencies: {e}[/yellow]")

    console.print()


# -------------------------
# Commands
# -------------------------


def cmd_doctor(ctx: typer.Context, verbose: bool = False):
    """
    Run comprehensive system health check.

    Checks:
    1. System Information
    2. Core Dependencies (with categories)
    3. Systemd Integration
    4. Backend Dependencies
    5. Configuration status
    6. Repository status (connection is the single source of truth)
    """
    console.print()
    console.print(
        Panel.fit("[bold cyan]Kopi-Docka System Health Check[/bold cyan]", border_style="cyan")
    )
    console.print()

    issues = []
    warnings = []

    cfg = get_config(ctx)
    dep_manager = DependencyManager()

    # ═══════════════════════════════════════════
    # Section 1: System Information
    # ═══════════════════════════════════════════
    _show_system_info()

    # ═══════════════════════════════════════════
    # Section 2: Core Dependencies (with categories)
    # ═══════════════════════════════════════════
    _show_core_dependencies(dep_manager)

    # Check for critical missing dependencies
    dep_status = dep_manager.check_all()
    if not dep_status.get("kopia", False):
        issues.append("Kopia is not installed")
    if not dep_status.get("docker", False):
        issues.append("Docker is not running")

    # ═══════════════════════════════════════════
    # Section 3: Systemd Integration
    # ═══════════════════════════════════════════
    _show_systemd_status()

    # ═══════════════════════════════════════════
    # Section 4: Backend Dependencies
    # ═══════════════════════════════════════════
    _show_backend_dependencies(cfg)

    # ═══════════════════════════════════════════
    # Section 5: Configuration
    # ═══════════════════════════════════════════
    console.print("[bold]5. Configuration[/bold]")
    console.print("-" * 40)

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
    # Section 6: Repository Status
    # (Kopia connection is the SINGLE SOURCE OF TRUTH)
    # ═══════════════════════════════════════════
    if cfg:
        console.print("[bold]6. Repository Status[/bold]")
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
