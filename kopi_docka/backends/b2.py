"""
Backblaze B2 Backend Configuration

Cost-effective cloud storage with S3-compatible API.
"""

import typer
from .base import BackendBase


class B2Backend(BackendBase):
    """Backblaze B2 cloud storage backend"""
    
    @property
    def name(self) -> str:
        return "b2"
    
    @property
    def display_name(self) -> str:
        return "Backblaze B2"
    
    @property
    def description(self) -> str:
        return "Cost-effective cloud storage"
    
    def configure(self) -> dict:
        """Interactive Backblaze B2 configuration wizard."""
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
        
        # Build Kopia command parameters
        kopia_params = f"b2 --bucket {bucket}"
        if prefix:
            kopia_params += f" --prefix {prefix}"
        
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
            'kopia_params': kopia_params,
            'env_vars': env_vars,
            'instructions': instructions,
        }

    def get_status(self) -> dict:
        """Get B2 backend status."""
        import shlex

        status = {
            "backend_type": self.name,
            "configured": bool(self.config),
            "available": False,
            "details": {
                "bucket": None,
                "prefix": None,
            }
        }

        kopia_params = self.config.get('kopia_params', '')
        if not kopia_params:
            return status

        try:
            parts = shlex.split(kopia_params)

            if '--bucket' in parts:
                idx = parts.index('--bucket')
                if idx + 1 < len(parts):
                    status["details"]["bucket"] = parts[idx + 1]

            if '--prefix' in parts:
                idx = parts.index('--prefix')
                if idx + 1 < len(parts):
                    status["details"]["prefix"] = parts[idx + 1]

            if status["details"]["bucket"]:
                status["configured"] = True
                status["available"] = True
        except Exception:
            pass

        return status


# Add abstract method implementations
B2Backend.check_dependencies = lambda self: []
B2Backend.install_dependencies = lambda self: False
B2Backend.setup_interactive = lambda self: self.configure()
B2Backend.validate_config = lambda self: (True, [])
B2Backend.test_connection = lambda self: True
B2Backend.get_kopia_args = lambda self: __import__('shlex').split(self.config.get('kopia_params', '')) if self.config.get('kopia_params') else []
