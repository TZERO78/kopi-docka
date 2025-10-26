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
