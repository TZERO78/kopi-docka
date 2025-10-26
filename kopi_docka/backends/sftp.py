"""
SFTP Backend Configuration

Store backups on remote server via SSH/SFTP.
"""

import typer
from .base import BackendBase


class SFTPBackend(BackendBase):
    """SFTP/SSH remote storage backend"""
    
    @property
    def name(self) -> str:
        return "sftp"
    
    @property
    def display_name(self) -> str:
        return "SFTP"
    
    @property
    def description(self) -> str:
        return "Remote server via SSH"
    
    def configure(self) -> dict:
        """Interactive SFTP configuration wizard."""
        typer.echo("SFTP storage selected.")
        typer.echo("")
        
        user = typer.prompt("SSH user")
        host = typer.prompt("SSH host")
        path = typer.prompt("Remote path", default="/backup/kopia")
        
        repo_path = f"sftp://{user}@{host}{path}"
        
        instructions = f"""
✓ SFTP backend configured.

Connection: {user}@{host}:{path}

Make sure:
  • SSH access is configured (key-based auth recommended)
  • Remote directory exists and is writable
  • SSH host is in known_hosts

Setup SSH key-based auth:
  ssh-copy-id {user}@{host}

Test connection:
  ssh {user}@{host} "ls -la {path}"
"""
        
        return {
            'repository_path': repo_path,
            'instructions': instructions,
        }
