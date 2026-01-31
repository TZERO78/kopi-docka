################################################################################
# KOPI-DOCKA
#
# @file:        setup_commands.py
# @module:      kopi_docka.commands
# @description: Master setup wizard - orchestrates complete setup flow
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Master Setup Wizard - Complete First-Time Setup

Orchestrates the complete setup process:
1. Check & install dependencies (Kopia)
2. Select repository storage type (filesystem/rclone/S3/B2/Azure/GCS/SFTP)
3. Configure repository settings
4. Create config file
5. Initialize repository

This is the "one command to set everything up" experience.
"""


import subprocess
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from ..helpers import get_logger
from ..cores.dependency_manager import DependencyManager
from ..helpers.ui_utils import (
    print_step,
    print_success,
    print_warning,
    print_error,
    print_next_steps,
    prompt_confirm,
)

logger = get_logger(__name__)
console = Console()


# ═══════════════════════════════════════════════════════════════════════════════
# Kopia Installation Helper
# ═══════════════════════════════════════════════════════════════════════════════

KOPIA_INSTALL_INSTRUCTIONS = """
[bold cyan]Ubuntu/Debian:[/bold cyan]
  curl -s https://kopia.io/signing-key | sudo gpg --dearmor -o /etc/apt/keyrings/kopia-keyring.gpg
  echo "deb [signed-by=/etc/apt/keyrings/kopia-keyring.gpg] http://packages.kopia.io/apt/ stable main" | sudo tee /etc/apt/sources.list.d/kopia.list
  sudo apt update && sudo apt install kopia

[bold cyan]Fedora/RHEL/CentOS:[/bold cyan]
  sudo rpm --import https://kopia.io/signing-key
  sudo dnf install -y dnf-plugins-core
  sudo dnf config-manager --add-repo https://kopia.io/repo/rpm/stable.repo
  sudo dnf install kopia

[bold cyan]Arch Linux (AUR):[/bold cyan]
  yay -S kopia-bin

[bold cyan]macOS (Homebrew):[/bold cyan]
  brew install kopia

[bold cyan]Universal (Official Script):[/bold cyan]
  curl -s https://kopia.io/install.sh | sudo bash
