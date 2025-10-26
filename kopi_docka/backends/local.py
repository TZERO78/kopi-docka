"""
Local Filesystem Backend Configuration

Store backups on local disk, NAS mount, USB drive, etc.
"""

import typer
from .base import BackendBase


class LocalBackend(BackendBase):
    """Local filesystem backend for Kopia"""
    
    @property
    def name(self) -> str:
        return "filesystem"
    
    @property
    def display_name(self) -> str:
        return "Local Filesystem"
    
    @property
    def description(self) -> str:
        return "Store backups on local disk, NAS mount, or USB drive"
    
    def configure(self) -> dict:
        """Interactive local filesystem configuration wizard."""
        typer.echo("Local filesystem storage selected.")
        typer.echo("Examples:")
        typer.echo("  • /backup/kopia-repository")
        typer.echo("  • /mnt/nas/backups")
        typer.echo("  • /media/usb-drive/kopia")
        typer.echo("")
        
        repo_path = typer.prompt("Repository path", default="/backup/kopia-repository")
        
        # Build Kopia command parameters
        kopia_params = f"filesystem --path {repo_path}"
        
        instructions = f"""
✓ Local filesystem backend configured.

Kopia command: kopia repository create {kopia_params}

Make sure:
  • Directory {repo_path} is writable
  • Has sufficient disk space
  • Is backed by reliable storage (RAID, NAS, etc.)
  
💡 For offsite backup, consider cloud storage (B2, S3, etc.)
"""
        
        return {
            'kopia_params': kopia_params,
            'instructions': instructions,
        }
