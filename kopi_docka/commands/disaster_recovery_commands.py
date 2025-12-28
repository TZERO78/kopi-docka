################################################################################
# KOPI-DOCKA
#
# @file:        disaster_recovery_commands.py
# @module:      kopi_docka.commands
# @description: Disaster recovery bundle commands
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Disaster recovery commands."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..helpers import Config, get_logger
from ..cores.disaster_recovery_manager import DisasterRecoveryManager

logger = get_logger(__name__)
console = Console()


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


def ensure_config(ctx: typer.Context) -> Config:
    """Ensure config exists or exit."""
    cfg = get_config(ctx)
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka advanced config new")
        raise typer.Exit(code=1)
    return cfg


def cmd_disaster_recovery(
    ctx: typer.Context,
    output: Optional[Path] = None,
    no_password_file: bool = False,
    skip_dependency_check: bool = False,
):
    """
    Create disaster recovery bundle.

    Creates an encrypted bundle containing:
    - Kopia repository configuration
    - Repository password
    - Kopi-Docka configuration
    - Recovery script (recover.sh)
    - Human-readable instructions
    - Recent backup status

    The bundle is encrypted with AES-256-CBC and a random password.
    """
    # HARD GATE: Check kopia (docker not needed for disaster recovery)
    from kopi_docka.cores.dependency_manager import DependencyManager
    dep_manager = DependencyManager()

    # Check only kopia, not docker (DR doesn't need docker)
    from kopi_docka.helpers.dependency_helper import DependencyHelper
    if not DependencyHelper.exists("kopia"):
        from rich.console import Console
        console_err = Console()
        console_err.print(
            "\n[red]✗ Cannot proceed - kopia is required[/red]\n\n"
            "Disaster Recovery requires Kopia to access the repository.\n\n"
            "Installation:\n"
            "  • Kopia: https://kopia.io/docs/installation/\n\n"
            "Automated Setup:\n"
            "  Use Server-Baukasten for automated system preparation:\n"
            "  https://github.com/TZERO78/Server-Baukasten\n\n"
            "After installation, verify with:\n"
            "  kopi-docka doctor\n"
        )
        raise typer.Exit(code=1)

    # SOFT GATE: Check tar and openssl (needed for bundle creation)
    dep_manager.check_soft_gate(
        required_tools=["tar", "openssl"],
        skip=skip_dependency_check
    )

    cfg = ensure_config(ctx)

    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]Disaster Recovery Bundle Creation[/bold cyan]\n\n"
            "This will create an encrypted bundle containing everything\n"
            "needed to reconnect to your Kopia repository on a new system.",
            border_style="cyan",
        )
    )
    console.print()

    try:
        manager = DisasterRecoveryManager(cfg)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Creating recovery bundle...", total=None)

            bundle_path = manager.create_recovery_bundle(
                output_dir=output, write_password_file=not no_password_file
            )

            progress.update(task, completed=True)

        console.print()
        console.print(
            Panel.fit(
                f"[green]✓ Recovery bundle created successfully![/green]\n\n"
                f"[bold]Bundle:[/bold] {bundle_path}\n"
                f"[bold]README:[/bold] {bundle_path}.README\n"
                + (
                    f"[bold]Password:[/bold] {bundle_path}.PASSWORD\n"
                    if not no_password_file
                    else ""
                )
                + "\n[yellow]⚠️  IMPORTANT:[/yellow]\n"
                "  • Store the password in a secure location\n"
                "  • Test recovery procedure regularly\n"
                "  • Keep bundle separate from production system\n\n"
                "[bold]To decrypt:[/bold]\n"
                f"  openssl enc -aes-256-cbc -salt -pbkdf2 -d \\\n"
                f"    -in {bundle_path.name} \\\n"
                f"    -out {bundle_path.stem} \\\n"
                "    -pass pass:'<PASSWORD>'",
                title="[bold green]Bundle Created[/bold green]",
                border_style="green",
            )
        )
        console.print()

    except Exception as e:
        console.print(f"[red]✗ Failed to create recovery bundle: {e}[/red]")
        logger.error(f"Recovery bundle creation failed: {e}", exc_info=True)
        raise typer.Exit(code=1)


def register(app: typer.Typer):
    """Register disaster recovery commands."""

    @app.command("disaster-recovery")
    def _disaster_recovery_cmd(
        ctx: typer.Context,
        output: Optional[Path] = typer.Option(
            None,
            "--output",
            "-o",
            help="Output directory for the bundle. Defaults to config recovery_bundle_path.",
        ),
        no_password_file: bool = typer.Option(
            False,
            "--no-password-file",
            help="Don't write password to sidecar file (more secure, but you must save it manually).",
        ),
        skip_dependency_check: bool = typer.Option(
            False,
            "--skip-dependency-check",
            help="Skip optional dependency checks (tar, openssl). Not recommended.",
        ),
    ):
        """Create disaster recovery bundle."""
        cmd_disaster_recovery(ctx, output, no_password_file, skip_dependency_check)