"""


def _handle_missing_kopia():
    """
    Handle missing Kopia installation with user-friendly guidance.
    
    Offers:
    1. Display installation instructions for various platforms
    2. Option to run official Kopia installer script
    3. Option to install manually and re-run setup
    """
    console.print()
    console.print(Panel(
        "[bold red]✗ Kopia not found[/bold red]\n\n"
        "Kopia is the backup engine that powers Kopi-Docka.\n"
        "It must be installed before continuing.\n\n"
        "[bold]Choose an option:[/bold]\n"
        "  [cyan][1][/cyan] Run official Kopia installer (recommended)\n"
        "  [cyan][2][/cyan] Show manual installation instructions\n"
        "  [cyan][3][/cyan] Exit and install manually",
        title="Missing Dependency",
        border_style="red"
    ))
    
    choice = Prompt.ask(
        "Select option",
        choices=["1", "2", "3"],
        default="1"
    )
    
    if choice == "1":
        _run_kopia_installer()
    elif choice == "2":
        console.print(Panel(
            KOPIA_INSTALL_INSTRUCTIONS,
            title="Kopia Installation Instructions",
            border_style="cyan"
        ))
        console.print("\n[yellow]After installing Kopia, run:[/yellow] [cyan]kopi-docka setup[/cyan]\n")
        raise typer.Exit(0)
    else:
        console.print("\n[dim]Install Kopia and run:[/dim] [cyan]kopi-docka setup[/cyan]\n")
        raise typer.Exit(0)


def _run_kopia_installer():
    """Run the official Kopia installer script."""
    console.print()
    console.print("[cyan]Running official Kopia installer...[/cyan]")
    console.print("[dim]Source: https://kopia.io/install.sh[/dim]\n")
    
    try:
        # Run the official installer
        result = subprocess.run(
            ["bash", "-c", "curl -s https://kopia.io/install.sh | sudo bash"],
            check=False,
        )
        
        if result.returncode != 0:
            print_warning("Installer returned non-zero exit code")
            console.print("[dim]You may need to install manually.[/dim]")
            
    except Exception as e:
        print_error(f"Failed to run installer: {e}")
        console.print(Panel(
            KOPIA_INSTALL_INSTRUCTIONS,
            title="Manual Installation Required",
            border_style="yellow"
        ))


def cmd_setup_wizard(
    force: bool = False,
    skip_deps: bool = False,
    skip_init: bool = False,
):
    """
    Complete setup wizard - guides through entire first-time setup.

    Steps:
    1. Check dependencies (Kopia, Docker)
    2. Select repository storage (local, S3, B2, etc.)
    3. Configure repository
    4. Initialize repository (optional)
    5. Setup notifications (optional)
    """
    # Display wizard header
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]Kopi-Docka Complete Setup Wizard[/bold cyan]\n\n"
            "This wizard will guide you through:\n"
            "  [1] Dependency verification\n"
            "  [2] Repository storage selection\n"
            "  [3] Configuration\n"
            "  [4] Repository initialization\n"
            "  [5] Notification setup (optional)",
            border_style="cyan",
        )
    )
    console.print()

    if not prompt_confirm("Continue?", default=True):
        raise typer.Exit(0)

    # ═══════════════════════════════════════════
    # Step 1: Dependencies
    # ═══════════════════════════════════════════
    if not skip_deps:
        print_step(1, 5, "Checking Dependencies")

        dep_mgr = DependencyManager()
        status = dep_mgr.check_all()

        if not status.get("kopia", False):
            _handle_missing_kopia()
            # Re-check after potential installation
            if not dep_mgr.check_kopia():
                print_error("Kopia is still not installed. Setup cannot continue.")
                raise typer.Exit(1)
            print_success("Kopia installed successfully!")
        else:
            print_success("Kopia found")

        if not status.get("docker", False):
            print_warning("Docker not found - required for backups!")
            console.print("   [dim]Install: https://docs.docker.com/engine/install/[/dim]")
        else:
            print_success("Docker found")

    # ═══════════════════════════════════════════
    # Step 2-3: Configuration (Repository + Password)
    # ═══════════════════════════════════════════
    print_step(2, 5, "Configuration Setup")

    # Use cmd_new_config for configuration - DRY!
    from ..commands.config_commands import cmd_new_config

    cfg = cmd_new_config(force=force, edit=False)

    kopia_params = cfg.get("kopia", "kopia_params")

    # ═══════════════════════════════════════════
    # Step 4: Repository Init (Optional)
    # ═══════════════════════════════════════════
    if not skip_init:
        print_step(4, 5, "Repository Initialization")

        if prompt_confirm("Initialize repository now?", default=True):
            console.print("[cyan]Initializing repository...[/cyan]")
            from ..commands.repository_commands import cmd_init

            try:
                # Create mock context
                import types

                ctx = types.SimpleNamespace()
                ctx.obj = {"config": cfg}
                cmd_init(ctx)
                print_success("Repository initialized!")
            except Exception as e:
                print_warning(f"Repository initialization failed: {e}")
                console.print(
                    "   [dim]You can initialize later with: kopi-docka advanced repo init[/dim]"
                )
        else:
            console.print("[dim]Skipped repository initialization[/dim]")

    # ═══════════════════════════════════════════
    # Step 5: Notification Setup (Optional)
    # ═══════════════════════════════════════════
    print_step(5, 5, "Notification Setup (Optional)")

    console.print(
        "[dim]Get notified about backup success/failure via Telegram, Discord, Email, etc.[/dim]"
    )
    console.print()

    if prompt_confirm("Setup backup notifications?", default=False):
        console.print()
        from ..commands.advanced.notification_commands import run_notification_setup

        try:
            run_notification_setup(cfg)
        except Exception as e:
            print_warning(f"Notification setup skipped: {e}")
            console.print(
                "   [dim]You can set it up later with: kopi-docka advanced notification setup[/dim]"
            )
    else:
        console.print("[dim]Skipped notification setup[/dim]")
        console.print(
            "   [dim]You can set it up later with: kopi-docka advanced notification setup[/dim]"
        )

    # ═══════════════════════════════════════════
    # Success Summary
    # ═══════════════════════════════════════════
    console.print()
    console.print(
        Panel.fit(
            "[green]✓ Setup Complete![/green]\n\n"
            "[bold]Configuration:[/bold]\n"
            f"  [cyan]Kopia params:[/cyan] {kopia_params}\n"
            f"  [cyan]Config file:[/cyan] {cfg.config_file}",
            title="[bold green]Success[/bold green]",
            border_style="green",
        )
    )

    print_next_steps(
        [
            "List Docker containers:\n   [cyan]sudo kopi-docka advanced snapshot list[/cyan]",
            "Test backup (dry-run):\n   [cyan]sudo kopi-docka dry-run[/cyan]",
            "Create first backup:\n   [cyan]sudo kopi-docka backup[/cyan]",
        ]
    )


# -------------------------
# Registration
# -------------------------


def register(app: typer.Typer):
    """Register setup commands."""

    @app.command("setup")
    def _setup_cmd(
        force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
        skip_deps: bool = typer.Option(False, "--skip-deps", help="Skip dependency check"),
        skip_init: bool = typer.Option(False, "--skip-init", help="Skip repository initialization"),
    ):
        """Complete setup wizard - first-time setup made easy."""
        cmd_setup_wizard(force=force, skip_deps=skip_deps, skip_init=skip_init)
