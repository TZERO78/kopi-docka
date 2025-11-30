################################################################################
# KOPI-DOCKA
#
# @file:        config_commands.py
# @module:      kopi_docka.commands
# @description: Configuration management commands
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.3.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Configuration management commands."""

import os
import subprocess
from pathlib import Path
from typing import Optional

import typer

from ..helpers import Config, create_default_config, get_logger, generate_secure_password
from ..backends.local import LocalBackend
from ..backends.s3 import S3Backend
from ..backends.b2 import B2Backend
from ..backends.azure import AzureBackend
from ..backends.gcs import GCSBackend
from ..backends.sftp import SFTPBackend
from ..backends.tailscale import TailscaleBackend

logger = get_logger(__name__)

# Backend registry (shared with setup) - backend classes
BACKEND_MODULES = {
    'filesystem': LocalBackend,
    's3': S3Backend,
    'b2': B2Backend,
    'azure': AzureBackend,
    'gcs': GCSBackend,
    'sftp': SFTPBackend,
    'tailscale': TailscaleBackend,
}


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


def ensure_config(ctx: typer.Context) -> Config:
    """Ensure config exists or exit."""
    cfg = get_config(ctx)
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka new-config")
        raise typer.Exit(code=1)
    return cfg


# -------------------------
# Commands
# -------------------------

def cmd_config(ctx: typer.Context, show: bool = True):
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
        typer.echo(f"⚠️  Config already exists at: {existing_cfg.config_file}")
        typer.echo("")
        
        if not force:
            typer.echo("Use one of these options:")
            typer.echo("  kopi-docka edit-config       - Modify existing config")
            typer.echo("  kopi-docka new-config --force - Overwrite with warnings")
            typer.echo("  kopi-docka reset-config      - Complete reset (DANGEROUS)")
            raise typer.Exit(code=1)
        
        # With --force: Show warnings
        typer.echo("⚠️  WARNING: This will overwrite the existing configuration!")
        typer.echo("")
        typer.echo("This means:")
        typer.echo("  • A NEW password will be generated")
        typer.echo("  • The OLD password will NOT work anymore")
        typer.echo("  • You will LOSE ACCESS to existing backups!")
        typer.echo("")
        
        if not typer.confirm("Continue anyway?", default=False):
            typer.echo("Aborted.")
            typer.echo("")
            typer.echo("💡 Safer alternatives:")
            typer.echo("  kopi-docka edit-config        - Edit existing config")
            typer.echo("  kopi-docka change-password    - Change repository password safely")
            raise typer.Exit(code=0)
        
        # Backup old config
        from datetime import datetime
        import shutil
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        timestamp_backup = existing_cfg.config_file.parent / f"{existing_cfg.config_file.stem}.{timestamp}.backup"
        shutil.copy2(existing_cfg.config_file, timestamp_backup)
        typer.echo(f"✓ Old config backed up to: {timestamp_backup}")
        typer.echo("")

    # Create base config with template
    typer.echo("╭─────────────────────────────────────────╮")
    typer.echo("│ Kopi-Docka Setup Wizard                 │")
    typer.echo("╰─────────────────────────────────────────╯")
    typer.echo("")
    
    created_path = create_default_config(path, force=True)
    cfg = Config(created_path)
    
    # ═══════════════════════════════════════════
    # Phase 1: Backend Selection & Configuration
    # ═══════════════════════════════════════════
    typer.echo("─────────────────────────────────────────")
    typer.echo("→ Backend Selection")
    typer.echo("─────────────────────────────────────────")
    typer.echo("")
    typer.echo("Where should backups be stored?")
    typer.echo("")
    typer.echo("Available backends:")
    typer.echo("  1. Local Filesystem  - Store on local disk/NAS mount")
    typer.echo("  2. AWS S3           - Amazon S3 or compatible (Wasabi, MinIO)")
    typer.echo("  3. Backblaze B2     - Cost-effective cloud storage")
    typer.echo("  4. Azure Blob       - Microsoft Azure storage")
    typer.echo("  5. Google Cloud     - GCS storage")
    typer.echo("  6. SFTP             - Remote server via SSH")
    typer.echo("  7. Tailscale        - P2P encrypted network")
    typer.echo("")
    
    backend_choice = typer.prompt(
        "Select backend",
        type=int,
        default=1,
        show_default=True
    )
    
    backend_map = {
        1: "filesystem",
        2: "s3",
        3: "b2",
        4: "azure",
        5: "gcs",
        6: "sftp",
        7: "tailscale",
    }
    
    backend_type = backend_map.get(backend_choice, "filesystem")
    typer.echo(f"\n✓ Selected: {backend_type}")
    typer.echo("")
    
    # Use backend class for configuration
    backend_class = BACKEND_MODULES.get(backend_type)
    
    if backend_class:
        backend = backend_class({})
        result = backend.configure()
        kopia_params = result.get('kopia_params', '')
        
        # Show setup instructions if provided
        if 'instructions' in result:
            typer.echo("")
            typer.echo(result['instructions'])
    else:
        # Fallback
        typer.echo(f"⚠️  Backend '{backend_type}' not found")
        repo_path = typer.prompt("Repository path", default="/backup/kopia-repository")
        kopia_params = f"filesystem --path {repo_path}"
    
    cfg.set('kopia', 'kopia_params', kopia_params)
    typer.echo("")
    
    # ═══════════════════════════════════════════
    # Phase 2: Password Setup
    # ═══════════════════════════════════════════
    typer.echo("─────────────────────────────────────────")
    typer.echo("→ Repository Encryption Password")
    typer.echo("─────────────────────────────────────────")
    typer.echo("")
    typer.echo("This password encrypts your backups.")
    typer.echo("⚠️  If you lose this password, backups are UNRECOVERABLE!")
    typer.echo("")
    
    use_generated = typer.confirm("Generate secure random password?", default=True)
    typer.echo("")
    
    if use_generated:
        password = generate_secure_password()
        typer.echo("═════════════════════════════════════════════════════════════")
        typer.echo("🔑 GENERATED PASSWORD (save this NOW!):")
        typer.echo("")
        typer.echo(f"   {password}")
        typer.echo("")
        typer.echo("═════════════════════════════════════════════════════════════")
        typer.echo("⚠️  Copy this to:")
        typer.echo("   • Password manager (recommended)")
        typer.echo("   • Encrypted USB drive")
        typer.echo("   • Secure physical location")
        typer.echo("═════════════════════════════════════════════════════════════")
        typer.echo("")
        input("Press Enter to continue...")
    else:
        password = getpass.getpass("Enter password: ")
        password_confirm = getpass.getpass("Confirm password: ")
        
        if password != password_confirm:
            typer.echo("❌ Passwords don't match!")
            raise typer.Exit(1)
        
        if len(password) < 12:
            typer.echo(f"\n⚠️  WARNING: Password is short ({len(password)} chars)")
            typer.echo("Recommended: At least 12 characters")
            if not typer.confirm("Continue with this password?", default=False):
                typer.echo("Aborted.")
                raise typer.Exit(0)
    
    # Save password to config
    cfg.set_password(password, use_file=True)
    typer.echo("")
    
    # ═══════════════════════════════════════════
    # Phase 3: Summary & Next Steps
    # ═══════════════════════════════════════════
    typer.echo("─────────────────────────────────────────")
    typer.echo("✓ Configuration Created Successfully")
    typer.echo("─────────────────────────────────────────")
    typer.echo("")
    typer.echo(f"Config file:    {cfg.config_file}")
    password_file = cfg.config_file.parent / f".{cfg.config_file.stem}.password"
    typer.echo(f"Password file:  {password_file}")
    typer.echo(f"Kopia params:   {kopia_params}")
    typer.echo("")
    
    typer.echo("╭──────────────────────────────────────────╮")
    typer.echo("│ Setup Complete! Next Steps:              │")
    typer.echo("╰──────────────────────────────────────────╯")
    typer.echo("")
    typer.echo("1. Initialize repository:")
    typer.echo("   sudo kopi-docka init")
    typer.echo("")
    typer.echo("2. List Docker containers:")
    typer.echo("   sudo kopi-docka list --units")
    typer.echo("")
    typer.echo("3. Test backup (dry-run):")
    typer.echo("   sudo kopi-docka dry-run")
    typer.echo("")
    typer.echo("4. Create first backup:")
    typer.echo("   sudo kopi-docka backup")
    typer.echo("")
    
    # Optional: Open in editor for advanced settings
    if edit:
        typer.echo("─────────────────────────────────────────")
        if typer.confirm("Open config in editor for advanced settings?", default=False):
            editor = os.environ.get('EDITOR', 'nano')
            typer.echo(f"\nOpening in {editor}...")
            typer.echo("Advanced settings you can adjust:")
            typer.echo("  • compression: zstd, s2, pgzip")
            typer.echo("  • encryption: AES256-GCM-HMAC-SHA256, etc.")
            typer.echo("  • parallel_workers: auto, or specific number")
            typer.echo("  • retention: daily/weekly/monthly/yearly")
            typer.echo("")
            subprocess.call([editor, str(created_path)])
    
    # Return config object (for use in setup wizard)
    return cfg


def cmd_edit_config(ctx: typer.Context, editor: Optional[str] = None):
    """Edit existing configuration file."""
    cfg = ensure_config(ctx)

    if not editor:
        editor = os.environ.get('EDITOR', 'nano')

    typer.echo(f"Opening {cfg.config_file} in {editor}...")
    subprocess.call([editor, str(cfg.config_file)])

    # Validate after editing
    try:
        Config(cfg.config_file)
        typer.echo("✓ Configuration valid")
    except Exception as e:
        typer.echo(f"⚠️  Configuration might have issues: {e}")


def cmd_reset_config(path: Optional[Path] = None):
    """
    Reset configuration completely (DANGEROUS).
    
    This will delete the existing config and create a new one with a new password.
    Use this only if you want to start fresh or have no existing backups.
    """
    typer.echo("=" * 70)
    typer.echo("⚠️  DANGER ZONE: CONFIGURATION RESET")
    typer.echo("=" * 70)
    typer.echo("")
    typer.echo("This operation will:")
    typer.echo("  1. DELETE the existing configuration")
    typer.echo("  2. Generate a COMPLETELY NEW password")
    typer.echo("  3. Make existing backups INACCESSIBLE")
    typer.echo("")
    typer.echo("✓ Only proceed if:")
    typer.echo("  • You want to start completely fresh")
    typer.echo("  • You have no existing backups")
    typer.echo("  • You have backed up your old password elsewhere")
    typer.echo("")
    typer.echo("✗ DO NOT proceed if:")
    typer.echo("  • You have existing backups you want to keep")
    typer.echo("  • You just want to change a setting (use 'edit-config' instead)")
    typer.echo("=" * 70)
    typer.echo("")
    
    # First confirmation
    if not typer.confirm("Do you understand that this will make existing backups inaccessible?", default=False):
        typer.echo("Aborted - Good choice!")
        raise typer.Exit(code=0)
    
    # Show what will be reset
    existing_path = path or (Path('/etc/kopi-docka.conf') if os.geteuid() == 0 
                             else Path.home() / '.config' / 'kopi-docka' / 'config.conf')
    
    if existing_path.exists():
        typer.echo(f"\nConfig to reset: {existing_path}")
        
        # Try to show current repository path
        try:
            cfg = Config(existing_path)
            # Show kopia_params
            kopia_params = cfg.get('kopia', 'kopia_params', fallback='')
            
            if kopia_params:
                typer.echo(f"Current kopia_params: {kopia_params}")
            else:
                typer.echo("⚠️  No repository configured")
            typer.echo("")
            typer.echo("⚠️  If you want to KEEP this repository, you must:")
            typer.echo("  1. Backup your current password from the config")
            typer.echo("  2. Copy it to the new config after creation")
        except Exception:
            pass
    
    typer.echo("")
    
    # Second confirmation with explicit typing
    confirmation = typer.prompt("Type 'DELETE' to confirm reset (or anything else to abort)")
    if confirmation != "DELETE":
        typer.echo("Aborted.")
        raise typer.Exit(code=0)
    
    # Backup before deletion
    if existing_path.exists():
        from datetime import datetime
        import shutil
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = existing_path.parent / f"{existing_path.stem}.{timestamp}.backup"
        shutil.copy2(existing_path, backup_path)
        typer.echo(f"\n✓ Backup created: {backup_path}")
        
        # Also backup password file if exists
        password_file = existing_path.parent / f".{existing_path.stem}.password"
        if password_file.exists():
            password_backup = existing_path.parent / f".{existing_path.stem}.{timestamp}.password.backup"
            shutil.copy2(password_file, password_backup)
            typer.echo(f"✓ Password backed up: {password_backup}")
    
    # Delete old config
    if existing_path.exists():
        existing_path.unlink()
        typer.echo(f"✓ Deleted old config: {existing_path}")
    
    typer.echo("")
    
    # Create new config
    typer.echo("Creating fresh configuration...")
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
            typer.echo("↻ Connecting to repository...")
            repo.connect()
    except Exception as e:
        typer.echo(f"✗ Failed to connect: {e}")
        typer.echo("\nMake sure:")
        typer.echo("  • Repository exists and is initialized")
        typer.echo("  • Current password in config is correct")
        raise typer.Exit(code=1)
    
    typer.echo("=" * 70)
    typer.echo("CHANGE KOPIA REPOSITORY PASSWORD")
    typer.echo("=" * 70)
    typer.echo(f"Repository: {repo.repo_path}")
    typer.echo(f"Profile: {repo.profile_name}")
    typer.echo("")
    
    # Verify current password first (security best practice)
    import getpass
    typer.echo("Verify current password:")
    current_password = getpass.getpass("Current password: ")
    
    typer.echo("↻ Verifying current password...")
    if not repo.verify_password(current_password):
        typer.echo("✗ Current password is incorrect!")
        typer.echo("\nIf you've forgotten the password:")
        typer.echo("  • Check /etc/.kopi-docka.password")
        typer.echo("  • Check password_file setting in config")
        typer.echo("  • As last resort: reset repository (lose all backups)")
        raise typer.Exit(code=1)
    
    typer.echo("✓ Current password verified")
    typer.echo("")
    
    # Get new password
    if not new_password:
        typer.echo("Enter new password (empty = auto-generate):")
        new_password = getpass.getpass("New password: ")
        
        if not new_password:
            new_password = generate_secure_password()
            typer.echo("\n" + "=" * 70)
            typer.echo("GENERATED PASSWORD:")
            typer.echo(new_password)
            typer.echo("=" * 70 + "\n")
            if not typer.confirm("Use this password?"):
                typer.echo("Aborted.")
                raise typer.Exit(code=0)
        else:
            new_password_confirm = getpass.getpass("Confirm new password: ")
            if new_password != new_password_confirm:
                typer.echo("✗ Passwords don't match!")
                raise typer.Exit(code=1)
    
    if len(new_password) < 12:
        typer.echo(f"\n⚠️  WARNING: Password is short ({len(new_password)} chars)")
        if not typer.confirm("Continue?"):
            raise typer.Exit(code=0)
    
    # Change in Kopia repository - KISS!
    typer.echo("\n↻ Changing repository password...")
    try:
        repo.set_repo_password(new_password)
        typer.echo("✓ Repository password changed")
    except Exception as e:
        typer.echo(f"✗ Error: {e}")
        raise typer.Exit(code=1)
    
    # Store password using Config class - KISS!
    typer.echo("\n↻ Storing new password...")
    try:
        cfg.set_password(new_password, use_file=use_file)
        
        if use_file:
            password_file = cfg.config_file.parent / f".{cfg.config_file.stem}.password"
            typer.echo(f"✓ Password stored in: {password_file} (chmod 600)")
        else:
            typer.echo(f"✓ Password stored in: {cfg.config_file} (chmod 600)")
    except Exception as e:
        typer.echo(f"✗ Failed to store password: {e}")
        typer.echo("\n⚠️  IMPORTANT: Write down this password manually!")
        typer.echo(f"Password: {new_password}")
        raise typer.Exit(code=1)
    
    typer.echo("\n" + "=" * 70)
    typer.echo("✓ PASSWORD CHANGED SUCCESSFULLY")
    typer.echo("=" * 70)


def cmd_status(ctx: typer.Context):
    """Show detailed status of configured backend."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    cfg = ensure_config(ctx)
    console = Console()

    # Get backend type from config
    backend_type = cfg.get('backend', 'type', fallback='filesystem')

    console.print(f"\n[bold cyan]Backend:[/bold cyan] {backend_type}")

    # Get backend class
    backend_class = BACKEND_MODULES.get(backend_type)
    if not backend_class:
        console.print(f"[red]❌ Backend '{backend_type}' not available[/red]\n")
        raise typer.Exit(code=1)

    # Load backend config
    backend_config = {}

    # Get kopia_params
    kopia_params = cfg.get('kopia', 'kopia_params', fallback='')
    if kopia_params:
        backend_config['kopia_params'] = kopia_params

    # Get credentials from config (if present)
    try:
        import json
        creds_str = cfg.get('backend', 'credentials', fallback='{}')
        credentials = json.loads(creds_str) if isinstance(creds_str, str) else creds_str
        if credentials:
            backend_config['credentials'] = credentials
    except Exception:
        pass

    # Get repository path
    repo_path = cfg.get('kopia', 'repository_path', fallback='')
    if repo_path:
        backend_config['repository_path'] = repo_path

    # Initialize backend
    backend = backend_class(backend_config)

    # Get status
    console.print("\n[dim]Checking backend status...[/dim]")
    status = backend.get_status()

    # Display based on backend type
    if backend_type == 'tailscale':
        _display_tailscale_status(console, status)
    elif backend_type == 'filesystem':
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
        latency_color = "green" if status["ping_ms"] < 50 else "yellow" if status["ping_ms"] < 150 else "red"
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
        console.print(Panel(
            "[red]⚠️  Tailscale is not running![/red]\nRun: [cyan]sudo tailscale up[/cyan]",
            title="Warning",
            border_style="red"
        ))
    elif not status.get("online"):
        console.print(Panel(
            "[yellow]⚠️  Peer is offline![/yellow]\nMake sure the backup target is powered on and connected to Tailscale.",
            title="Warning",
            border_style="yellow"
        ))
    elif not status.get("ssh_connected"):
        console.print(Panel(
            "[yellow]⚠️  SSH connection failed![/yellow]\nCheck SSH keys and permissions.",
            title="Warning",
            border_style="yellow"
        ))
    else:
        console.print(Panel(
            "[green]✓ All systems operational![/green]\nReady for backups.",
            title="Status",
            border_style="green"
        ))


