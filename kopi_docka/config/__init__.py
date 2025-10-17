"""
Configuration Management for Kopi-Docka v2

Handles backend configuration storage and repository status.
"""

from .manager import (
    save_backend_config,
    load_backend_config,
    get_config_path,
    is_repository_initialized,
    update_repository_status,
    delete_config,
    ConfigError,
)

__all__ = [
    "save_backend_config",
    "load_backend_config",
    "get_config_path",
    "is_repository_initialized",
    "update_repository_status",
    "delete_config",
    "ConfigError",
]
