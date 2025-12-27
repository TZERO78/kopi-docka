"""
Local Filesystem Backend Configuration

Store backups on local disk, NAS mount, USB drive, etc.
"""

import typer
from .base import BackendBase


class LocalBackend(BackendBase):
    """Local filesystem backend for Kopia"""

    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def display_name(self) -> str:
        return "Local Filesystem"

    @property
    def description(self) -> str:
        return "Store backups on local disk, NAS mount, or USB drive"

    def configure(self) -> dict:
        """Interactive local filesystem configuration wizard."""
        typer.echo("Local filesystem storage selected.")
        typer.echo("Examples:")
        typer.echo("  • /backup/kopia-repository")
        typer.echo("  • /mnt/nas/backups")
        typer.echo("  • /media/usb-drive/kopia")
        typer.echo("")

        repo_path = typer.prompt("Repository path", default="/backup/kopia-repository")

        # Build Kopia command parameters
        kopia_params = f"filesystem --path {repo_path}"

        instructions = f"""
✓ Local filesystem storage configured.

Kopia command: kopia repository create {kopia_params}

Make sure:
  • Directory {repo_path} is writable
  • Has sufficient disk space
  • Is backed by reliable storage (RAID, NAS, etc.)
  
💡 For offsite backup, consider cloud storage (B2, S3, etc.)
"""

        return {
            "kopia_params": kopia_params,
            "instructions": instructions,
        }

    # Abstract method implementations (required by BackendBase)
    def check_dependencies(self) -> list:
        """Check dependencies."""
        return []

    def install_dependencies(self) -> bool:
        """Install dependencies (not implemented)."""
        return False

    def setup_interactive(self) -> dict:
        """Use configure() instead."""
        return self.configure()

    def validate_config(self) -> tuple:
        """Validate configuration."""
        return (True, [])

    def test_connection(self) -> bool:
        """Test connection (not implemented)."""
        return True

    def get_kopia_args(self) -> list:
        """Get Kopia arguments from kopia_params."""
        import shlex

        kopia_params = self.config.get("kopia_params", "")
        return shlex.split(kopia_params) if kopia_params else []

    def get_status(self) -> dict:
        """Get filesystem storage status including disk space."""
        import shutil
        import os
        from pathlib import Path

        status = {
            "repository_type": self.name,
            "configured": bool(self.config),
            "available": False,
            "details": {
                "path": None,
                "exists": False,
                "writable": False,
                "disk_free_gb": None,
                "disk_total_gb": None,
            },
        }

        # Extract path from kopia_params
        kopia_params = self.config.get("kopia_params", "")
        if not kopia_params:
            return status

        # Parse path from "filesystem --path /backup/kopia-repository"
        import shlex

        try:
            parts = shlex.split(kopia_params)
            if "--path" in parts:
                idx = parts.index("--path")
                if idx + 1 < len(parts):
                    path = Path(parts[idx + 1])
                    status["details"]["path"] = str(path)

                    # Check if path exists
                    status["details"]["exists"] = path.exists()

                    # Check if writable
                    if path.exists():
                        status["details"]["writable"] = os.access(path, os.W_OK)
                        status["available"] = status["details"]["writable"]

                        # Get disk space
                        try:
                            disk_usage = shutil.disk_usage(path)
                            status["details"]["disk_total_gb"] = disk_usage.total / (1024**3)
                            status["details"]["disk_free_gb"] = disk_usage.free / (1024**3)
                        except Exception:
                            pass
                    elif path.parent.exists():
                        # Path doesn't exist yet, but parent does - check parent
                        status["details"]["writable"] = os.access(path.parent, os.W_OK)
                        status["available"] = status["details"]["writable"]

                        try:
                            disk_usage = shutil.disk_usage(path.parent)
                            status["details"]["disk_total_gb"] = disk_usage.total / (1024**3)
                            status["details"]["disk_free_gb"] = disk_usage.free / (1024**3)
                        except Exception:
                            pass

        except Exception:
            pass

        return status
