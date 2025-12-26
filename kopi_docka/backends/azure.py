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
            "AZURE_STORAGE_ACCOUNT": "<your-storage-account-name>",
            "AZURE_STORAGE_KEY": "<your-storage-account-key>",
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
            "kopia_params": kopia_params,
            "env_vars": env_vars,
            "instructions": instructions,
        }

    def get_status(self) -> dict:
        """Get Azure storage status."""
        import shlex

        status = {
            "repository_type": self.name,
            "configured": bool(self.config),
            "available": False,
            "details": {
                "container": None,
                "prefix": None,
            },
        }

        kopia_params = self.config.get("kopia_params", "")
        if not kopia_params:
            return status

        try:
            parts = shlex.split(kopia_params)

            if "--container" in parts:
                idx = parts.index("--container")
                if idx + 1 < len(parts):
                    status["details"]["container"] = parts[idx + 1]

            if "--prefix" in parts:
                idx = parts.index("--prefix")
                if idx + 1 < len(parts):
                    status["details"]["prefix"] = parts[idx + 1]

            if status["details"]["container"]:
                status["configured"] = True
                status["available"] = True
        except Exception:
            pass

        return status

    # Abstract method implementations (required by BackendBase)
    def check_dependencies(self) -> list:
        """No local dependencies required for Azure."""
        return []

    def install_dependencies(self) -> bool:
        """No dependencies to install."""
        return True

    def setup_interactive(self) -> dict:
        """Use configure() for setup."""
        return self.configure()

    def validate_config(self) -> tuple:
        """Validate configuration."""
        return (True, [])

    def test_connection(self) -> bool:
        """Test connection (requires Azure credentials in environment)."""
        return True

    def get_kopia_args(self) -> list:
        """Get Kopia arguments from kopia_params."""
        import shlex

        kopia_params = self.config.get("kopia_params", "")
        return shlex.split(kopia_params) if kopia_params else []
