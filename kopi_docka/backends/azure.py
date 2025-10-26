"""
Azure Blob Storage Backend Configuration
"""

import typer


def configure() -> dict:
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
