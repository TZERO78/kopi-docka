################################################################################
# KOPI-DOCKA
#
# @file:        config_commands.py
# @module:      kopi_docka.commands.advanced
# @description: Configuration management commands (admin config subgroup)
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.4.1
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Configuration management commands under 'admin config'.

Commands:
- admin config show   - Show current configuration
- admin config edit   - Edit configuration file
- admin config new    - Create new configuration
- admin config reset  - Reset configuration (DANGEROUS)
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

import typer

# Note: From advanced/ we need ...helpers (go up two levels)
from ...helpers import Config, create_default_config, get_logger, generate_secure_password
from ...backends.local import LocalBackend
from ...backends.s3 import S3Backend
from ...backends.b2 import B2Backend
from ...backends.azure import AzureBackend
from ...backends.gcs import GCSBackend
from ...backends.sftp import SFTPBackend
from ...backends.tailscale import TailscaleBackend
from ...backends.rclone import RcloneBackend

logger = get_logger(__name__)

# Backend registry
BACKEND_MODULES = {
    'filesystem': LocalBackend,
    's3': S3Backend,
    'b2': B2Backend,
    'azure': AzureBackend,
    'gcs': GCSBackend,
    'sftp': SFTPBackend,
    'tailscale': TailscaleBackend,
    'rclone': RcloneBackend,
}

# Create config subcommand group
config_app = typer.Typer(
    name="config",
    help="Configuration management commands.",
    no_args_is_help=True,
)


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


def ensure_config(ctx: typer.Context) -> Config:
    """Ensure config exists or exit."""
    cfg = get_config(ctx)
    if not cfg:
        typer.echo("No configuration found")
        typer.echo("Run: kopi-docka admin config new")
        raise typer.Exit(code=1)
    return cfg


# -------------------------
# Commands
# -------------------------

def cmd_config_show(ctx: typer.Context):
    """Show current configuration."""
    cfg = ensure_config(ctx)
    cfg.display()


