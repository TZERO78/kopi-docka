################################################################################
# KOPI-DOCKA
#
# @file:        config_commands.py
# @module:      kopi_docka.commands
# @description: Configuration management commands
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Configuration management commands."""

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from ..helpers import (
    Config,
    create_default_config,
    get_logger,
    generate_secure_password,
    detect_repository_type,
    detect_existing_filesystem_repo,
    is_cloud_backend,
)
from ..helpers.ui_utils import (
    print_success,
    print_error,
    print_warning,
    print_menu,
    print_success_panel,
    print_error_panel,
    print_warning_panel,
    print_next_steps,
    prompt_confirm,
    run_command,
)
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

# Storage backend registry - maps repository types to their setup/status classes
# Used by cmd_new_config() for interactive setup and cmd_status() for status display
BACKEND_MODULES = {
    "filesystem": LocalBackend,
    "s3": S3Backend,
    "b2": B2Backend,
    "azure": AzureBackend,
    "gcs": GCSBackend,
    "sftp": SFTPBackend,
    "tailscale": TailscaleBackend,
    "rclone": RcloneBackend,
}


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


# -------------------------
# Commands
# -------------------------


def cmd_config(ctx: typer.Context):
    """Show current configuration."""
    cfg = ensure_config(ctx)

    # Nutze die display() Methode der Config-Klasse - KISS!
    cfg.display()


def cmd_new_config(
    force: bool = False,
    edit: bool = True,
    path: Optional[Path] = None,
) -> Config:
    """
    Create new configuration file with interactive setup wizard.

    Returns:
        Config: The created configuration object
    """
    import getpass

    # Check if config exists
    existing_cfg = None
    try:
        if path:
            existing_cfg = Config(path)
        else:
            existing_cfg = Config()
    except Exception:
        pass  # Config doesn't exist, that's fine

    if existing_cfg and existing_cfg.config_file.exists():
        print_warning_panel(f"Config already exists at: {existing_cfg.config_file}")

        if not force:
            console.print("[bold]Use one of these options:[/bold]")
            console.print(
                "  [cyan]kopi-docka advanced config edit[/cyan]       - Modify existing config"
            )
            console.print(
                "  [cyan]kopi-docka advanced config new --force[/cyan] - Overwrite with warnings"
            )
            console.print(
                "  [cyan]kopi-docka advanced config reset[/cyan]      - Complete reset (DANGEROUS)"
            )
            console.print()
            raise typer.Exit(code=1)

        # With --force: Show warnings
        console.print(
            Panel.fit(
                "[bold red]WARNING: This will overwrite the existing configuration![/bold red]\n\n"
                "[yellow]This means:[/yellow]\n"
                "  [red]•[/red] A NEW password will be generated\n"
                "  [red]•[/red] The OLD password will NOT work anymore\n"
                "  [red]•[/red] You will LOSE ACCESS to existing backups!",
                title="[bold red]Danger[/bold red]",
                border_style="red",
            )
        )
        console.print()

        if not prompt_confirm("Continue anyway?", default=True):  # default_no=True
            console.print("[dim]Aborted.[/dim]")
            console.print()
            console.print("[bold]Safer alternatives:[/bold]")
            console.print(
                "  [cyan]kopi-docka advanced config edit[/cyan]        - Edit existing config"
            )
            console.print(
                "  [cyan]kopi-docka advanced repo change-password[/cyan] - Change password safely"
            )
            raise typer.Exit(code=0)

        # Backup old config
        from datetime import datetime
        import shutil

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp_backup = (
            existing_cfg.config_file.parent / f"{existing_cfg.config_file.stem}.{timestamp}.backup"
        )
        shutil.copy2(existing_cfg.config_file, timestamp_backup)
        print_success(f"Old config backed up to: {timestamp_backup}")
        console.print()

    # Create base config with template
    console.print()
    console.print(Panel.fit("[bold cyan]Kopi-Docka Setup Wizard[/bold cyan]", border_style="cyan"))
    console.print()

    created_path = create_default_config(path, force=True)
    cfg = Config(created_path)

    # ═══════════════════════════════════════════
    # Phase 1: Backup Scope Selection
    # ═══════════════════════════════════════════
    console.print(
        Panel.fit(
            "[bold cyan]Backup Scope Selection[/bold cyan]\n\n"
            "Choose how much data to include in backups:",
            border_style="cyan",
        )
    )
    console.print()

    print_menu(
        "Backup Scope Options",
        [
            (
                "1",
                "[yellow]minimal[/yellow]  - Volumes only (fastest, smallest)\n"
                "          ⚠️  Cannot restore containers, only data!",
            ),
            (
                "2",
                "[green]standard[/green] - Volumes + Recipes + Networks [RECOMMENDED]\n"
                "          ✅ Full container restore capability",
            ),
            (
                "3",
                "[blue]full[/blue]     - Everything + Docker daemon config (DR-ready)\n"
                "          ✅ Complete disaster recovery capability",
            ),
        ],
    )

    scope_choice = console.input("\n[cyan]Select backup scope [2]:[/cyan] ") or "2"
    try:
        scope_choice = int(scope_choice)
    except ValueError:
        scope_choice = 2

    scope_map = {1: "minimal", 2: "standard", 3: "full"}
    backup_scope = scope_map.get(scope_choice, "standard")

    if backup_scope == "minimal":
        console.print()
        console.print(
            Panel.fit(
                "[yellow]⚠️  WARNING: Minimal Scope Selected[/yellow]\n\n"
                "You will only be able to restore volume data.\n"
                "Containers must be recreated manually after restore.\n\n"
                "[bold]After restore with minimal scope:[/bold]\n"
                "  • Volumes will be restored ✅\n"
                "  • Containers must be recreated manually ❌\n"
                "  • Networks must be recreated manually ❌",
                title="[yellow]Important[/yellow]",
                border_style="yellow",
            )
        )
        console.print()
        if not prompt_confirm("Are you sure you want minimal scope?", default=True):
            backup_scope = "standard"
            console.print("[green]Changed to standard scope (recommended)[/green]")

    cfg.set("backup", "backup_scope", backup_scope)
    print_success(f"Backup scope set to: {backup_scope}")
    console.print()

    # ═══════════════════════════════════════════
    # Phase 2: Repository Storage Selection & Configuration
    # ═══════════════════════════════════════════
    print_menu(
        "Repository Storage",
        [
            ("1", "Local Filesystem  - Store on local disk/NAS mount"),
            ("2", "AWS S3           - Amazon S3 or compatible (Wasabi, MinIO)"),
            ("3", "Backblaze B2     - Cost-effective cloud storage"),
            ("4", "Azure Blob       - Microsoft Azure storage"),
            ("5", "Google Cloud     - GCS storage"),
            ("6", "SFTP             - Remote server via SSH"),
            ("7", "Tailscale        - P2P encrypted network"),
            ("8", "Rclone           - Universal (70+ cloud providers)"),
        ],
    )

    backend_choice = int(console.input("[cyan]Select repository type [1]:[/cyan] ") or "1")

    backend_map = {
        1: "filesystem",
        2: "s3",
        3: "b2",
        4: "azure",
        5: "gcs",
        6: "sftp",
        7: "tailscale",
        8: "rclone",
    }

    backend_type = backend_map.get(backend_choice, "filesystem")
    print_success(f"Selected: {backend_type}")
    console.print()

    # Use backend class for configuration
    backend_class = BACKEND_MODULES.get(backend_type)

    if backend_class:
        backend = backend_class({})
        result = backend.configure()
        kopia_params = result.get("kopia_params", "")

        # Show setup instructions if provided
        if "instructions" in result:
            console.print()
            console.print(result["instructions"])
    else:
        # Fallback
        print_warning(f"Repository type '{backend_type}' not found")
        repo_path = (
            console.input("[cyan]Repository path [/backup/kopia-repository]:[/cyan] ")
            or "/backup/kopia-repository"
        )
        kopia_params = f"filesystem --path {repo_path}"

    cfg.set("kopia", "kopia_params", kopia_params)
    console.print()

    # ═══════════════════════════════════════════
    # Phase 2.1: Check for existing repository
    # ═══════════════════════════════════════════
    existing_repo_detected = False
    repo_location = None

    # Check if repository already exists at the configured location
    if not is_cloud_backend(kopia_params):
        # Filesystem backend - check locally
        exists, path = detect_existing_filesystem_repo(kopia_params)
        if exists and path:
            existing_repo_detected = True
            repo_location = str(path)
    # Note: Cloud backend check will happen after password is set (needs password to probe)

    if existing_repo_detected:
        console.print(
            Panel.fit(
                f"[bold yellow]⚠️  Existing Kopia repository detected![/bold yellow]\n"
                f"Location: [cyan]{repo_location}[/cyan]\n\n"
                "[bold]repo init[/bold] will automatically connect to it.\n"
                "Make sure you use the [bold]correct password[/bold] for this repository!",
                title="[bold yellow]Repository Already Exists[/bold yellow]",
                border_style="yellow",
            )
        )
        console.print()

    # ═══════════════════════════════════════════
    # Phase 3: Password Setup
    # ═══════════════════════════════════════════
    if existing_repo_detected:
        # Repository exists - ask for existing password or delete
        console.print(
            Panel.fit(
                "[bold yellow]Existing Repository Detected[/bold yellow]\n\n"
                f"Location: [cyan]{repo_location}[/cyan]\n\n"
                "[bold]Options:[/bold]\n"
                "  [green]1[/green] - Enter existing password (connect to repository)\n"
                "  [red]2[/red] - Delete repository and start fresh",
                title="[yellow]Repository Already Exists[/yellow]",
                border_style="yellow",
            )
        )
        console.print()

        repo_action = console.input("[cyan]Select option [1]:[/cyan] ") or "1"
        console.print()

        if repo_action == "2":
            # Delete repository
            console.print(
                Panel.fit(
                    "[bold red]⚠️  WARNING: Repository Deletion[/bold red]\n\n"
                    "[bold]This will permanently delete:[/bold]\n"
                    f"  • Repository at: [cyan]{repo_location}[/cyan]\n"
                    "  • All backup snapshots\n"
                    "  • All backup metadata\n\n"
                    "[red]This action CANNOT be undone![/red]",
                    title="[red]Confirm Deletion[/red]",
                    border_style="red",
                )
            )
            console.print()

            if not prompt_confirm("Delete repository and all backups?", default=False):
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit(0)

            # Delete the repository
            try:
                if not is_cloud_backend(kopia_params):
                    # Filesystem - use rm -rf
                    run_command(
                        ["rm", "-rf", repo_location],
                        description=f"Deleting repository: {repo_location}",
                        check=True,
                        show_output=False,
                    )
                else:
                    # Cloud backend - try kopia delete
                    console.print("[dim]Cloud backend detected - attempting cleanup...[/dim]")
                    # For cloud backends, we'll let kopia handle it during init
                    # Just show a warning
                    console.print("[yellow]Note: Cloud backend cleanup will be handled by Kopia during initialization[/yellow]")

                print_success(f"✓ Repository deleted: {repo_location}")
                console.print()
                existing_repo_detected = False  # No longer exists

            except Exception as e:
                print_error(f"Failed to delete repository: {e}")
                raise typer.Exit(1)

        # Now ask for password (either for existing repo or new one after deletion)
        if repo_action == "1":
            # Connecting to existing repo
            console.print(
                Panel.fit(
                    "[bold cyan]Enter Existing Repository Password[/bold cyan]\n\n"
                    "Enter the password for the existing repository.",
                    border_style="cyan",
                )
            )
            console.print()

            max_attempts = 3
            password_validated = False

            for attempt in range(1, max_attempts + 1):
                password = getpass.getpass("Enter existing repository password: ")
                
                # Test password immediately
                console.print()
                console.print("[dim]Validating password...[/dim]")
                
                cfg.set_password(password, use_file=True)
                
                try:
                    from ..cores import KopiaRepository
                    test_repo = KopiaRepository(cfg)
                    test_repo.connect()
                    
                    # Success!
                    console.print()
                    print_success("✓ Password correct! Successfully connected to existing repository.")
                    console.print()
                    password_validated = True
                    break
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    if "invalid password" in error_msg or "password" in error_msg:
                        console.print()
                        print_error(f"✗ Invalid password (Attempt {attempt}/{max_attempts})")
                        
                        if attempt < max_attempts:
                            console.print("[yellow]Try again or press Ctrl+C to abort.[/yellow]")
                            console.print()
                    else:
                        # Other error (network, permissions, etc.)
                        console.print()
                        print_warning(f"Connection test failed: {e}")
                        console.print("[yellow]Cannot validate password, but continuing...[/yellow]")
                        console.print()
                        password_validated = True
                        break

            if not password_validated:
                console.print()
                print_error_panel(
                    f"Failed to validate password after {max_attempts} attempts.\n\n"
                    "[bold]Options:[/bold]\n"
                    "  • Run 'config new' again with the correct password\n"
                    "  • Delete the repository manually and start fresh:\n"
                    f"    [cyan]sudo rm -rf {repo_location}[/cyan]"
                )
                raise typer.Exit(1)

        else:
            # Deleted repo - now create new password
            existing_repo_detected = False

    if not existing_repo_detected:
        # New repository - ask for new password
        console.print(
            Panel.fit(
                "[bold cyan]Repository Encryption Password[/bold cyan]\n\n"
                "This password encrypts your backups.\n"
                "[red]If you lose this password, backups are UNRECOVERABLE![/red]",
                border_style="cyan",
            )
        )
        console.print()

        use_generated = prompt_confirm("Generate secure random password?", default=False)
        console.print()

        if use_generated:
            password = generate_secure_password()
            console.print(
                Panel.fit(
                    f"[bold yellow]GENERATED PASSWORD[/bold yellow]\n\n"
                    f"[bold white]{password}[/bold white]\n\n"
                    "[dim]Copy this password to:[/dim]\n"
                    "  [yellow]•[/yellow] Password manager (recommended)\n"
                    "  [yellow]•[/yellow] Encrypted USB drive\n"
                    "  [yellow]•[/yellow] Secure physical location\n\n"
                    "[red]If you lose this password, backups are UNRECOVERABLE![/red]",
                    title="[bold yellow]Save This Now![/bold yellow]",
                    border_style="yellow",
                )
            )
            console.print()
            console.input("[dim]Press Enter to continue...[/dim]")
        else:
            password = getpass.getpass("Enter password: ")
            password_confirm = getpass.getpass("Confirm password: ")

            if password != password_confirm:
                print_error_panel("Passwords don't match!")
                raise typer.Exit(1)

            if len(password) < 12:
                print_warning_panel(
                    f"Password is short ({len(password)} chars)\nRecommended: At least 12 characters"
                )
                if not prompt_confirm("Continue with this password?", default=True):
                    console.print("[dim]Aborted.[/dim]")
                    raise typer.Exit(0)

        # Save password to config
        cfg.set_password(password, use_file=True)
    
    console.print()

    # ═══════════════════════════════════════════
    # Phase 3: Summary & Next Steps
    # ═══════════════════════════════════════════
    password_file = cfg.config_file.parent / f".{cfg.config_file.stem}.password"

    console.print(
        Panel.fit(
            "[green]✓ Configuration Created Successfully[/green]\n\n"
            "[bold]Configuration:[/bold]\n"
            f"  [cyan]Config file:[/cyan]    {cfg.config_file}\n"
            f"  [cyan]Password file:[/cyan]  {password_file}\n"
            f"  [cyan]Kopia params:[/cyan]   {kopia_params}",
            title="[bold green]Success[/bold green]",
            border_style="green",
        )
    )

    # Customize next steps based on existing repo detection
    if existing_repo_detected:
        print_next_steps(
            [
                "[yellow]Connect to existing repository:[/yellow]\n   [cyan]sudo kopi-docka advanced repo init[/cyan]\n   [dim](Will connect using your password)[/dim]",
                "List Docker containers:\n   [cyan]sudo kopi-docka advanced snapshot list[/cyan]",
                "Test backup (dry-run):\n   [cyan]sudo kopi-docka dry-run[/cyan]",
                "Create backup:\n   [cyan]sudo kopi-docka backup[/cyan]",
            ]
        )
    else:
        print_next_steps(
            [
                "Initialize repository:\n   [cyan]sudo kopi-docka advanced repo init[/cyan]",
                "List Docker containers:\n   [cyan]sudo kopi-docka advanced snapshot list[/cyan]",
                "Test backup (dry-run):\n   [cyan]sudo kopi-docka dry-run[/cyan]",
                "Create first backup:\n   [cyan]sudo kopi-docka backup[/cyan]",
            ]
        )

    # ═══════════════════════════════════════════
    # Optional: Setup Notifications
    # ═══════════════════════════════════════════
    console.print()
    if prompt_confirm("Setup backup notifications? (Telegram, Discord, Email, etc.)", default=False):
        console.print()
        from ..commands.advanced.notification_commands import run_notification_setup

        try:
            run_notification_setup(cfg)
        except Exception as e:
            print_warning(f"Notification setup skipped: {e}")
            console.print("   [dim]You can set it up later with: kopi-docka advanced notification setup[/dim]")

    # Optional: Open in editor for advanced settings
    if edit:
        if prompt_confirm("Open config in editor for advanced settings?", default=True):
            editor = os.environ.get("EDITOR", "nano")
            console.print(f"\n[cyan]Opening in {editor}...[/cyan]")
            console.print("[dim]Advanced settings you can adjust:[/dim]")
            console.print("  [dim]• compression: zstd, s2, pgzip[/dim]")
            console.print("  [dim]• encryption: AES256-GCM-HMAC-SHA256, etc.[/dim]")
            console.print("  [dim]• parallel_workers: auto, or specific number[/dim]")
            console.print("  [dim]• retention: daily/weekly/monthly/yearly[/dim]")
            console.print()
            run_command(
                [editor, str(created_path)],
                description=f"Opening {editor}",
                check=False,
                show_output=True,
            )

    # Return config object (for use in setup wizard)
    return cfg


def cmd_edit_config(ctx: typer.Context, editor: Optional[str] = None):
    """Edit existing configuration file."""
    cfg = ensure_config(ctx)

    if not editor:
        editor = os.environ.get("EDITOR", "nano")

    console.print(f"[cyan]Opening {cfg.config_file} in {editor}...[/cyan]")
    run_command(
        [editor, str(cfg.config_file)],
        description=f"Opening {editor}",
        check=False,
        show_output=True,
    )

    # Validate after editing
    try:
        Config(cfg.config_file)
        print_success("Configuration valid")
    except Exception as e:
        print_warning(f"Configuration might have issues: {e}")


def _config_reconnect_mode(path: Optional[Path] = None):
    """
    Reconnect mode: Fix password in config for existing repository.

    This is the safe alternative to full reset when you just need to
    correct the password in your config to match an existing repository.
    """
    import getpass
    from ..cores import KopiaRepository

    console.print(
        Panel.fit(
            "[bold cyan]RECONNECT MODE[/bold cyan]\n\n"
            "This will help you reconnect to an existing repository\n"
            "by updating the password in your configuration.\n\n"
            "[green]✓ Your existing config will be preserved[/green]\n"
            "[green]✓ Your repository data stays intact[/green]\n"
            "[green]✓ Only the password will be updated[/green]",
            title="[bold]Repository Reconnection[/bold]",
            border_style="cyan",
        )
    )
    console.print()

    # Find config
    config_path = path or (
        Path("/etc/kopi-docka.conf")
        if os.geteuid() == 0
        else Path.home() / ".config" / "kopi-docka" / "config.conf"
    )

    if not config_path.exists():
        print_error_panel(
            f"Config not found: {config_path}\n\n"
            "[dim]Create a new config with:[/dim] [cyan]kopi-docka advanced config new[/cyan]"
        )
        raise typer.Exit(code=1)

    try:
        cfg = Config(config_path)
    except Exception as e:
        print_error_panel(f"Failed to load config: {e}")
        raise typer.Exit(code=1)

    kopia_params = cfg.get("kopia", "kopia_params", fallback="")
    if not kopia_params:
        print_error_panel("No repository configured in this config file.")
        raise typer.Exit(code=1)

    console.print(f"[bold]Config:[/bold] {config_path}")
    console.print(f"[bold]Repository:[/bold] {kopia_params}")
    console.print()

    # Password retry loop
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        console.print(f"[dim]Attempt {attempt}/{max_attempts}[/dim]")
        new_password = getpass.getpass("Enter repository password: ")

        if not new_password:
            console.print("[yellow]Password cannot be empty.[/yellow]")
            continue

        # Save password to config BEFORE trying to connect
        console.print("[dim]Saving password to config...[/dim]")
        cfg.set_password(new_password, use_file=True)

        # Reload config to pick up new password
        cfg = Config(config_path)

        # Try to connect
        console.print("[cyan]Testing connection...[/cyan]")
        try:
            repo = KopiaRepository(cfg)
            repo.connect()

            console.print()
            print_success_panel(
                "Successfully reconnected to repository!\n\n"
                f"[bold]Config:[/bold] {config_path}\n"
                f"[bold]Repository:[/bold] {kopia_params}"
            )

            from ..helpers.ui_utils import print_next_steps
            print_next_steps(
                [
                    "Show repository status: [cyan]kopi-docka advanced repo status[/cyan]",
                    "List backup units: [cyan]kopi-docka advanced snapshot list[/cyan]",
                    "Test backup: [cyan]kopi-docka dry-run[/cyan]",
                ]
            )
            return

        except Exception as e:
            error_msg = str(e).lower()
            if "invalid password" in error_msg or "password" in error_msg:
                console.print("[red]Invalid password.[/red]")
            else:
                console.print(f"[red]Connection failed: {e}[/red]")

            if attempt < max_attempts:
                console.print("[dim]Please try again.[/dim]")
                console.print()

    # All attempts failed
    console.print()
    print_error_panel(
        f"Failed to connect after {max_attempts} attempts.\n\n"
        "[bold]Options:[/bold]\n"
        "  • Try again with the correct password\n"
        "  • Check if repository exists at the configured location\n"
        "  • Full reset if you want to start fresh:\n"
        "    [cyan]kopi-docka advanced config reset[/cyan] (without --reconnect)"
    )
    raise typer.Exit(code=1)


def cmd_reset_config(path: Optional[Path] = None):
    """
    Reset configuration completely (DANGEROUS).

    Deletes existing config and creates new one with new password.
    Use this only if you want to start fresh or have no existing backups.

    Examples:
        # Full reset (DANGEROUS - loses access to existing backups)
        kopi-docka advanced config reset
    """
    # Full reset mode
    console.print(
        Panel.fit(
            "[bold red]DANGER ZONE: CONFIGURATION RESET[/bold red]\n\n"
            "[yellow]This operation will:[/yellow]\n"
            "  [red]1.[/red] DELETE the existing configuration\n"
            "  [red]2.[/red] Generate a COMPLETELY NEW password\n"
            "  [red]3.[/red] Make existing backups INACCESSIBLE\n\n"
            "[green]✓ Only proceed if:[/green]\n"
            "  • You want to start completely fresh\n"
            "  • You have no existing backups\n"
            "  • You have backed up your old password elsewhere\n\n"
            "[red]✗ DO NOT proceed if:[/red]\n"
            "  • You have existing backups you want to keep\n"
            "  • You just want to change a setting (use 'admin config edit' instead)",
            title="[bold red]Warning[/bold red]",
            border_style="red",
        )
    )
    console.print()

    # First confirmation
    if not prompt_confirm(
        "Do you understand that this will make existing backups inaccessible?", default=True
    ):
        console.print("[green]Aborted - Good choice![/green]")
        raise typer.Exit(code=0)

    # Show what will be reset
    existing_path = path or (
        Path("/etc/kopi-docka.conf")
        if os.geteuid() == 0
        else Path.home() / ".config" / "kopi-docka" / "config.conf"
    )

    if existing_path.exists():
        console.print(f"\n[bold]Config to reset:[/bold] {existing_path}")

        # Try to show current repository path
        try:
            cfg = Config(existing_path)
            # Show kopia_params
            kopia_params = cfg.get("kopia", "kopia_params", fallback="")

            if kopia_params:
                console.print(f"[cyan]Current kopia_params:[/cyan] {kopia_params}")
            else:
                print_warning("No repository configured")
            console.print()
            print_warning("If you want to KEEP this repository, you must:")
            console.print("  [dim]1. Backup your current password from the config[/dim]")
            console.print("  [dim]2. Copy it to the new config after creation[/dim]")
        except Exception:
            pass

    console.print()

    # Second confirmation with explicit typing
    confirmation = console.input(
        "[red]Type 'DELETE' to confirm reset (or anything else to abort):[/red] "
    )
    if confirmation != "DELETE":
        console.print("[dim]Aborted.[/dim]")
        raise typer.Exit(code=0)

    # Backup before deletion
    if existing_path.exists():
        from datetime import datetime
        import shutil

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = existing_path.parent / f"{existing_path.stem}.{timestamp}.backup"
        shutil.copy2(existing_path, backup_path)
        print_success(f"Backup created: {backup_path}")

        # Also backup password file if exists
        password_file = existing_path.parent / f".{existing_path.stem}.password"
        if password_file.exists():
            password_backup = (
                existing_path.parent / f".{existing_path.stem}.{timestamp}.password.backup"
            )
            shutil.copy2(password_file, password_backup)
            print_success(f"Password backed up: {password_backup}")

    # Delete old config
    if existing_path.exists():
        existing_path.unlink()
        print_success(f"Deleted old config: {existing_path}")

    console.print()

    # Create new config
    console.print("[cyan]Creating fresh configuration...[/cyan]")
    cmd_new_config(force=True, edit=True, path=path)


def cmd_change_password(
    ctx: typer.Context,
    new_password: Optional[str] = None,
    use_file: bool = True,  # Default: Store in external file
):
    """Change Kopia repository password and store securely."""
    cfg = ensure_config(ctx)
    from ..cores import KopiaRepository

    repo = KopiaRepository(cfg)

    # Connect check
    try:
        if not repo.is_connected():
            console.print("[cyan]Connecting to repository...[/cyan]")
            repo.connect()
    except Exception as e:
        print_error_panel(
            f"Failed to connect: {e}\n\n"
            "[bold]Make sure:[/bold]\n"
            "  • Repository exists and is initialized\n"
            "  • Current password in config is correct"
        )
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            "[bold cyan]Change Kopia Repository Password[/bold cyan]\n\n"
            f"[cyan]Repository:[/cyan] {repo.repo_path}\n"
            f"[cyan]Profile:[/cyan] {repo.profile_name}",
            border_style="cyan",
        )
    )
    console.print()

    # Verify current password first (security best practice)
    import getpass

    console.print("[bold]Verify current password:[/bold]")
    current_password = getpass.getpass("Current password: ")

    console.print("[cyan]Verifying current password...[/cyan]")
    if not repo.verify_password(current_password):
        print_error_panel(
            "Current password is incorrect!\n\n"
            "[bold]If you've forgotten the password:[/bold]\n"
            "  • Check /etc/.kopi-docka.password\n"
            "  • Check password_file setting in config\n"
            "  • As last resort: reset repository (lose all backups)"
        )
        raise typer.Exit(code=1)

    print_success("Current password verified")
    console.print()

    # Get new password
    if not new_password:
        console.print("[bold]Enter new password (empty = auto-generate):[/bold]")
        new_password = getpass.getpass("New password: ")

        if not new_password:
            new_password = generate_secure_password()
            console.print(
                Panel.fit(
                    f"[bold yellow]GENERATED PASSWORD[/bold yellow]\n\n"
                    f"[bold white]{new_password}[/bold white]",
                    title="[bold yellow]New Password[/bold yellow]",
                    border_style="yellow",
                )
            )
            if not prompt_confirm("Use this password?", default=False):
                console.print("[dim]Aborted.[/dim]")
                raise typer.Exit(code=0)
        else:
            new_password_confirm = getpass.getpass("Confirm new password: ")
            if new_password != new_password_confirm:
                print_error_panel("Passwords don't match!")
                raise typer.Exit(code=1)

    if len(new_password) < 12:
        print_warning_panel(f"Password is short ({len(new_password)} chars)")
        if not prompt_confirm("Continue?", default=True):
            raise typer.Exit(code=0)

    # Change in Kopia repository - KISS!
    console.print("\n[cyan]Changing repository password...[/cyan]")
    try:
        repo.set_repo_password(new_password)
        print_success("Repository password changed")
    except Exception as e:
        print_error_panel(f"Error: {e}")
        raise typer.Exit(code=1)

    # Store password using Config class - KISS!
    console.print("[cyan]Storing new password...[/cyan]")
    try:
        cfg.set_password(new_password, use_file=use_file)

        if use_file:
            password_file = cfg.config_file.parent / f".{cfg.config_file.stem}.password"
            print_success(f"Password stored in: {password_file} (chmod 600)")
        else:
            print_success(f"Password stored in: {cfg.config_file} (chmod 600)")
    except Exception as e:
        print_error_panel(f"Failed to store password: {e}")
        print_warning_panel(
            f"IMPORTANT: Write down this password manually!\nPassword: {new_password}"
        )
        raise typer.Exit(code=1)

    print_success_panel("Password changed successfully!")


def cmd_status(ctx: typer.Context):
    """Show detailed status of configured repository storage."""
    from rich.console import Console

    cfg = ensure_config(ctx)
    console = Console()

    # Detect repository type from kopia_params
    kopia_params = cfg.get("kopia", "kopia_params", fallback="")
    backend_type = detect_repository_type(kopia_params)

    console.print(f"\n[bold cyan]Repository Type:[/bold cyan] {backend_type}")

    # Get backend class
    backend_class = BACKEND_MODULES.get(backend_type)
    if not backend_class:
        console.print(f"[red]❌ Repository type '{backend_type}' not available[/red]\n")
        raise typer.Exit(code=1)

    # Build backend config from kopia_params
    # Note: Credentials are stored externally (rclone.conf, env vars, SSH keys)
    # not in the kopi-docka config file
    backend_config = {"kopia_params": kopia_params}

    # Initialize backend
    backend = backend_class(backend_config)

    # Get status
    console.print("\n[dim]Checking repository status...[/dim]")
    status = backend.get_status()

    # Display based on backend type
    if backend_type == "tailscale":
        _display_tailscale_status(console, status)
    elif backend_type == "filesystem":
        _display_filesystem_status(console, status)
    else:
        _display_generic_status(console, status, backend_type)


def _display_tailscale_status(console, status):
    """Display Tailscale-specific status."""
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    # Create status table
    table = Table(title="Tailscale Backup Target Status", box=box.ROUNDED, show_header=False)
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value", style="white")

    # Tailscale status
    ts_status = "🟢 Running" if status.get("tailscale_running") else "🔴 Not Running"
    table.add_row("Tailscale", ts_status)

    # Peer info
    if status.get("hostname"):
        table.add_row("Hostname", status["hostname"])
    if status.get("ip"):
        table.add_row("IP Address", status["ip"])

    # Online status
    online_status = "🟢 Online" if status.get("online") else "🔴 Offline"
    table.add_row("Peer Status", online_status)

    # Latency
    if status.get("ping_ms") is not None:
        latency_color = (
            "green" if status["ping_ms"] < 50 else "yellow" if status["ping_ms"] < 150 else "red"
        )
        table.add_row("Latency", f"[{latency_color}]{status['ping_ms']}ms[/{latency_color}]")

    # SSH status
    ssh_status = "🟢 Connected" if status.get("ssh_connected") else "🔴 No Connection"
    table.add_row("SSH", ssh_status)

    # Disk space (if available)
    if status.get("disk_free_gb") is not None and status.get("disk_total_gb") is not None:
        used_gb = status["disk_total_gb"] - status["disk_free_gb"]
        used_percent = (used_gb / status["disk_total_gb"]) * 100

        # Color based on usage
        disk_color = "green" if used_percent < 70 else "yellow" if used_percent < 90 else "red"

        disk_info = (
            f"[{disk_color}]{status['disk_free_gb']:.1f}GB free[/{disk_color}] / "
            f"{status['disk_total_gb']:.1f}GB total "
            f"([{disk_color}]{used_percent:.1f}% used[/{disk_color}])"
        )
        table.add_row("Disk Space", disk_info)
    elif status.get("ssh_connected"):
        table.add_row("Disk Space", "[yellow]Could not retrieve[/yellow]")

    console.print()
    console.print(table)
    console.print()

    # Health check summary
    if not status.get("tailscale_running"):
        console.print(
            Panel(
                "[red]⚠️  Tailscale is not running![/red]\nRun: [cyan]sudo tailscale up[/cyan]",
                title="Warning",
                border_style="red",
            )
        )
    elif not status.get("online"):
        console.print(
            Panel(
                "[yellow]⚠️  Peer is offline![/yellow]\nMake sure the backup target is powered on and connected to Tailscale.",
                title="Warning",
                border_style="yellow",
            )
        )
    elif not status.get("ssh_connected"):
        console.print(
            Panel(
                "[yellow]⚠️  SSH connection failed![/yellow]\nCheck SSH keys and permissions.",
                title="Warning",
                border_style="yellow",
            )
        )
    else:
        console.print(
            Panel(
                "[green]✓ All systems operational![/green]\nReady for backups.",
                title="Status",
                border_style="green",
            )
        )


def _display_filesystem_status(console, status):
    """Display filesystem-specific status."""
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    details = status.get("details", {})

    # Create status table
    table = Table(title="Filesystem Repository Status", box=box.ROUNDED, show_header=False)
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value", style="white")

    # Path
    if details.get("path"):
        table.add_row("Repository Path", details["path"])

    # Exists status
    exists_status = "🟢 Exists" if details.get("exists") else "🔴 Not Found"
    table.add_row("Path Status", exists_status)

    # Writable
    if details.get("exists"):
        writable_status = "🟢 Writable" if details.get("writable") else "🔴 Read-Only"
        table.add_row("Write Access", writable_status)

    # Disk space
    if details.get("disk_free_gb") is not None and details.get("disk_total_gb") is not None:
        used_gb = details["disk_total_gb"] - details["disk_free_gb"]
        used_percent = (used_gb / details["disk_total_gb"]) * 100

        # Color based on usage
        disk_color = "green" if used_percent < 70 else "yellow" if used_percent < 90 else "red"

        disk_info = (
            f"[{disk_color}]{details['disk_free_gb']:.1f}GB free[/{disk_color}] / "
            f"{details['disk_total_gb']:.1f}GB total "
            f"([{disk_color}]{used_percent:.1f}% used[/{disk_color}])"
        )
        table.add_row("Disk Space", disk_info)

    console.print()
    console.print(table)
    console.print()

    # Health check
    if not details.get("exists"):
        console.print(
            Panel(
                f"[red]⚠️  Repository path does not exist![/red]\nCreate it first or run: [cyan]kopi-docka init[/cyan]",
                title="Warning",
                border_style="red",
            )
        )
    elif not details.get("writable"):
        console.print(
            Panel(
                "[red]⚠️  Repository is not writable![/red]\nCheck permissions.",
                title="Warning",
                border_style="red",
            )
        )
    elif status.get("available"):
        console.print(
            Panel(
                "[green]✓ Filesystem repository ready![/green]\nReady for backups.",
                title="Status",
                border_style="green",
            )
        )


def _display_generic_status(console, status, backend_type):
    """Display generic status for repository types."""
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    # Create status table
    table = Table(
        title=f"{backend_type.upper()} Repository Status", box=box.ROUNDED, show_header=False
    )
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value", style="white")

    # Configured
    configured_status = "🟢 Yes" if status.get("configured") else "🔴 No"
    table.add_row("Configured", configured_status)

    # Available
    available_status = "🟢 Available" if status.get("available") else "🔴 Not Available"
    table.add_row("Connection", available_status)

    # Show any details
    details = status.get("details", {})
    for key, value in details.items():
        if value is not None:
            table.add_row(key.replace("_", " ").title(), str(value))

    console.print()
    console.print(table)
    console.print()

    if not status.get("configured"):
        console.print(
            Panel(
                f"[yellow]⚠️  Repository not configured![/yellow]\nRun: [cyan]kopi-docka advanced config new[/cyan]",
                title="Warning",
                border_style="yellow",
            )
        )
    elif not status.get("available"):
        console.print(
            Panel(
                f"[yellow]⚠️  Repository not available![/yellow]\nCheck configuration and connectivity.",
                title="Warning",
                border_style="yellow",
            )
        )
    else:
        console.print(
            Panel(
                f"[green]✓ {backend_type.title()} repository ready![/green]\nReady for backups.",
                title="Status",
                border_style="green",
            )
        )


# -------------------------
# Registration
# -------------------------


def register(app: typer.Typer):
    """Register configuration commands."""

    @app.command("show-config")
    def _config_cmd(ctx: typer.Context):
        """Show current configuration."""
        cmd_config(ctx, show=True)

    @app.command("new-config")
    def _new_config_cmd(
        force: bool = typer.Option(
            False, "--force", "-f", help="Overwrite existing config (with warnings)"
        ),
        edit: bool = typer.Option(True, "--edit/--no-edit", help="Open in editor after creation"),
        path: Optional[Path] = typer.Option(None, "--path", help="Custom config path"),
    ):
        """Create new configuration file."""
        cmd_new_config(force, edit, path)

    @app.command("edit-config")
    def _edit_config_cmd(
        ctx: typer.Context,
        editor: Optional[str] = typer.Option(None, "--editor", help="Specify editor to use"),
    ):
        """Edit existing configuration file."""
        cmd_edit_config(ctx, editor)

    @app.command("reset-config")
    def _reset_config_cmd(
        path: Optional[Path] = typer.Option(None, "--path", help="Custom config path"),
    ):
        """Reset configuration completely (DANGEROUS - creates new password!)."""
        cmd_reset_config(path)

    @app.command("change-password")
    def _change_password_cmd(
        ctx: typer.Context,
        new_password: Optional[str] = typer.Option(
            None, "--new-password", help="New password (will prompt if not provided)"
        ),
        use_file: bool = typer.Option(
            True, "--file/--inline", help="Store in external file (default) or inline in config"
        ),
    ):
        """Change Kopia repository password."""
        cmd_change_password(ctx, new_password, use_file)

    @app.command("status")
    def _status_cmd(ctx: typer.Context):
        """Show detailed repository storage status (disk space, connectivity, etc.)."""
        cmd_status(ctx)
