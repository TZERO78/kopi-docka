"""Configuration management commands."""

import os
import subprocess
import configparser
from pathlib import Path
from typing import Optional

import typer

from ..helpers import Config, create_default_config, get_logger

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

    typer.echo(f"Configuration file: {cfg.config_file}")
    typer.echo("=" * 60)

    config = configparser.ConfigParser()
    config.read(cfg.config_file)

    for section in config.sections():
        typer.echo(f"\n[{section}]")
        for option, value in config.items(section):
            if 'password' in option.lower() or 'token' in option.lower():
                value = '***MASKED***'
            typer.echo(f"  {option} = {value}")


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

    if existing_cfg and existing_cfg.config_file.exists() and not force:
        typer.echo(f"⚠️ Config already exists at: {existing_cfg.config_file}")
        typer.echo("Use --force to overwrite or 'edit-config' to modify")
        raise typer.Exit(code=1)

    typer.echo("Creating new configuration...")
    created_path = create_default_config(path, force)
    typer.echo(f"✓ Config created at: {created_path}")

    if edit:
        editor = os.environ.get('EDITOR', 'nano')
        typer.echo(f"\nOpening in {editor} for initial setup...")
        typer.echo("Important settings to configure:")
        typer.echo("  • repository_path - Where to store backups")
        typer.echo("  • password - Strong password for encryption")
        typer.echo("  • backup paths - Adjust for your system")
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
        typer.echo(f"⚠️ Configuration might have issues: {e}")


# -------------------------
# Registration
# -------------------------

def register(app: typer.Typer):
    """Register all configuration commands."""
    
    app.command("config")(
        lambda ctx: cmd_config(
            ctx,
            show=typer.Option(True, "--show", help="Show current configuration")
        )
    )
    
    app.command("new-config")(
        lambda force=typer.Option(False, "--force", "-f", help="Overwrite existing config"),
               edit=typer.Option(True, "--edit/--no-edit", help="Open in editor after creation"),
               path=typer.Option(None, "--path", "-p", help="Custom config path"): 
            cmd_new_config(force, edit, path)
    )
    
    app.command("edit-config")(
        lambda ctx, editor=typer.Option(None, "--editor", "-e", help="Specify editor to use"):
            cmd_edit_config(ctx, editor)
    )