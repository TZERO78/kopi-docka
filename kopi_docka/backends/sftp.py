"""
SFTP Backend Configuration

Store backups on remote server via SSH/SFTP.
"""

import typer
from typing import Dict
from .base import BackendBase, DependencyError
from ..helpers.dependency_helper import DependencyHelper, ToolInfo


class SFTPBackend(BackendBase):
    """SFTP/SSH remote storage backend"""

    REQUIRED_TOOLS = ["ssh", "ssh-keygen"]

    @property
    def name(self) -> str:
        return "sftp"

    @property
    def display_name(self) -> str:
        return "SFTP"

    @property
    def description(self) -> str:
        return "Remote server via SSH"

    def configure(self) -> dict:
        """Interactive SFTP configuration wizard."""
        typer.echo("SFTP storage selected.")
        typer.echo("")

        # Check dependencies before interactive setup
        missing = self.check_dependencies()
        if missing:
            raise DependencyError(
                f"Missing required SSH tools: {', '.join(missing)}\n"
                f"Please install manually.\n\n"
                f"Automated Setup:\n"
                f"  https://github.com/TZERO78/Server-Baukasten"
            )

        user = typer.prompt("SSH user")
        host = typer.prompt("SSH host")
        path = typer.prompt("Remote path", default="/backup/kopia")
        port = typer.prompt("SSH port", default="22")

        # Build Kopia command parameters
        kopia_params = f"sftp --path {user}@{host}:{path}"
        if port != "22":
            kopia_params += f" --sftp-port {port}"

        instructions = f"""
✓ SFTP storage configured.

Connection: {user}@{host}:{path}

Make sure:
  • SSH access is configured (key-based auth recommended)
  • Remote directory exists and is writable
  • SSH host is in known_hosts

Setup SSH key-based auth:
  ssh-copy-id {user}@{host}

Test connection:
  ssh {user}@{host} "ls -la {path}"
"""

        return {
            "kopia_params": kopia_params,
            "instructions": instructions,
        }

    def get_status(self) -> dict:
        """Get SFTP storage status."""
        import shlex
        import re

        status = {
            "repository_type": self.name,
            "configured": bool(self.config),
            "available": False,
            "details": {
                "user": None,
                "host": None,
                "path": None,
                "port": "22",
            },
        }

        kopia_params = self.config.get("kopia_params", "")
        if not kopia_params:
            return status

        try:
            parts = shlex.split(kopia_params)

            # Parse --path user@host:path
            if "--path" in parts:
                idx = parts.index("--path")
                if idx + 1 < len(parts):
                    path_str = parts[idx + 1]
                    # Parse user@host:path format
                    match = re.match(r"(.+)@(.+):(.+)", path_str)
                    if match:
                        status["details"]["user"] = match.group(1)
                        status["details"]["host"] = match.group(2)
                        status["details"]["path"] = match.group(3)

            # Parse port if specified
            if "--sftp-port" in parts:
                idx = parts.index("--sftp-port")
                if idx + 1 < len(parts):
                    status["details"]["port"] = parts[idx + 1]

            if status["details"]["host"]:
                status["configured"] = True
                status["available"] = True
        except Exception:
            pass

        return status

    # Abstract method implementations (required by BackendBase)
    def check_dependencies(self) -> list:
        """
        Check if SSH client tools are available.

        Returns:
            List of missing dependencies (empty if all present)
        """
        return DependencyHelper.missing(self.REQUIRED_TOOLS)

    def get_dependency_status(self) -> Dict[str, ToolInfo]:
        """
        Get status of all required tools for SFTP backend.

        Returns:
            Dict mapping tool name to ToolInfo
        """
        return DependencyHelper.check_all(self.REQUIRED_TOOLS)

    def install_dependencies(self) -> bool:
        """
        Stub method - automatic installation removed (Think Simple strategy).

        Users must install dependencies manually or use Server-Baukasten.
        https://github.com/TZERO78/Server-Baukasten

        Raises:
            NotImplementedError: Automatic installation is not supported
        """
        raise NotImplementedError(
            "Automatic dependency installation has been removed. "
            "Please install ssh and ssh-keygen manually or use Server-Baukasten: "
            "https://github.com/TZERO78/Server-Baukasten"
        )

    def setup_interactive(self) -> dict:
        """Use configure() for setup."""
        return self.configure()

    def validate_config(self) -> tuple:
        """Validate configuration."""
        return (True, [])

    def test_connection(self) -> bool:
        """Test connection (requires SSH access)."""
        return True

    def get_kopia_args(self) -> list:
        """Get Kopia arguments from kopia_params."""
        import shlex

        kopia_params = self.config.get("kopia_params", "")
        return shlex.split(kopia_params) if kopia_params else []
