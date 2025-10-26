"""
Configuration commands for Kopi-Docka v2

Configuration management and password handling.
"""

import os
import subprocess
import getpass
from typing import Optional
from pathlib import Path

import typer
from rich.console import Console

from kopi_docka.cli import utils
from kopi_docka.i18n import t, get_current_language

# Create sub-app for config commands
app = typer.Typer(
    help="Configuration management commands",
)

console = Console()


@app.command(name="show")
def config_show():
    """
    Show current configuration
    
    Displays the active configuration file and its settings.
    """
    from kopi_docka.helpers.config import Config
    
    utils.print_header(
        "Configuration Overview",
        "Current Kopi-Docka settings"
    )
    
    try:
        cfg = Config()
        cfg.display()
    except Exception as e:
        utils.print_error(f"Failed to load configuration: {e}")
        utils.print_info("\nCreate a new config with: kopi-docka config new")
        raise typer.Exit(1)


@app.command(name="new")
def config_new(
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Overwrite existing config (with warnings)"
    ),
    no_edit: bool = typer.Option(
        False,
        "--no-edit",
        help="Don't open editor after creation"
    ),
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        help="Custom config path"
    ),
):
    """
    Create new configuration file
    
    Generates a default configuration with random password.
    CAUTION: Overwrites existing config (requires --force).
    """
    from kopi_docka.helpers.config import Config, create_default_config
    
    # Check sudo for system-wide config
    if not path:
        if os.geteuid() == 0:
            utils.require_sudo("system configuration creation")
    
    utils.print_header(
        "Create New Configuration",
        "Generate fresh Kopi-Docka config"
    )
    
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
        utils.print_warning(f"⚠️  Config already exists: {existing_cfg.config_file}")
        console.print()
        
        if not force:
            console.print("[yellow]Use one of these options:[/yellow]")
            console.print("  kopi-docka config edit        - Modify existing config")
            console.print("  kopi-docka config new --force - Overwrite with warnings")
            console.print("  kopi-docka config reset       - Complete reset (DANGEROUS)")
            raise typer.Exit(1)
        
        # With --force: Show warnings
        console.print("[red]⚠️  WARNING: This will overwrite the existing configuration![/red]")
        console.print()
        console.print("This means:")
        console.print("  • A NEW password will be generated")
        console.print("  • The OLD password will NOT work anymore")
        console.print("  • You will LOSE ACCESS to existing backups!")
        console.print()
        
        if not typer.confirm("Continue anyway?", default=False):
            utils.print_warning("Aborted.")
            console.print()
            console.print("💡 Safer alternatives:")
            console.print("  kopi-docka config edit             - Edit existing config")
            console.print("  kopi-docka config change-password  - Change password safely")
            raise typer.Exit(0)
        
        # Backup old config
        from datetime import datetime
        import shutil
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = existing_cfg.config_file.parent / f"{existing_cfg.config_file.stem}.{timestamp}.backup"
        shutil.copy2(existing_cfg.config_file, backup_path)
        utils.print_success(f"✓ Old config backed up to: {backup_path}")
        console.print()
    
    # Create config
    utils.print_info("Creating new configuration...")
    created_path = create_default_config(path, force=True)
    utils.print_success(f"✓ Config created at: {created_path}")
    
    # Open in editor
    if not no_edit:
        editor = os.environ.get('EDITOR', 'nano')
        console.print()
        utils.print_info(f"Opening in {editor} for initial setup...")
        console.print("Important settings to review:")
        console.print("  • repository_path: Where to store backups")
        console.print("  • password: Default is 'kopia-docka' (change after init!)")
        console.print("  • backup paths: Adjust for your system")
        console.print()
        
        subprocess.call([editor, str(created_path)])


