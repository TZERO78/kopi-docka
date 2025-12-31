"""
Abstract Base Class for Storage Backends

Defines the interface that all backend implementations must follow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple



class BackendBase(ABC):
    """
    Abstract base class for all storage backends.

    Each backend implementation must:
    1. Check/install dependencies
    2. Provide interactive setup wizard
    3. Validate configuration
    4. Test connectivity
    5. Generate Kopia CLI arguments
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize backend with configuration.

        Args:
            config: Backend-specific configuration dictionary (optional for setup)
        """
        self.config = config or {}

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name (e.g., 'filesystem', 'tailscale', 'rclone')"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable backend name (translatable)"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Backend description (translatable)"""
        pass

    @abstractmethod
    def check_dependencies(self) -> List[str]:
        """
        Check for missing system dependencies.

        Returns:
            List of missing dependency names (empty if all satisfied)

        Example:
            return ["rclone", "tailscale"]  # Missing
            return []  # All satisfied
        """
        pass

    @abstractmethod
    def install_dependencies(self) -> bool:
        """
        Auto-install missing dependencies (with user approval).

        Returns:
            True if successful, False otherwise

        Note:
            Should handle OS detection (Debian, Ubuntu, Arch, etc.)
            and use appropriate package manager.
        """
        pass

    @abstractmethod
    def setup_interactive(self) -> Dict[str, Any]:
        """
        Interactive setup wizard for this backend.

        Should guide the user through:
        - Selecting/configuring remote
        - Setting up credentials
        - Choosing paths
        - Testing connection

        Returns:
            Configuration dictionary ready for KopiDockaConfig.backend

        Example return:
            {
                "type": "tailscale",
                "kopia_params": "sftp --path=backup-nas.tailnet:/backup/kopia --host=backup-nas.tailnet",
                "credentials": {
                    "ssh_key": "~/.ssh/kopi-docka_ed25519",
                    "ssh_user": "root"
                }
            }
        """
        pass

    @abstractmethod
    def validate_config(self) -> Tuple[bool, List[str]]:
        """
        Validate backend configuration.

        Returns:
            Tuple of (is_valid, error_messages)

        Example:
            return (True, [])  # Valid
            return (False, ["SSH key not found", "Invalid path"])
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test backend connectivity.

        Returns:
            True if connection successful, False otherwise

        Note:
            Should test actual connectivity (e.g., SSH ping, S3 bucket access)
            without modifying any data.
        """
        pass

    @abstractmethod
    def get_kopia_args(self) -> List[str]:
        """
        Generate Kopia CLI arguments for repository create/connect.

        Returns:
            List of Kopia CLI arguments

        Example for filesystem:
            ["--path", "/backup/kopia-repository"]

        Example for rclone:
            ["--remote-path", "remote:path", "--embed-rclone-config", "/path/to/rclone.conf"]

        Example for S3:
            ["--bucket", "my-bucket", "--prefix", "kopia/", "--access-key", "...", "--secret-access-key", "..."]
        """
        pass

    # Optional helper methods (can be overridden)

    def get_backend_type(self) -> str:
        """Get Kopia backend type (e.g., 'filesystem', 'rclone', 's3')"""
        return self.name

    def get_env_vars(self) -> Dict[str, str]:
        """
        Get environment variables for Kopia CLI.

        Returns:
            Dictionary of environment variables

        Example:
            {"AWS_ACCESS_KEY_ID": "...", "AWS_SECRET_ACCESS_KEY": "..."}
        """
        return {}

    def post_setup(self) -> None:
        """
        Optional post-setup actions after repository creation.

        Can be used for:
        - Configuring SSH keys
        - Setting up rclone config
        - Validating credentials
        """
        pass

    def get_recovery_instructions(self) -> str:
        """
        Get backend-specific recovery instructions for DR bundles.

        Returns:
            Markdown-formatted instructions
        """
        return f"""
## {self.display_name} Recovery

1. Install required dependencies: {', '.join(self.check_dependencies()) or 'None'}
2. Restore credentials from the recovery bundle
3. Test connection: kopia repository status
4. Proceed with data restore
"""

    def get_status(self) -> dict:
        """
        Get detailed status information about the configured storage.

        This method can be overridden by backend implementations to provide
        storage-specific status information (e.g., disk space, connectivity).

        Returns:
            dict: Status information with at least these keys:
                - repository_type: str (name of the storage type)
                - configured: bool (whether storage is configured)
                - available: bool (whether storage is accessible)
                - details: dict (storage-specific details)

        Example return for filesystem storage:
            {
                "repository_type": "filesystem",
                "configured": True,
                "available": True,
                "details": {
                    "path": "/backup/kopia",
                    "disk_free_gb": 450.5,
                    "disk_total_gb": 1000.0,
                    "writable": True
                }
            }
        """
        # Default implementation - just check if configured
        status = {
            "repository_type": self.name,
            "configured": bool(self.config),
            "available": False,
            "details": {},
        }

        # Try to test connection
        try:
            status["available"] = self.test_connection()
        except Exception:
            pass

        return status

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name})>"


class BackendError(Exception):
    """Base exception for backend errors"""

    pass


class DependencyError(BackendError):
    """Raised when dependencies are missing or cannot be installed"""

    pass


class ConfigurationError(BackendError):
    """Raised when configuration is invalid"""

    pass


class ConnectionError(BackendError):
    """Raised when connection test fails"""

    pass
