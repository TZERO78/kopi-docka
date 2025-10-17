"""
Configuration Manager for Kopi-Docka v2

Handles JSON-based configuration storage and retrieval.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import socket


class ConfigError(Exception):
    """Configuration-related errors"""
    pass


def get_config_dir() -> Path:
    """Get configuration directory path"""
    # Use XDG_CONFIG_HOME if set, otherwise ~/.config
    config_home = os.getenv("XDG_CONFIG_HOME")
    if config_home:
        config_dir = Path(config_home) / "kopi-docka"
    else:
        config_dir = Path.home() / ".config" / "kopi-docka"
    
    # Create if doesn't exist
    config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    
    return config_dir


def get_config_path() -> Path:
    """Get main backend configuration file path"""
    return get_config_dir() / "backend.json"


def save_backend_config(backend_type: str, backend_config: Dict[str, Any]) -> Path:
    """
    Save backend configuration to JSON file
    
    Args:
        backend_type: Type of backend (tailscale, filesystem, rclone)
        backend_config: Backend configuration dictionary
        
    Returns:
        Path to saved config file
        
    Raises:
        ConfigError: If save fails
    """
    config_path = get_config_path()
    
    # Build full config structure
    config = {
        "version": "2.1",
        "backend_type": backend_type,
        "backend_config": backend_config,
        "repository": {
            "initialized": False,
            "created_at": None,
            "last_check": None
        },
        "metadata": {
            "created_by": "kopi-docka-v2",
            "created_at": datetime.now().isoformat(),
            "hostname": socket.gethostname(),
            "os": os.uname().sysname if hasattr(os, 'uname') else "Unknown"
        }
    }
    
    try:
        # Write with secure permissions
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # Ensure secure permissions
        config_path.chmod(0o600)
        
        return config_path
        
    except Exception as e:
        raise ConfigError(f"Failed to save configuration: {e}")


def load_backend_config() -> Optional[Dict[str, Any]]:
    """
    Load backend configuration from JSON file
    
    Returns:
        Configuration dictionary or None if not found
        
    Raises:
        ConfigError: If config exists but is invalid
    """
    config_path = get_config_path()
    
    if not config_path.exists():
        return None
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Validate structure
        required_keys = ["version", "backend_type", "backend_config"]
        for key in required_keys:
            if key not in config:
                raise ConfigError(f"Invalid config: missing '{key}'")
        
        return config
        
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in config file: {e}")
    except Exception as e:
        raise ConfigError(f"Failed to load configuration: {e}")


def update_repository_status(
    initialized: bool = False,
    created_at: Optional[str] = None,
    last_check: Optional[str] = None
) -> None:
    """
    Update repository status in config
    
    Args:
        initialized: Whether repository is initialized
        created_at: ISO timestamp of creation
        last_check: ISO timestamp of last check
        
    Raises:
        ConfigError: If config doesn't exist or update fails
    """
    config = load_backend_config()
    
    if config is None:
        raise ConfigError("No configuration found. Run setup first.")
    
    # Update repository status
    if "repository" not in config:
        config["repository"] = {}
    
    config["repository"]["initialized"] = initialized
    
    if created_at:
        config["repository"]["created_at"] = created_at
    
    if last_check:
        config["repository"]["last_check"] = last_check
    
    if initialized and created_at is None:
        # Auto-set created_at if marking as initialized
        config["repository"]["created_at"] = datetime.now().isoformat()
    
    # Save updated config
    config_path = get_config_path()
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        config_path.chmod(0o600)
        
    except Exception as e:
        raise ConfigError(f"Failed to update repository status: {e}")


def is_repository_initialized() -> bool:
    """
    Check if repository is initialized
    
    Returns:
        True if initialized, False otherwise
    """
    config = load_backend_config()
    
    if config is None:
        return False
    
    return config.get("repository", {}).get("initialized", False)


def get_backend_type() -> Optional[str]:
    """
    Get configured backend type
    
    Returns:
        Backend type string or None
    """
    config = load_backend_config()
    
    if config is None:
        return None
    
    return config.get("backend_type")


def delete_config() -> bool:
    """
    Delete configuration file
    
    Returns:
        True if deleted, False if didn't exist
    """
    config_path = get_config_path()
    
    if config_path.exists():
        config_path.unlink()
        return True
    
    return False
