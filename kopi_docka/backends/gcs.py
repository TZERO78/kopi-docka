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
            'kopia_params': kopia_params,
            'instructions': instructions,
        }

    def get_status(self) -> dict:
        """Get GCS backend status."""
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
GCSBackend.check_dependencies = lambda self: []
GCSBackend.install_dependencies = lambda self: False
GCSBackend.setup_interactive = lambda self: self.configure()
GCSBackend.validate_config = lambda self: (True, [])
GCSBackend.test_connection = lambda self: True
GCSBackend.get_kopia_args = lambda self: __import__('shlex').split(self.config.get('kopia_params', '')) if self.config.get('kopia_params') else []
