"""
SFTP Backend Configuration
"""

import typer
from pathlib import Path


def configure() -> dict:
    """Interactive SFTP configuration wizard."""
    typer.echo("SFTP storage selected.")
    typer.echo("")
    
    user = typer.prompt("SSH user", default="root")
    host = typer.prompt("SSH host (IP or hostname)")
    port = typer.prompt("SSH port", default=22, show_default=True)
    path = typer.prompt("Remote path", default="/backup/kopia")
    
    # SSH key setup
    ssh_key = Path.home() / ".ssh" / "id_rsa"
    use_key = typer.confirm(f"Use SSH key authentication? (key: {ssh_key})", default=True)
    
    if use_key:
        custom_key = typer.prompt(
            "SSH key path (press Enter for default)",
            default=str(ssh_key),
            show_default=False
        )
        ssh_key = Path(custom_key)
        
        if not ssh_key.exists():
            typer.echo(f"⚠️  SSH key not found: {ssh_key}")
            typer.echo("Generate with: ssh-keygen -t ed25519")
            typer.echo(f"Copy to server: ssh-copy-id {user}@{host}")
    
    # Build repository path
    if port != 22:
        repo_path = f"sftp://{user}@{host}:{port}{path}"
    else:
        repo_path = f"sftp://{user}@{host}{path}"
    
    instructions = f"""
⚠️  SFTP Setup Required:

1. Ensure SSH access is configured:
   ssh {user}@{host}

2. For key-based authentication (recommended):
   ssh-keygen -t ed25519 -f ~/.ssh/id_rsa
   ssh-copy-id -i ~/.ssh/id_rsa {user}@{host}

3. Test connection:
   ssh {user}@{host} "mkdir -p {path}"

4. For password authentication:
   You'll be prompted during repository initialization

💡 SSH key authentication is more secure and doesn't require
   password entry for each backup.
"""
    
    result = {
        'repository_path': repo_path,
        'instructions': instructions,
        'ssh_user': user,
        'ssh_host': host,
        'ssh_port': port,
        'remote_path': path,
    }
    
    if use_key and ssh_key.exists():
        result['ssh_key'] = str(ssh_key)
    
    return result
