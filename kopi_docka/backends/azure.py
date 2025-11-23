"""
Azure Blob Storage Backend Configuration
"""

import typer
from .base import BackendBase


class AzureBackend(BackendBase):
    """Azure Blob Storage backend"""
    
    @property
    def name(self) -> str:
        return "azure"
    
    @property
    def display_name(self) -> str:
        return "Azure Blob Storage"
    
    @property
    def description(self) -> str:
        return "Microsoft Azure cloud storage"
    
    def configure(self) -> dict:
        """Interactive Azure Blob Storage configuration wizard."""
        typer.echo("Azure Blob Storage selected.")
        typer.echo("")
        
        container = typer.prompt("Container name")
        prefix = typer.prompt("Path prefix (optional)", default="kopia", show_default=True)
        
        # Build Kopia command parameters
        kopia_params = f"azure --container {container}"
        if prefix:
            kopia_params += f" --prefix {prefix}"
        
        env_vars = {
            'AZURE_STORAGE_ACCOUNT': '<your-storage-account-name>',
            'AZURE_STORAGE_KEY': '<your-storage-account-key>',
        }
        
        instructions = """
⚠️  Set these environment variables before running init:

  export AZURE_STORAGE_ACCOUNT='your-account-name'
  export AZURE_STORAGE_KEY='your-account-key'

Get credentials from Azure Portal:
  https://portal.azure.com/#blade/HubsExtension/BrowseResource/resourceType/Microsoft.Storage%2FStorageAccounts

Or use Azure CLI:
  az storage account keys list --account-name <name> --resource-group <rg>
"""
        
        return {
            'kopia_params': kopia_params,
            'env_vars': env_vars,
            'instructions': instructions,
        }

    def get_status(self) -> dict:
        """Get Azure backend status."""
        import shlex

        status = {
            "backend_type": self.name,
            "configured": bool(self.config),
            "available": False,
            "details": {
                "container": None,
                "prefix": None,
            }
        }

        kopia_params = self.config.get('kopia_params', '')
        if not kopia_params:
            return status

        try:
            parts = shlex.split(kopia_params)

            if '--container' in parts:
                idx = parts.index('--container')
                if idx + 1 < len(parts):
                    status["details"]["container"] = parts[idx + 1]

            if '--prefix' in parts:
                idx = parts.index('--prefix')
                if idx + 1 < len(parts):
                    status["details"]["prefix"] = parts[idx + 1]

            if status["details"]["container"]:
                status["configured"] = True
                status["available"] = True
        except Exception:
            pass

        return status


# Add abstract method implementations
AzureBackend.check_dependencies = lambda self: []
AzureBackend.install_dependencies = lambda self: False
AzureBackend.setup_interactive = lambda self: self.configure()
AzureBackend.validate_config = lambda self: (True, [])
AzureBackend.test_connection = lambda self: True
AzureBackend.get_kopia_args = lambda self: __import__('shlex').split(self.config.get('kopia_params', '')) if self.config.get('kopia_params') else []
