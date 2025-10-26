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
from ..backends import local, s3, b2, azure, gcs, sftp, tailscale

logger = get_logger(__name__)

# Backend module registry
BACKEND_MODULES = {
    'filesystem': local,
    's3': s3,
    'b2': b2,
    'azure': azure,
    'gcs': gcs,
    'sftp': sftp,
    'tailscale': tailscale,
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
        
        if not status['kopia']['installed']:
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
        
        if not status['docker']['installed']:
            typer.echo("⚠️  Docker not found - required for backups!")
            typer.echo("Install manually: https://docs.docker.com/engine/install/")
        else:
            typer.echo("✓ Docker found")
    
    # ═══════════════════════════════════════════
    # Step 2: Backend Selection
    # ═══════════════════════════════════════════
    typer.echo("")
    typer.echo("─" * 70)
    typer.echo("Step 2/4: Backend Selection")
    typer.echo("─" * 70)
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
    
    # ═══════════════════════════════════════════
    # Step 3: Backend Configuration
    # ═══════════════════════════════════════════
    typer.echo("")
    typer.echo("─" * 70)
    typer.echo("Step 3/4: Backend Configuration")
    typer.echo("─" * 70)
    typer.echo("")
    
    # Use backend module for configuration
    backend_module = BACKEND_MODULES.get(backend_type)
    
    if backend_module:
        # Call module's configure() function
        result = backend_module.configure()
        repo_path = result['repository_path']
        
        # Show setup instructions if provided
        if 'instructions' in result:
            typer.echo("")
            typer.echo(result['instructions'])
    else:
        # Fallback for unknown backends
        typer.echo(f"⚠️  Backend '{backend_type}' not found")
        typer.echo("Using manual configuration...")
        repo_path = typer.prompt("Repository path")
    
    # ═══════════════════════════════════════════
    # Password Setup
    # ═══════════════════════════════════════════
    typer.echo("")
    typer.echo("─" * 70)
    typer.echo("Repository Encryption Password")
    typer.echo("─" * 70)
    typer.echo("")
    typer.echo("This password encrypts your backups.")
    typer.echo("⚠️  If you lose this password, backups are UNRECOVERABLE!")
    typer.echo("")
    
    use_generated = typer.confirm("Generate secure random password?", default=True)
    typer.echo("")
    
    if use_generated:
        password = generate_secure_password()
        typer.echo("═" * 70)
        typer.echo("🔑 GENERATED PASSWORD (save this NOW!):")
        typer.echo("")
        typer.echo(f"   {password}")
        typer.echo("")
        typer.echo("═" * 70)
        typer.echo("")
        input("Press Enter to continue...")
    else:
        password = getpass.getpass("Enter password: ")
        password_confirm = getpass.getpass("Confirm password: ")
        
        if password != password_confirm:
            typer.echo("❌ Passwords don't match!")
            raise typer.Exit(1)
    
    # ═══════════════════════════════════════════
    # Create Config
    # ═══════════════════════════════════════════
    typer.echo("")
    typer.echo("─" * 70)
    typer.echo("Creating Configuration")
    typer.echo("─" * 70)
    
    config_path = create_default_config(force=force)
    cfg = Config(config_path)
    cfg.set('kopia', 'repository_path', repo_path)
    cfg.set_password(password, use_file=True)
    
    typer.echo(f"✓ Config created: {config_path}")
    password_file = config_path.parent / f".{config_path.stem}.password"
    typer.echo(f"✓ Password saved: {password_file}")
    
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
    typer.echo(f"  • Backend:    {backend_type}")
    typer.echo(f"  • Repository: {repo_path}")
    typer.echo(f"  • Config:     {config_path}")
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
