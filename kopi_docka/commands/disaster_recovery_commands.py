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
    sha256_file,
)

logger = get_logger(__name__)
console = Console()


def _print_external_secrets_panel(
    console: Console,
    manager: DisasterRecoveryManager,
    ssh_key_embedded: bool = False,
) -> None:
    """For SFTP/cloud backends, print a second panel after the "Bundle
    Created" success box that lists what is (or is not) in the bundle and
    what the user must keep at a separate location.

    For SFTP:
      - ``ssh_key_embedded=False`` (default): tells the user the SSH key
        is intentionally NOT in the bundle, shows its path + SHA256 so
        they have a fingerprint to verify the externally-held copy.
      - ``ssh_key_embedded=True`` (opt-in --include-ssh-key): warns that
        the bundle now carries the key and is a single point of
        compromise.

    Stays silent for filesystem repos (nothing to flag) and for export
    failures (this only runs on the success path).
    """
    try:
        info = manager._create_recovery_info()
    except Exception as e:
        logger.debug("Skipping external-secrets panel (recovery-info failed): %s", e)
        return

    rpt = info.get("repository", {})
    rt = rpt.get("type", "")
    conn = rpt.get("connection", {})

    if rt == "sftp":
        keyfile = conn.get("keyfile", "")
        if ssh_key_embedded:
            body = (
                "[bold red]This bundle INCLUDES your SSH private key.[/bold red]\n"
                "[dim]A single compromise (bundle + passphrase) gives full\n"
                "backup-server access. Store accordingly.[/dim]\n\n"
                "[bold]Treat this bundle like the SSH key itself:[/bold]\n"
                "  • Air-gapped offline storage\n"
                "  • Hardware token / encrypted vault\n"
                "  • Do NOT store next to the passphrase\n\n"
                f"[bold]Key embedded from:[/bold] [cyan]{keyfile}[/cyan]"
            )
        else:
            sha = sha256_file(Path(keyfile)) if keyfile else None
            body = (
                "[bold]This bundle does NOT contain your SSH private key.[/bold]\n"
                "[dim]Defense in depth: a single compromise (bundle + passphrase)\n"
                "won't grant backup-server access.[/dim]\n\n"
                "[bold]Store ALSO, at a SEPARATE location:[/bold]\n"
                f"  • [cyan]{keyfile or '(not configured)'}[/cyan]\n"
                f"    sha256: [yellow]{sha or '(could not read)'}[/yellow]\n\n"
                "[bold]Suggested storage:[/bold]\n"
                "  • Password-manager attachment (1Password / Bitwarden / KeePassXC)\n"
                "  • Separate encrypted USB stick at a different physical site\n"
                "  • GPG-symmetric encrypted in a different cloud\n"
                "  • Air-gapped paper printout (key is ~400 bytes)"
            )
        console.print()
        console.print(
            Panel.fit(
                body,
                title="[bold yellow]⚠  Additional Secrets Required[/bold yellow]",
                border_style="red" if ssh_key_embedded else "yellow",
            )
        )
    elif rt in {"s3", "b2", "azure", "gcs"}:
        secret_label = {
            "s3":    "AWS Access Key ID + Secret Access Key",
            "b2":    "B2 Account ID + Application Key",
            "azure": "Azure Storage Account name + Storage Key",
            "gcs":   "GCP service-account JSON file",
        }[rt]
        console.print()
        console.print(
            Panel.fit(
                f"[bold]This bundle does NOT contain cloud credentials.[/bold]\n"
                f"[dim]Defense in depth — credentials live separately.[/dim]\n\n"
                f"[bold]Keep separately (e.g. password manager):[/bold]\n"
                f"  • {secret_label}\n\n"
                "[dim]recover.sh will prompt for them interactively on restore.[/dim]",
                title="[bold yellow]⚠  Additional Secrets Required[/bold yellow]",
                border_style="yellow",
            )
        )


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
    include_ssh_key: bool = False,
    yes: bool = False,
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

    # --include-ssh-key safety gate (Plan 0030 / v7.5.1)
    if include_ssh_key:
        # Make sure the current backend actually has an SSH key to embed.
        # For non-SFTP backends the flag is a no-op — warn the user.
        kp = (cfg.get("kopia", "kopia_params", fallback="") or "").strip().lower()
        if not kp.startswith("sftp"):
            console.print(
                "[yellow]⚠ --include-ssh-key only applies to SFTP/Tailscale "
                "backends. Current backend has no SSH key — flag ignored.[/yellow]"
            )
            include_ssh_key = False
        elif not yes:
            console.print()
            console.print(
                Panel.fit(
                    "[bold red]⚠ Including the SSH private key in the bundle[/bold red]\n\n"
                    "This means a single compromise (bundle + passphrase) gives\n"
                    "full backup-server access. Recommended only when the bundle\n"
                    "is stored at a HIGHER trust level than the SSH key itself\n"
                    "(e.g. air-gapped offline storage, hardware token vault).\n\n"
                    "For the standard recommended posture, keep the key separate\n"
                    "(default behavior — leave [bold]--include-ssh-key[/bold] off).",
                    title="[bold red]Security Trade-off[/bold red]",
                    border_style="red",
                )
            )
            console.print()
            if not typer.confirm(
                "Include the SSH private key in this bundle?", default=False
            ):
                console.print("[dim]Aborted — proceeding without the SSH key.[/dim]")
                include_ssh_key = False

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
        manager.export_to_stream(passphrase, include_ssh_key=include_ssh_key)
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
            result_path = manager.export_to_file(
                Path(output).expanduser(), passphrase, include_ssh_key=include_ssh_key,
            )
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

        _print_external_secrets_panel(console, manager, ssh_key_embedded=include_ssh_key)

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
        include_ssh_key: bool = typer.Option(
            False,
            "--include-ssh-key",
            help=(
                "Embed the SSH private key (SFTP/Tailscale only). "
                "Default OFF — keep the key separate from the bundle "
                "for defense in depth. Requires explicit confirmation."
            ),
        ),
        yes: bool = typer.Option(
            False,
            "--yes",
            "-y",
            help="Skip the --include-ssh-key confirmation prompt (non-interactive).",
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

          # All-in-one bundle (NOT recommended — see help text)
          sudo kopi-docka disaster-recovery export /tmp/recovery.zip --include-ssh-key
        """
        cmd_disaster_recovery_export(
            ctx, output, stream, passphrase, passphrase_type,
            include_ssh_key=include_ssh_key, yes=yes,
        )

    app.add_typer(dr_app, name="disaster-recovery")
