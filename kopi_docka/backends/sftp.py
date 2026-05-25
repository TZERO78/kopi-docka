"""
SFTP Backend Configuration

Store backups on remote server via SSH/SFTP.

Since v7.6.1 (Plan 0038) the wizard emits Kopia's canonical SFTP shape
(separate ``--path`` / ``--host`` / ``--username`` / ``--keyfile`` flags)
and persists a ``[credentials]`` block compatible with
``advanced config repair-kopia-params``.
"""

from pathlib import Path
from typing import Any, Dict, Optional

import typer
from .base import BackendBase, DependencyError, MissingCredentialsError
from ..helpers.backend_helper import (
    build_sftp_kopia_params,
    ensure_known_hosts,
)
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
        """Interactive SFTP configuration wizard.

        Builds canonical Kopia SFTP params via ``backend_helper`` and
        persists a ``[credentials]`` block so the result is repairable
        by ``advanced config repair-kopia-params`` later.
        """
        typer.echo("SFTP storage selected.")
        typer.echo("")

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

        default_key = str(Path.home() / ".ssh" / "id_ed25519")
        ssh_key = typer.prompt("SSH private key file", default=default_key)

        known_hosts_path = ensure_known_hosts(host)
        known_hosts_str = str(known_hosts_path) if known_hosts_path else ""

        kopia_params = build_sftp_kopia_params(
            remote_path=path,
            host=host,
            ssh_user=user,
            ssh_key=ssh_key,
            known_hosts=known_hosts_str or None,
            port=port,
        )

        instructions = f"""
✓ SFTP storage configured.

Connection: {user}@{host}:{path}

Make sure:
  • SSH access is configured (key-based auth recommended)
  • Remote directory exists and is writable
  • SSH host is in known_hosts

Setup SSH key-based auth:
  ssh-copy-id -i {ssh_key} {user}@{host}

Test connection:
  ssh -i {ssh_key} {user}@{host} "ls -la {path}"
"""

        return {
            "type": "sftp",
            "kopia_params": kopia_params,
            "credentials": {
                "remote_path": path,
                "host": host,
                "peer_fqdn": host,  # alias for repair-kopia-params compatibility
                "ssh_user": user,
                "ssh_key": ssh_key,
                "known_hosts": known_hosts_str,
                "port": str(port),
            },
            "instructions": instructions,
        }

    def get_status(self) -> dict:
        """Get SFTP storage status from canonical kopia_params shape."""
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

            def _flag_value(name: str) -> Optional[str]:
                """Return value for ``--flag=VALUE`` or ``--flag VALUE``."""
                for i, tok in enumerate(parts):
                    if tok.startswith(f"{name}="):
                        return tok.split("=", 1)[1]
                    if tok == name and i + 1 < len(parts):
                        return parts[i + 1]
                return None

            path_val = _flag_value("--path")
            host_val = _flag_value("--host")
            user_val = _flag_value("--username")
            port_val = _flag_value("--port")

            if path_val and host_val is None and ":" in path_val:
                # Legacy/broken shape: --path user@host:path
                m = re.match(r"(.+)@(.+):(.+)", path_val)
                if m:
                    status["details"]["user"] = m.group(1)
                    status["details"]["host"] = m.group(2)
                    status["details"]["path"] = m.group(3)
            else:
                status["details"]["user"] = user_val
                status["details"]["host"] = host_val
                status["details"]["path"] = path_val

            if port_val:
                status["details"]["port"] = port_val

            if status["details"]["host"]:
                status["configured"] = True
                status["available"] = True
        except Exception:
            pass

        return status

    def rebuild_kopia_params(
        self, credentials: Dict[str, Any]
    ) -> Optional[str]:
        """Rebuild canonical kopia_params from a [credentials] block.

        Accepts either ``host`` (new SFTP wizard) or ``peer_fqdn`` /
        ``peer_hostname`` (Tailscale-flavoured credentials, when an old
        Tailscale-shaped config gets routed through here).

        Raises:
            MissingCredentialsError: When ``remote_path``, ``host``
                (or one of its Tailscale aliases), or ``ssh_key`` is
                missing from the credentials block.
        """
        remote_path = credentials.get("remote_path", "") or ""
        host = (
            credentials.get("host")
            or credentials.get("peer_fqdn")
            or credentials.get("peer_hostname")
            or ""
        )
        ssh_user = credentials.get("ssh_user", "root") or "root"
        ssh_key = credentials.get("ssh_key", "") or ""
        known_hosts = credentials.get("known_hosts", "") or ""
        port = credentials.get("port", "") or ""

        missing = []
        if not remote_path:
            missing.append("remote_path")
        if not host:
            missing.append("host (or peer_fqdn / peer_hostname)")
        if not ssh_key:
            missing.append("ssh_key")
        if missing:
            raise MissingCredentialsError(missing)

        return build_sftp_kopia_params(
            remote_path=remote_path,
            host=host,
            ssh_user=ssh_user,
            ssh_key=ssh_key,
            known_hosts=known_hosts or None,
            port=port or None,
        )

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
