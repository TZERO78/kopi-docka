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
        
        repo_path = f"azure://{container}/{prefix}" if prefix else f"azure://{container}"
        
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
            'repository_path': repo_path,
            'env_vars': env_vars,
            'instructions': instructions,
        }
