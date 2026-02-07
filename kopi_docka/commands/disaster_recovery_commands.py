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

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..helpers import Config, get_logger
from ..cores.disaster_recovery_manager import (
    DisasterRecoveryManager,
    generate_passphrase,
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


def cmd_disaster_recovery_export(
    ctx: typer.Context,
    output: Optional[Path] = None,
    stream: bool = False,
    passphrase: Optional[str] = None,
    passphrase_type: str = "words",
):
    """
    Export disaster recovery bundle as a single encrypted ZIP file.

    This creates ONE password-protected ZIP archive (AES-256) containing
    everything needed to reconnect to the Kopia repository on a new system.
    No external tools (tar, openssl) required.

    Examples:

        # Interactive mode (generates passphrase, asks for confirmation)
        sudo kopi-docka disaster-recovery export /home/user/recovery.zip

        # With custom passphrase
        sudo kopi-docka disaster-recovery export /home/user/recovery.zip --passphrase "my-secret"

        # SSH stream mode (zero disk footprint on server)
        ssh user@server "sudo kopi-docka disaster-recovery export --stream --passphrase 'xxx'" > recovery.zip
    """
    # HARD GATE: Check kopia
    from kopi_docka.helpers.dependency_helper import DependencyHelper

    if not DependencyHelper.exists("kopia"):
        console.print(
            "\n[red]✗ Cannot proceed - kopia is required[/red]\n\n"
            "Disaster Recovery requires Kopia to access the repository.\n\n"
            "Installation:\n"
            "  • Kopia: https://kopia.io/docs/installation/\n\n"
            "After installation, verify with:\n"
            "  kopi-docka doctor\n"
        )
        raise typer.Exit(code=1)

    cfg = ensure_config(ctx)
    manager = DisasterRecoveryManager(cfg)

    if stream:
        # ── Stream mode: ZIP → stdout (for SSH piping) ──
        if not passphrase:
            console.print(
                "[red]✗ --stream requires --passphrase[/red]\n"
                "  (no TTY available for interactive passphrase generation)\n\n"
                "Example:\n"
                '  ssh user@server "sudo kopi-docka disaster-recovery export '
                "--stream --passphrase 'my-secret'\" > recovery.zip",
                err=True,
            )
            raise typer.Exit(code=1)

        # All informational output goes to stderr; ZIP goes to stdout
        console.print("[cyan]Creating encrypted DR bundle (streaming)...[/cyan]", err=True)
        manager.export_to_stream(passphrase)
        console.print("[green]✓ Bundle streamed successfully[/green]", err=True)

    else:
        # ── File mode: interactive passphrase handling ──
        if not output:
            console.print(
                "[red]✗ Output path required (or use --stream)[/red]\n\n"
                "Usage:\n"
                "  sudo kopi-docka disaster-recovery export /home/user/recovery.zip\n"
                "  sudo kopi-docka disaster-recovery export --stream --passphrase 'xxx'"
            )
            raise typer.Exit(code=1)

        # Check parent directory is writable
        output_parent = output.expanduser().parent
        if output_parent.exists() and not os.access(output_parent, os.W_OK):
            console.print(f"[red]✗ Output directory is not writable: {output_parent}[/red]")
            raise typer.Exit(code=1)

        if not passphrase:
            # Generate and confirm passphrase interactively
            generated = generate_passphrase(style=passphrase_type)

            console.print()
            console.print(
                Panel.fit(
                    f"[bold cyan]Generated Passphrase:[/bold cyan]\n\n"
                    f"  [bold yellow]{generated}[/bold yellow]\n\n"
                    "[dim]Write this down in a secure location![/dim]",
                    title="[bold cyan]🔑 Passphrase[/bold cyan]",
                    border_style="cyan",
                )
            )
            console.print()

            confirmed = typer.prompt("Re-enter passphrase to confirm")
            if confirmed != generated:
                console.print("[red]✗ Passphrase does not match![/red]")
                raise typer.Exit(code=1)

            passphrase = generated

        # Create the bundle
        console.print()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Creating encrypted ZIP bundle...", total=None)
            result_path = manager.export_to_file(Path(output).expanduser(), passphrase)
            progress.update(task, completed=True)

        size_mb = result_path.stat().st_size / 1024 / 1024

        console.print()
        console.print(
            Panel.fit(
                f"[green]✓ Recovery bundle created![/green]\n\n"
                f"[bold]File:[/bold] {result_path}\n"
                f"[bold]Size:[/bold] {size_mb:.1f} MB\n"
                f"[bold]Format:[/bold] AES-256 encrypted ZIP\n\n"
                "[yellow]⚠️  IMPORTANT:[/yellow]\n"
                "  • Store the passphrase in a secure location\n"
                "  • The passphrase is NOT stored in the file\n"
                "  • Test recovery procedure regularly\n"
                "  • Extract with: 7-Zip, WinZip, unzip, etc.\n\n"
                "[bold]To extract:[/bold]\n"
                f"  7z x {result_path.name}   [dim](enter passphrase when prompted)[/dim]\n"
                "  [dim]or:[/dim]\n"
                f"  unzip {result_path.name}   [dim](enter passphrase when prompted)[/dim]",
                title="[bold green]Bundle Created[/bold green]",
                border_style="green",
            )
        )
        console.print()


def register(app: typer.Typer):
    """Register disaster recovery commands."""

    # Create a sub-app for the disaster-recovery group
    dr_app = typer.Typer(
        name="disaster-recovery",
        help="Disaster recovery bundle management.",
        add_completion=False,
    )

    @dr_app.callback(invoke_without_command=True)
    def _dr_callback(
        ctx: typer.Context,
        output: Optional[Path] = typer.Option(
            None,
            "--output",
            "-o",
            help="Output directory for the bundle (legacy mode).",
        ),
        no_password_file: bool = typer.Option(
            False,
            "--no-password-file",
            help="Don't write password to sidecar file.",
        ),
        skip_dependency_check: bool = typer.Option(
            False,
            "--skip-dependency-check",
            help="Skip optional dependency checks (tar, openssl).",
        ),
    ):
        """
        Create disaster recovery bundle.

        DEPRECATED: Use 'disaster-recovery export' for the new single-file ZIP format.
        """
        # If a subcommand is being invoked, don't run the legacy behavior
        if ctx.invoked_subcommand is not None:
            return

        # Legacy mode: show deprecation warning
        console.print()
        console.print(
            Panel.fit(
                "[yellow]⚠️  DEPRECATION WARNING[/yellow]\n\n"
                "The legacy 3-file bundle format (tar.gz.enc + PASSWORD + README)\n"
                "is deprecated and will be removed in a future release.\n\n"
                "[bold]Use the new single-file ZIP format instead:[/bold]\n"
                "  [cyan]sudo kopi-docka disaster-recovery export /path/to/recovery.zip[/cyan]\n\n"
                "[bold]Or stream via SSH (zero disk footprint):[/bold]\n"
                "  [cyan]ssh user@server \"sudo kopi-docka disaster-recovery export "
                "--stream --passphrase 'xxx'\" > recovery.zip[/cyan]\n\n"
                "[dim]Benefits: Single file, AES-256 ZIP, no tar/openssl needed,[/dim]\n"
                "[dim]automatic ownership, cross-platform extraction.[/dim]",
                title="[bold yellow]Deprecated Command[/bold yellow]",
                border_style="yellow",
            )
        )
        console.print()

        # Run the legacy command
        cmd_disaster_recovery(ctx, output, no_password_file, skip_dependency_check)

    @dr_app.command("export")
    def _dr_export_cmd(
        ctx: typer.Context,
        output: Optional[Path] = typer.Argument(
            None,
            help="Output path for the encrypted ZIP file. Omit with --stream.",
        ),
        stream: bool = typer.Option(
            False,
            "--stream",
            help="Stream ZIP to stdout (for SSH piping). Requires --passphrase.",
        ),
        passphrase: Optional[str] = typer.Option(
            None,
            "--passphrase",
            help="Encryption passphrase. If omitted, one is generated interactively.",
        ),
        passphrase_type: str = typer.Option(
            "words",
            "--passphrase-type",
            help="Passphrase style: 'words' (memorable) or 'random' (alphanumeric).",
        ),
    ):
        """
        Export disaster recovery bundle as encrypted ZIP.

        Creates a single AES-256 encrypted ZIP file containing everything
        needed to restore your Kopia repository on a new system.

        No external tools (tar, openssl) required. The ZIP can be extracted
        with any standard tool (7-Zip, WinZip, unzip).

        \b
        Examples:
          # Interactive (generates passphrase, asks for confirmation)
          sudo kopi-docka disaster-recovery export /home/user/recovery.zip

          # With custom passphrase
          sudo kopi-docka disaster-recovery export /home/user/dr.zip --passphrase "my-secret"

          # SSH stream (zero disk footprint on server)
          ssh user@server "sudo kopi-docka disaster-recovery export --stream --passphrase 'xxx'" > recovery.zip
        """
        cmd_disaster_recovery_export(ctx, output, stream, passphrase, passphrase_type)

    app.add_typer(dr_app, name="disaster-recovery")