@app.command(name="edit")
def config_edit(
    editor: Optional[str] = typer.Option(
        None,
        "--editor",
        help="Specify editor to use (default: $EDITOR or nano)"
    ),
):
    """
    Edit existing configuration file
    
    Opens the configuration in your preferred text editor.
    """
    from kopi_docka.helpers.config import Config
    
    utils.print_header(
        "Edit Configuration",
        "Modify Kopi-Docka settings"
    )
    
    try:
        cfg = Config()
    except Exception as e:
        utils.print_error(f"Failed to load configuration: {e}")
        utils.print_info("\nCreate a new config with: kopi-docka config new")
        raise typer.Exit(1)
    
    if not editor:
        editor = os.environ.get('EDITOR', 'nano')
    
    utils.print_info(f"Opening {cfg.config_file} in {editor}...")
    subprocess.call([editor, str(cfg.config_file)])
    
    # Validate after editing
    try:
        Config(cfg.config_file)
        utils.print_success("\n✓ Configuration valid")
    except Exception as e:
        utils.print_warning(f"\n⚠️  Configuration might have issues: {e}")


@app.command(name="reset")
def config_reset(
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        help="Custom config path"
    ),
):
    """
    Reset configuration completely (DANGEROUS)
    
    Deletes existing config and creates a new one with a new password.
    Use this only if you want to start fresh or have no existing backups.
    """
    from kopi_docka.helpers.config import Config, create_default_config
    
    console.print("=" * 70)
    console.print("[red]⚠️  DANGER ZONE: CONFIGURATION RESET[/red]")
    console.print("=" * 70)
    console.print()
    console.print("This operation will:")
    console.print("  1. DELETE the existing configuration")
    console.print("  2. Generate a COMPLETELY NEW password")
    console.print("  3. Make existing backups INACCESSIBLE")
    console.print()
    console.print("✓ Only proceed if:")
    console.print("  • You want to start completely fresh")
    console.print("  • You have no existing backups")
    console.print("  • You have backed up your old password elsewhere")
    console.print()
    console.print("✗ DO NOT proceed if:")
    console.print("  • You have existing backups you want to keep")
    console.print("  • You just want to change a setting (use 'config edit' instead)")
    console.print("=" * 70)
    console.print()
    
    # First confirmation
    if not typer.confirm("Do you understand that this will make existing backups inaccessible?", default=False):
        utils.print_success("Aborted - Good choice!")
        raise typer.Exit(0)
    
    # Show what will be reset
    existing_path = path or (
        Path('/etc/kopi-docka.conf') if os.geteuid() == 0
        else Path.home() / '.config' / 'kopi-docka' / 'config.conf'
    )
    
    if existing_path.exists():
        console.print(f"\nConfig to reset: {existing_path}")
        
        # Try to show current repository path
        try:
            cfg = Config(existing_path)
            repo_path = cfg.get('kopia', 'repository_path')
            console.print(f"Current repository: {repo_path}")
            console.print()
            utils.print_warning("⚠️  If you want to KEEP this repository, you must:")
            console.print("  1. Backup your current password from the config")
            console.print("  2. Copy it to the new config after creation")
        except Exception:
            pass
    
    console.print()
    
    # Second confirmation with explicit typing
    confirmation = typer.prompt("Type 'DELETE' to confirm reset (or anything else to abort)")
    if confirmation != "DELETE":
        utils.print_warning("Aborted.")
        raise typer.Exit(0)
    
    # Backup before deletion
    if existing_path.exists():
        from datetime import datetime
        import shutil
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = existing_path.parent / f"{existing_path.stem}.{timestamp}.backup"
        shutil.copy2(existing_path, backup_path)
        utils.print_success(f"\n✓ Backup created: {backup_path}")
        
        # Also backup password file if exists
        password_file = existing_path.parent / f".{existing_path.stem}.password"
        if password_file.exists():
            password_backup = existing_path.parent / f".{existing_path.stem}.{timestamp}.password.backup"
            shutil.copy2(password_file, password_backup)
            utils.print_success(f"✓ Password backed up: {password_backup}")
    
    # Delete old config
    if existing_path.exists():
        existing_path.unlink()
        utils.print_success(f"✓ Deleted old config: {existing_path}")
    
    console.print()
    
    # Create new config
    utils.print_info("Creating fresh configuration...")
    created_path = create_default_config(path, force=True)
    utils.print_success(f"✓ New config created: {created_path}")
    
    # Open in editor
    editor = os.environ.get('EDITOR', 'nano')
    console.print()
    utils.print_info(f"Opening in {editor} for setup...")
    subprocess.call([editor, str(created_path)])


