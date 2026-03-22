"""
Storage Backend Module

Provides backend classes for different storage types (filesystem, cloud, etc.).
Each backend handles setup configuration and status display.

Note: Backend registration is handled by BACKEND_MODULES in config_commands.py,
not by a registry pattern here. This keeps the code simple and explicit.
"""

from .base import BackendBase, BackendError, DependencyError, ConfigurationError, ConnectionError


def get_backend_class(backend_type: str):
    """Get backend class by type name."""
    from .local import LocalBackend
    from .s3 import S3Backend
    from .b2 import B2Backend
    from .azure import AzureBackend
    from .gcs import GCSBackend
    from .sftp import SFTPBackend
    from .tailscale import TailscaleBackend
    from .rclone import RcloneBackend

    BACKEND_REGISTRY = {
        "filesystem": LocalBackend,
        "s3": S3Backend,
        "b2": B2Backend,
        "azure": AzureBackend,
        "gcs": GCSBackend,
        "sftp": SFTPBackend,
        "tailscale": TailscaleBackend,
        "rclone": RcloneBackend,
    }
    return BACKEND_REGISTRY.get(backend_type)


# Export public API
__all__ = [
    "BackendBase",
    "BackendError",
    "DependencyError",
    "ConfigurationError",
    "ConnectionError",
    "get_backend_class",
]