def _display_filesystem_status(console, status):
    """Display filesystem-specific status."""
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    details = status.get("details", {})

    # Create status table
    table = Table(title="Filesystem Backend Status", box=box.ROUNDED, show_header=False)
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
        console.print(Panel(
            f"[red]⚠️  Repository path does not exist![/red]\nCreate it first or run: [cyan]kopi-docka init[/cyan]",
            title="Warning",
            border_style="red"
        ))
    elif not details.get("writable"):
        console.print(Panel(
            "[red]⚠️  Repository is not writable![/red]\nCheck permissions.",
            title="Warning",
            border_style="red"
        ))
    elif status.get("available"):
        console.print(Panel(
            "[green]✓ Filesystem backend ready![/green]\nReady for backups.",
            title="Status",
            border_style="green"
        ))


def _display_generic_status(console, status, backend_type):
    """Display generic status for other backends."""
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    # Create status table
    table = Table(title=f"{backend_type.upper()} Backend Status", box=box.ROUNDED, show_header=False)
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
        console.print(Panel(
            f"[yellow]⚠️  Backend not configured![/yellow]\nRun: [cyan]kopi-docka new-config[/cyan]",
            title="Warning",
            border_style="yellow"
        ))
    elif not status.get("available"):
        console.print(Panel(
            f"[yellow]⚠️  Backend not available![/yellow]\nCheck configuration and connectivity.",
            title="Warning",
            border_style="yellow"
        ))
    else:
        console.print(Panel(
            f"[green]✓ {backend_type.title()} backend ready![/green]\nReady for backups.",
            title="Status",
            border_style="green"
        ))


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
        force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config (with warnings)"),
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
        new_password: Optional[str] = typer.Option(None, "--new-password", help="New password (will prompt if not provided)"),
        use_file: bool = typer.Option(True, "--file/--inline", help="Store in external file (default) or inline in config"),
    ):
        """Change Kopia repository password."""
        cmd_change_password(ctx, new_password, use_file)

    @app.command("status")
    def _status_cmd(ctx: typer.Context):
        """Show detailed backend status (disk space, connectivity, etc.)."""
        cmd_status(ctx)
