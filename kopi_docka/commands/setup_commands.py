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
2. Select backend type (local/S3/B2/Azure/GCS/Tailscale)
3. Configure backend-specific settings
4. Create config file
5. Initialize repository

This is the "one command to set everything up" experience.
"""

import shutil
from pathlib import Path
from typing import Optional

import typer

from ..helpers import get_logger, Config, create_default_config, generate_secure_password
from ..cores import DependencyManager
from ..backends.local import LocalBackend
from ..backends.s3 import S3Backend
from ..backends.b2 import B2Backend
from ..backends.azure import AzureBackend
from ..backends.gcs import GCSBackend
from ..backends.sftp import SFTPBackend
from ..backends.tailscale import TailscaleBackend

logger = get_logger(__name__)

# Backend registry - backend classes
BACKEND_MODULES = {
    'filesystem': LocalBackend,
    's3': S3Backend,
    'b2': B2Backend,
    'azure': AzureBackend,
    'gcs': GCSBackend,
    'sftp': SFTPBackend,
    'tailscale': TailscaleBackend,
}


def cmd_setup_wizard(
    force: bool = False,
    skip_deps: bool = False,
    skip_init: bool = False,
):
    """
    Complete setup wizard - guides through entire first-time setup.
    
    Steps:
    1. Check dependencies (Kopia, Docker)
    2. Select backend (local, S3, B2, etc.)
    3. Configure backend
    4. Create config file
    5. Initialize repository (optional)
    """
    import getpass
    
    typer.echo("═" * 70)
    typer.echo("🔥 Kopi-Docka Complete Setup Wizard")
    typer.echo("═" * 70)
    typer.echo("")
    typer.echo("This wizard will guide you through:")
    typer.echo("  1. ✅ Dependency verification")
    typer.echo("  2. 📦 Backend selection")
    typer.echo("  3. ⚙️  Configuration")
    typer.echo("  4. 🔐 Repository initialization")
    typer.echo("")
    
    if not typer.confirm("Continue?", default=True):
        raise typer.Exit(0)
    
    # ═══════════════════════════════════════════
    # Step 1: Dependencies
    # ═══════════════════════════════════════════
    if not skip_deps:
        typer.echo("")
        typer.echo("─" * 70)
        typer.echo("Step 1/4: Checking Dependencies")
        typer.echo("─" * 70)
        
        dep_mgr = DependencyManager()
        status = dep_mgr.check_all()
        
        if not status.get('kopia', False):
            typer.echo("\n⚠️  Kopia not found!")
            if typer.confirm("Install Kopia automatically?", default=True):
                from ..commands.dependency_commands import cmd_install_deps
                cmd_install_deps(dry_run=False, tools=['kopia'])
            else:
                typer.echo("❌ Kopia is required. Install manually:")
                typer.echo("   https://kopia.io/docs/installation/")
                raise typer.Exit(1)
        else:
            typer.echo("✓ Kopia found")
        
        if not status.get('docker', False):
            typer.echo("⚠️  Docker not found - required for backups!")
            typer.echo("Install manually: https://docs.docker.com/engine/install/")
        else:
            typer.echo("✓ Docker found")
    
    # ═══════════════════════════════════════════
    # Step 2-3: Configuration (Backend + Password)
    # ═══════════════════════════════════════════
    typer.echo("")
    typer.echo("─" * 70)
    typer.echo("Step 2/4: Configuration Setup")
    typer.echo("─" * 70)
    typer.echo("")
    
    # Use cmd_new_config for configuration - DRY!
    from ..commands.config_commands import cmd_new_config
    cfg = cmd_new_config(force=force, edit=False)
    
    kopia_params = cfg.get('kopia', 'kopia_params')
    
    # ═══════════════════════════════════════════
    # Step 4: Repository Init (Optional)
    # ═══════════════════════════════════════════
    if not skip_init:
        typer.echo("")
        typer.echo("─" * 70)
        typer.echo("Step 4/4: Repository Initialization")
        typer.echo("─" * 70)
        typer.echo("")
        
        if typer.confirm("Initialize repository now?", default=True):
            typer.echo("")
            typer.echo("Initializing repository...")
            from ..commands.repository_commands import cmd_init
            try:
                # Create mock context
                import types
                ctx = types.SimpleNamespace()
                ctx.obj = {"config": cfg}
                cmd_init(ctx)
                typer.echo("✓ Repository initialized!")
            except Exception as e:
                typer.echo(f"⚠️  Repository initialization failed: {e}")
                typer.echo("You can initialize later with: kopi-docka init")
        else:
            typer.echo("Skipped repository initialization")
    
    # ═══════════════════════════════════════════
    # Success Summary
    # ═══════════════════════════════════════════
    typer.echo("")
    typer.echo("═" * 70)
    typer.echo("✅ Setup Complete!")
    typer.echo("═" * 70)
    typer.echo("")
    typer.echo("What's configured:")
    typer.echo(f"  • Kopia params: {kopia_params}")
    typer.echo(f"  • Config:       {cfg.config_file}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  1. List Docker containers:")
    typer.echo("     sudo kopi-docka list --units")
    typer.echo("")
    typer.echo("  2. Test backup (dry-run):")
    typer.echo("     sudo kopi-docka dry-run")
    typer.echo("")
    typer.echo("  3. Create first backup:")
    typer.echo("     sudo kopi-docka backup")
    typer.echo("")


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
