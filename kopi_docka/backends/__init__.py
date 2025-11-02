"""
Backend Factory and Registry

Central registry for all storage backend implementations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Type

from .base import BackendBase, BackendError, DependencyError, ConfigurationError, ConnectionError

# Backend registry (will be populated as backends are implemented)
_BACKEND_REGISTRY: Dict[str, Type[BackendBase]] = {}


def register_backend(backend_class: Type[BackendBase]) -> Type[BackendBase]:
    """
    Register a backend implementation.
    
    Args:
        backend_class: Backend class to register
    
    Returns:
        The backend class (for decorator usage)
    
    Usage:
        @register_backend
        class FilesystemBackend(BackendBase):
            ...
    """
    # Instantiate temporarily to get name
    temp_instance = backend_class({})
    _BACKEND_REGISTRY[temp_instance.name] = backend_class
    return backend_class


def get_backend_class(backend_type: str) -> Type[BackendBase]:
    """
    Get backend class by type.
    
    Args:
        backend_type: Backend type name (e.g., 'filesystem', 'tailscale')
    
    Returns:
        Backend class
    
    Raises:
        ValueError: If backend type not found
    """
    if backend_type not in _BACKEND_REGISTRY:
        available = ', '.join(sorted(_BACKEND_REGISTRY.keys()))
        raise ValueError(
            f"Unknown backend type: {backend_type}. "
            f"Available backends: {available}"
        )
    return _BACKEND_REGISTRY[backend_type]


def create_backend(backend_type: str, config: Dict[str, Any]) -> BackendBase:
    """
    Create backend instance.
    
    Args:
        backend_type: Backend type name
        config: Backend configuration
    
    Returns:
        Backend instance
    
    Raises:
        ValueError: If backend type not found
    """
    backend_class = get_backend_class(backend_type)
    return backend_class(config)


def list_available_backends() -> List[str]:
    """
    List all registered backend types.
    
    Returns:
        List of backend type names
    """
    return sorted(_BACKEND_REGISTRY.keys())


def get_backend_info(backend_type: str) -> Dict[str, str]:
    """
    Get backend information.
    
    Args:
        backend_type: Backend type name
    
    Returns:
        Dictionary with backend info (name, display_name, description)
    
    Raises:
        ValueError: If backend type not found
    """
    backend_class = get_backend_class(backend_type)
    # Create temporary instance to get properties
    temp = backend_class({})
    return {
        "name": temp.name,
        "display_name": temp.display_name,
        "description": temp.description,
    }


# Alias for direct registry access
BACKENDS = _BACKEND_REGISTRY

# Export public API
__all__ = [
    "BackendBase",
    "BackendError",
    "DependencyError",
    "ConfigurationError",
    "ConnectionError",
    "register_backend",
    "get_backend_class",
    "create_backend",
    "list_available_backends",
    "get_backend_info",
    "BACKENDS",
]


# Auto-import all backend implementations
# This ensures they are registered when the module is imported
def _import_backends():
    """Import all backend implementations to trigger registration"""
    try:
        from . import local  # noqa: F401
    except ImportError:
        pass
    
    try:
        from . import s3  # noqa: F401
    except ImportError:
        pass
    
    try:
        from . import b2  # noqa: F401
    except ImportError:
        pass
    
    try:
        from . import azure  # noqa: F401
    except ImportError:
        pass
    
    try:
        from . import gcs  # noqa: F401
    except ImportError:
        pass
    
    try:
        from . import sftp  # noqa: F401
    except ImportError:
        pass
    
    try:
        from . import rclone  # noqa: F401
    except ImportError:
        pass
    
    try:
        from . import tailscale  # noqa: F401
    except ImportError:
        pass


# Import backends on module load
_import_backends()