def cmd_config_new(
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
        pass

    if existing_cfg and existing_cfg.config_file.exists():
        typer.echo(f"Config already exists at: {existing_cfg.config_file}")
        typer.echo("")

        if not force:
            typer.echo("Use one of these options:")
            typer.echo("  kopi-docka admin config edit  - Modify existing config")
            typer.echo("  kopi-docka admin config new --force - Overwrite with warnings")
            typer.echo("  kopi-docka admin config reset - Complete reset (DANGEROUS)")
            raise typer.Exit(code=1)

        # With --force: Show warnings
        typer.echo("WARNING: This will overwrite the existing configuration!")
        typer.echo("")
        typer.echo("This means:")
        typer.echo("  - A NEW password will be generated")
        typer.echo("  - The OLD password will NOT work anymore")
        typer.echo("  - You will LOSE ACCESS to existing backups!")
        typer.echo("")

        if not typer.confirm("Continue anyway?", default=False):
            typer.echo("Aborted.")
            typer.echo("")
            typer.echo("Safer alternatives:")
            typer.echo("  kopi-docka admin config edit   - Edit existing config")
            typer.echo("  kopi-docka admin repo change-password - Change repository password safely")
            raise typer.Exit(code=0)

        # Backup old config
        from datetime import datetime
        import shutil
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        timestamp_backup = existing_cfg.config_file.parent / f"{existing_cfg.config_file.stem}.{timestamp}.backup"
        shutil.copy2(existing_cfg.config_file, timestamp_backup)
        typer.echo(f"Old config backed up to: {timestamp_backup}")
        typer.echo("")

    # Create base config with template
    typer.echo("Kopi-Docka Setup Wizard")
    typer.echo("-" * 40)
    typer.echo("")

    created_path = create_default_config(path, force=True)
    cfg = Config(created_path)

    # Phase 1: Backend Selection & Configuration
    typer.echo("Backend Selection")
    typer.echo("-" * 40)
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
    typer.echo("  8. Rclone           - Universal (70+ cloud providers)")
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
        8: "rclone",
    }

    backend_type = backend_map.get(backend_choice, "filesystem")
    typer.echo(f"\nSelected: {backend_type}")
    typer.echo("")

    # Use backend class for configuration
    backend_class = BACKEND_MODULES.get(backend_type)

    if backend_class:
        backend = backend_class({})
        result = backend.configure()
        kopia_params = result.get('kopia_params', '')

        if 'instructions' in result:
            typer.echo("")
            typer.echo(result['instructions'])
    else:
        typer.echo(f"Backend '{backend_type}' not found")
        repo_path = typer.prompt("Repository path", default="/backup/kopia-repository")
        kopia_params = f"filesystem --path {repo_path}"

    cfg.set('kopia', 'kopia_params', kopia_params)
    typer.echo("")

    # Phase 2: Password Setup
    typer.echo("Repository Encryption Password")
    typer.echo("-" * 40)
    typer.echo("")
    typer.echo("This password encrypts your backups.")
    typer.echo("If you lose this password, backups are UNRECOVERABLE!")
    typer.echo("")

    use_generated = typer.confirm("Generate secure random password?", default=True)
    typer.echo("")

    if use_generated:
        password = generate_secure_password()
        typer.echo("=" * 60)
        typer.echo("GENERATED PASSWORD (save this NOW!):")
        typer.echo("")
        typer.echo(f"   {password}")
        typer.echo("")
        typer.echo("=" * 60)
        typer.echo("Copy this to:")
        typer.echo("   - Password manager (recommended)")
        typer.echo("   - Encrypted USB drive")
        typer.echo("   - Secure physical location")
        typer.echo("=" * 60)
        typer.echo("")
        input("Press Enter to continue...")
    else:
        password = getpass.getpass("Enter password: ")
        password_confirm = getpass.getpass("Confirm password: ")

        if password != password_confirm:
            typer.echo("Passwords don't match!")
            raise typer.Exit(1)

        if len(password) < 12:
            typer.echo(f"\nWARNING: Password is short ({len(password)} chars)")
            typer.echo("Recommended: At least 12 characters")
            if not typer.confirm("Continue with this password?", default=False):
                typer.echo("Aborted.")
                raise typer.Exit(0)

    # Save password to config
    cfg.set_password(password, use_file=True)
    typer.echo("")

    # Phase 3: Summary & Next Steps
    typer.echo("Configuration Created Successfully")
    typer.echo("-" * 40)
    typer.echo("")
    typer.echo(f"Config file:    {cfg.config_file}")
    password_file = cfg.config_file.parent / f".{cfg.config_file.stem}.password"
    typer.echo(f"Password file:  {password_file}")
    typer.echo(f"Kopia params:   {kopia_params}")
    typer.echo("")

    typer.echo("Setup Complete! Next Steps:")
    typer.echo("")
    typer.echo("1. Initialize repository:")
    typer.echo("   sudo kopi-docka admin repo init")
    typer.echo("")
    typer.echo("2. List Docker containers:")
    typer.echo("   sudo kopi-docka admin snapshot list --units")
    typer.echo("")
    typer.echo("3. Test backup (dry-run):")
    typer.echo("   sudo kopi-docka dry-run")
    typer.echo("")
    typer.echo("4. Create first backup:")
    typer.echo("   sudo kopi-docka backup")
    typer.echo("")

    # Optional: Open in editor for advanced settings
    if edit:
        if typer.confirm("Open config in editor for advanced settings?", default=False):
            editor = os.environ.get('EDITOR', 'nano')
            typer.echo(f"\nOpening in {editor}...")
            typer.echo("Advanced settings you can adjust:")
            typer.echo("  - compression: zstd, s2, pgzip")
            typer.echo("  - encryption: AES256-GCM-HMAC-SHA256, etc.")
            typer.echo("  - parallel_workers: auto, or specific number")
            typer.echo("  - retention: daily/weekly/monthly/yearly")
            typer.echo("")
            subprocess.call([editor, str(created_path)])

    return cfg


