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
        port = typer.prompt("SSH port", default="22")
        
        # Build Kopia command parameters
        kopia_params = f"sftp --path {user}@{host}:{path}"
        if port != "22":
            kopia_params += f" --sftp-port {port}"
        
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
            'kopia_params': kopia_params,
            'instructions': instructions,
        }


# Add abstract method implementations
SFTPBackend.check_dependencies = lambda self: []
SFTPBackend.install_dependencies = lambda self: False
SFTPBackend.setup_interactive = lambda self: self.configure()
SFTPBackend.validate_config = lambda self: (True, [])
SFTPBackend.test_connection = lambda self: True
SFTPBackend.get_kopia_args = lambda self: __import__('shlex').split(self.config.get('kopia_params', '')) if self.config.get('kopia_params') else []
