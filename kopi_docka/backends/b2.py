"""
Backblaze B2 Backend Configuration

Cost-effective cloud storage with S3-compatible API.
"""

import typer


def configure() -> dict:
    """
    Interactive Backblaze B2 configuration wizard.
    
    Returns:
        dict with repository_path, env_vars, instructions
    """
    typer.echo("Backblaze B2 cloud storage selected.")
    typer.echo("")
    typer.echo("You'll need:")
    typer.echo("  • B2 Application Key ID")
    typer.echo("  • B2 Application Key")
    typer.echo("  • Bucket name")
    typer.echo("")
    typer.echo("Get credentials: https://secure.backblaze.com/app_keys.htm")
    typer.echo("")
    
    bucket = typer.prompt("Bucket name")
    prefix = typer.prompt("Path prefix (optional)", default="kopia", show_default=True)
    
    repo_path = f"b2://{bucket}/{prefix}" if prefix else f"b2://{bucket}"
    
    env_vars = {
        'B2_APPLICATION_KEY_ID': '<your-application-key-id>',
        'B2_APPLICATION_KEY': '<your-application-key>',
    }
    
    instructions = f"""
⚠️  Set these environment variables before running init:

  export B2_APPLICATION_KEY_ID='your-key-id'
  export B2_APPLICATION_KEY='your-application-key'

To set permanently (add to /etc/environment or ~/.bashrc):
  echo 'B2_APPLICATION_KEY_ID=your-key' | sudo tee -a /etc/environment
  echo 'B2_APPLICATION_KEY=your-secret' | sudo tee -a /etc/environment

Get credentials from:
  https://secure.backblaze.com/app_keys.htm

💡 B2 is cost-effective:
  • $0.005/GB/month storage
  • Free egress up to 3x storage
  • No API request fees
"""
    
    return {
        'repository_path': repo_path,
        'env_vars': env_vars,
        'instructions': instructions,
    }