def cmd_config_edit(ctx: typer.Context, editor: Optional[str] = None):
    """Edit existing configuration file."""
    cfg = ensure_config(ctx)

    if not editor:
        editor = os.environ.get('EDITOR', 'nano')

    typer.echo(f"Opening {cfg.config_file} in {editor}...")
    subprocess.call([editor, str(cfg.config_file)])

    # Validate after editing
    try:
        Config(cfg.config_file)
        typer.echo("Configuration valid")
    except Exception as e:
        typer.echo(f"Configuration might have issues: {e}")


def cmd_config_reset(path: Optional[Path] = None):
    """
    Reset configuration completely (DANGEROUS).

    This will delete the existing config and create a new one with a new password.
    """
    typer.echo("=" * 70)
    typer.echo("DANGER ZONE: CONFIGURATION RESET")
    typer.echo("=" * 70)
    typer.echo("")
    typer.echo("This operation will:")
    typer.echo("  1. DELETE the existing configuration")
    typer.echo("  2. Generate a COMPLETELY NEW password")
    typer.echo("  3. Make existing backups INACCESSIBLE")
    typer.echo("")
    typer.echo("Only proceed if:")
    typer.echo("  - You want to start completely fresh")
    typer.echo("  - You have no existing backups")
    typer.echo("  - You have backed up your old password elsewhere")
    typer.echo("")
    typer.echo("DO NOT proceed if:")
    typer.echo("  - You have existing backups you want to keep")
    typer.echo("  - You just want to change a setting (use 'admin config edit' instead)")
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

        try:
            cfg = Config(existing_path)
            kopia_params = cfg.get('kopia', 'kopia_params', fallback='')

            if kopia_params:
                typer.echo(f"Current kopia_params: {kopia_params}")
            else:
                typer.echo("No repository configured")
            typer.echo("")
            typer.echo("If you want to KEEP this repository, you must:")
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
        typer.echo(f"\nBackup created: {backup_path}")

        # Also backup password file if exists
        password_file = existing_path.parent / f".{existing_path.stem}.password"
        if password_file.exists():
            password_backup = existing_path.parent / f".{existing_path.stem}.{timestamp}.password.backup"
            shutil.copy2(password_file, password_backup)
            typer.echo(f"Password backed up: {password_backup}")

    # Delete old config
    if existing_path.exists():
        existing_path.unlink()
        typer.echo(f"Deleted old config: {existing_path}")

    typer.echo("")

    # Create new config
    typer.echo("Creating fresh configuration...")
    cmd_config_new(force=True, edit=True, path=path)


# -------------------------
# Registration
# -------------------------

def register(app: typer.Typer):
    """Register configuration commands under 'admin config'."""

    @config_app.command("show")
    def _config_show_cmd(ctx: typer.Context):
        """Show current configuration."""
        cmd_config_show(ctx)

    @config_app.command("new")
    def _config_new_cmd(
        force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config (with warnings)"),
        edit: bool = typer.Option(True, "--edit/--no-edit", help="Open in editor after creation"),
        path: Optional[Path] = typer.Option(None, "--path", help="Custom config path"),
    ):
        """Create new configuration file."""
        cmd_config_new(force, edit, path)

    @config_app.command("edit")
    def _config_edit_cmd(
        ctx: typer.Context,
        editor: Optional[str] = typer.Option(None, "--editor", help="Specify editor to use"),
    ):
        """Edit existing configuration file."""
        cmd_config_edit(ctx, editor)

    @config_app.command("reset")
    def _config_reset_cmd(
        path: Optional[Path] = typer.Option(None, "--path", help="Custom config path"),
    ):
        """Reset configuration completely (DANGEROUS - creates new password!)."""
        cmd_config_reset(path)

    # Add config subgroup to admin app
    app.add_typer(config_app, name="config", help="Configuration management commands")
