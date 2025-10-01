"""Configuration management commands."""

import os
import subprocess
from pathlib import Path
from typing import Optional

import typer

from ..helpers import Config, create_default_config, get_logger, generate_secure_password

logger = get_logger(__name__)


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
):
    """Create new configuration file."""
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

    typer.echo("Creating new configuration...")
    created_path = create_default_config(path, force=True)
    typer.echo(f"✓ Config created at: {created_path}")

    if edit:
        editor = os.environ.get('EDITOR', 'nano')
        typer.echo(f"\nOpening in {editor} for initial setup...")
        typer.echo("Important settings to review:")
        typer.echo("  • repository_path: Where to store backups")
        typer.echo("  • password: Default is 'kopia-docka' (change after init!)")
        typer.echo("  • backup paths: Adjust for your system")
        typer.echo("")
        subprocess.call([editor, str(created_path)])


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
            repo_path = cfg.get('kopia', 'repository_path')
            typer.echo(f"Current repository: {repo_path}")
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


# -------------------------
# Registration
# -------------------------

def register(app: typer.Typer):
    """Register all configuration commands."""
    
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