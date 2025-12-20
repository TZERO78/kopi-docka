"""
Storage Backend Module

Provides backend classes for different storage types (filesystem, cloud, etc.).
Each backend handles setup configuration and status display.

Note: Backend registration is handled by BACKEND_MODULES in config_commands.py,
not by a registry pattern here. This keeps the code simple and explicit.
"""

from .base import BackendBase, BackendError, DependencyError, ConfigurationError, ConnectionError

# Export public API
__all__ = [
    "BackendBase",
    "BackendError",
    "DependencyError",
    "ConfigurationError",
    "ConnectionError",
]
