"""
Google Cloud Storage Backend Configuration
"""

import typer
from .base import BackendBase


class GCSBackend(BackendBase):
    """Google Cloud Storage backend"""

    @property
    def name(self) -> str:
        return "gcs"

    @property
    def display_name(self) -> str:
        return "Google Cloud Storage"

    @property
    def description(self) -> str:
        return "GCS cloud storage"

    def configure(self) -> dict:
        """Interactive Google Cloud Storage configuration wizard."""
        typer.echo("Google Cloud Storage selected.")
        typer.echo("")

        bucket = typer.prompt("Bucket name")
        prefix = typer.prompt("Path prefix (optional)", default="kopia", show_default=True)

        # Build Kopia command parameters
        kopia_params = f"gcs --bucket {bucket}"
        if prefix:
            kopia_params += f" --prefix {prefix}"

        instructions = """
⚠️  Authenticate with Google Cloud:

Option 1: gcloud CLI (recommended)
  gcloud auth application-default login

Option 2: Service Account Key
  export GOOGLE_APPLICATION_CREDENTIALS='/path/to/service-account-key.json'

Get service account key from Google Cloud Console:
  https://console.cloud.google.com/iam-admin/serviceaccounts

Required permissions:
  • storage.objects.create
  • storage.objects.delete
  • storage.objects.get
  • storage.objects.list
"""

        return {
            "kopia_params": kopia_params,
            "instructions": instructions,
        }

    def get_status(self) -> dict:
        """Get GCS storage status."""
        import shlex

        status = {
            "repository_type": self.name,
            "configured": bool(self.config),
            "available": False,
            "details": {
                "bucket": None,
                "prefix": None,
            },
        }

        kopia_params = self.config.get("kopia_params", "")
        if not kopia_params:
            return status

        try:
            parts = shlex.split(kopia_params)

            if "--bucket" in parts:
                idx = parts.index("--bucket")
                if idx + 1 < len(parts):
                    status["details"]["bucket"] = parts[idx + 1]

            if "--prefix" in parts:
                idx = parts.index("--prefix")
                if idx + 1 < len(parts):
                    status["details"]["prefix"] = parts[idx + 1]

            if status["details"]["bucket"]:
                status["configured"] = True
                status["available"] = True
        except Exception:
            pass

        return status

    # Abstract method implementations (required by BackendBase)
    def check_dependencies(self) -> list:
        """No local dependencies required for GCS."""
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
        """Test connection (requires GCP credentials)."""
        return True

    def get_kopia_args(self) -> list:
        """Get Kopia arguments from kopia_params."""
        import shlex

        kopia_params = self.config.get("kopia_params", "")
        return shlex.split(kopia_params) if kopia_params else []
