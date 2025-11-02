#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        rclone.py
# @module:      kopi_docka.backends
# @description: Rclone backend implementation for Kopia
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Rclone backend for Kopia.

Uses Kopia's built-in rclone support to connect to any cloud storage
that rclone supports (OneDrive, Dropbox, Google Drive, etc.).
"""

from pathlib import Path
from typing import Dict

import typer

from .base import BackendBase
from . import register_backend


@register_backend
class RcloneBackend(BackendBase):
    """
    Rclone backend implementation.
    
    Leverages Kopia's native rclone support to connect to any
    cloud storage provider supported by rclone.
    """

    @property
    def name(self) -> str:
        return "rclone"

    @property
    def display_name(self) -> str:
        return "Rclone (Universal Cloud Storage)"

    @property
    def description(self) -> str:
        return "Use rclone to connect to any cloud storage (OneDrive, Dropbox, Google Drive, etc.)"

    def configure(self) -> dict:
        """
        Configure Rclone backend.
        
        Returns:
            Configuration dictionary with kopia_params
        """
        typer.echo("=" * 60)
        typer.echo("Rclone Backend Configuration")
        typer.echo("=" * 60)
        typer.echo("")
        typer.echo("Prerequisites:")
        typer.echo("  1. Rclone must be installed: https://rclone.org/install/")
        typer.echo("  2. Configure your remote: rclone config")
        typer.echo("  3. Test connection: rclone ls <remote>:")
        typer.echo("")
        
        # Get rclone remote name
        remote = typer.prompt(
            "Rclone remote name (from 'rclone config')",
            type=str
        ).strip()
        
        if not remote:
            raise ValueError("Remote name cannot be empty")
        
        # Get remote path
        remote_path = typer.prompt(
            "Remote path (e.g., 'backups/kopia')",
            default="kopia-backup",
            type=str
        ).strip()
        
        # Optional: Rclone config file location
        typer.echo("")
        typer.echo("Rclone config file location (optional):")
        typer.echo(f"  Default: {Path.home() / '.config/rclone/rclone.conf'}")
        
        use_custom_config = typer.confirm(
            "Use custom rclone config file location?",
            default=False
        )
        
        rclone_config = ""
        if use_custom_config:
            config_path = typer.prompt(
                "Rclone config file path",
                type=str
            ).strip()
            rclone_config = str(Path(config_path).expanduser())
        
        # Build kopia_params
        full_remote_path = f"{remote}:{remote_path}"
        kopia_params = f"rclone --remote-path={full_remote_path}"
        
        # Add rclone config if specified
        if rclone_config:
            kopia_params += f" --rclone-config={rclone_config}"
        
        # Build instructions
        instructions = f"""
Rclone Backend Setup Complete
{'=' * 60}

Remote Configuration:
  Remote Name: {remote}
  Remote Path: {remote_path}
  Full Path:   {full_remote_path}

Next Steps:
  1. Verify rclone connection:
     rclone ls {remote}:
  
  2. Initialize repository:
     sudo kopi-docka init
  
  3. Test connection:
     rclone tree {remote}:{remote_path}

Rclone Commands:
  - List files:    rclone ls {remote}:
  - Check config:  rclone config show {remote}
  - Test speed:    rclone test speed {remote}:

Documentation:
  - Rclone docs: https://rclone.org/docs/
  - Kopia rclone: https://kopia.io/docs/repositories/#rclone
"""
        
        typer.echo("")
        typer.echo("=" * 60)
        typer.echo("Configuration Summary")
        typer.echo("=" * 60)
        typer.echo(f"Remote:      {remote}")
        typer.echo(f"Path:        {remote_path}")
        typer.echo(f"Full Path:   {full_remote_path}")
        if rclone_config:
            typer.echo(f"Config File: {rclone_config}")
        typer.echo("")
        
        return {
            'kopia_params': kopia_params,
            'instructions': instructions
        }
    
    # Abstract method implementations (required by BackendBase)
    # These are stubs since the new architecture uses configure() instead
    
    def check_dependencies(self) -> list:
        """Check if rclone is installed."""
        import shutil
        missing = []
        if not shutil.which("rclone"):
            missing.append("rclone")
        return missing
    
    def install_dependencies(self) -> bool:
        """Rclone must be installed manually."""
        return False
    
    def setup_interactive(self) -> dict:
        """Use configure() instead."""
        return self.configure()
    
    def validate_config(self) -> tuple:
        """Validate configuration."""
        return (True, [])
    
    def test_connection(self) -> bool:
        """Test connection (not implemented)."""
        return True
    
    def get_kopia_args(self) -> list:
        """Get Kopia arguments from kopia_params."""
        import shlex
        kopia_params = self.config.get('kopia_params', '')
        return shlex.split(kopia_params) if kopia_params else []