@app.command(name="change-password")
def config_change_password(
    new_password: Optional[str] = typer.Option(
        None,
        "--new-password",
        help="New password (will prompt if not provided)"
    ),
    use_file: bool = typer.Option(
        True,
        "--file/--inline",
        help="Store in external file (default) or inline in config"
    ),
):
    """
    Change Kopia repository password
    
    Safely changes the repository password and updates the configuration.
    """
    from kopi_docka.helpers.config import Config, generate_secure_password
    from kopi_docka.cores.repository_manager import KopiaRepository
    
    utils.print_header(
        "Change Repository Password",
        "Update Kopia repository credentials"
    )
    
    # Load config
    try:
        cfg = Config()
    except Exception as e:
        utils.print_error(f"Failed to load configuration: {e}")
        raise typer.Exit(1)
    
    repo = KopiaRepository(cfg)
    
    # Connect check
    try:
        if not repo.is_connected():
            utils.print_info("↻ Connecting to repository...")
            repo.connect()
    except Exception as e:
        utils.print_error(f"✗ Failed to connect: {e}")
        console.print()
        console.print("Make sure:")
        console.print("  • Repository exists and is initialized")
        console.print("  • Current password in config is correct")
        raise typer.Exit(1)
    
    console.print("=" * 70)
    console.print(f"Repository: {repo.repo_path}")
    console.print(f"Profile: {repo.profile_name}")
    console.print("=" * 70)
    console.print()
    
    # Verify current password first (security best practice)
    console.print("Verify current password:")
    current_password = getpass.getpass("Current password: ")
    
    utils.print_info("↻ Verifying current password...")
    if not repo.verify_password(current_password):
        utils.print_error("✗ Current password is incorrect!")
        console.print()
        console.print("If you've forgotten the password:")
        console.print("  • Check /etc/.kopi-docka.password")
        console.print("  • Check password_file setting in config")
        console.print("  • As last resort: reset repository (lose all backups)")
        raise typer.Exit(1)
    
    utils.print_success("✓ Current password verified")
    console.print()
    
    # Get new password
    if not new_password:
        console.print("Enter new password (empty = auto-generate):")
        new_password = getpass.getpass("New password: ")
        
        if not new_password:
            new_password = generate_secure_password()
            console.print()
            console.print("=" * 70)
            console.print("[yellow]GENERATED PASSWORD:[/yellow]")
            console.print(f"[cyan]{new_password}[/cyan]")
            console.print("=" * 70)
            console.print()
            if not typer.confirm("Use this password?"):
                utils.print_warning("Aborted.")
                raise typer.Exit(0)
        else:
            new_password_confirm = getpass.getpass("Confirm new password: ")
            if new_password != new_password_confirm:
                utils.print_error("✗ Passwords don't match!")
                raise typer.Exit(1)
    
    if len(new_password) < 12:
        console.print()
        utils.print_warning(f"⚠️  WARNING: Password is short ({len(new_password)} chars)")
        if not typer.confirm("Continue?"):
            raise typer.Exit(0)
    
    # Change in Kopia repository
    console.print()
    utils.print_info("↻ Changing repository password...")
    try:
        repo.set_repo_password(new_password)
        utils.print_success("✓ Repository password changed")
    except Exception as e:
        utils.print_error(f"✗ Error: {e}")
        raise typer.Exit(1)
    
    # Store password using Config class
    console.print()
    utils.print_info("↻ Storing new password...")
    try:
        cfg.set_password(new_password, use_file=use_file)
        
        if use_file:
            password_file = cfg.config_file.parent / f".{cfg.config_file.stem}.password"
            utils.print_success(f"✓ Password stored in: {password_file} (chmod 600)")
        else:
            utils.print_success(f"✓ Password stored in: {cfg.config_file} (chmod 600)")
    except Exception as e:
        utils.print_error(f"✗ Failed to store password: {e}")
        console.print()
        utils.print_warning("⚠️  IMPORTANT: Write down this password manually!")
        console.print(f"Password: [cyan]{new_password}[/cyan]")
        raise typer.Exit(1)
    
    console.print()
    console.print("=" * 70)
    utils.print_success("✓ PASSWORD CHANGED SUCCESSFULLY")
    console.print("=" * 70)


# Register config commands to main app
def register_to_main_app(main_app: typer.Typer):
    """Register config commands to main CLI app"""
    main_app.add_typer(app, name="config")
