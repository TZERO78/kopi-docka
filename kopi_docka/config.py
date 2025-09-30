"""
Configuration management for Kopia-Docka.

This module handles reading, writing, and validating configuration files,
as well as creating default configurations when needed.
"""

import configparser
import logging
import secrets
import string
from pathlib import Path
from typing import Optional, Dict, Any, List
import os
import sys

from .constants import DEFAULT_CONFIG_PATHS

logger = logging.getLogger(__name__)


def generate_secure_password(length: int = 32) -> str:
    """
    Generate a cryptographically secure password.
    
    Args:
        length: Password length
        
    Returns:
        Secure random password
    """
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def create_default_config(path: Optional[Path] = None, force: bool = False):
    """
    Create a default configuration file from the template.
    
    Args:
        path: Optional path where to create the config file. If None, uses default.
        force: Overwrite existing file if True.
    """
    # Handle None path - determine default location
    if path is None:
        if os.geteuid() == 0:
            path = Path('/etc/kopi-docka.conf')
        else:
            path = Path.home() / '.config' / 'kopi-docka' / 'config.conf'
    else:
        path = Path(path).expanduser()
    
    # Now safe to check exists
    if path.exists() and not force:
        logger.warning(f"Configuration file already exists at {path}, not overwriting.")
        return
    
    # Ensure the parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Find the template file
    template_path = Path(__file__).parent / 'config-template.ini'
    
    if not template_path.exists():
        # Fallback: Try alternative name
        template_path = Path(__file__).parent / 'config_template.ini'
        
    if not template_path.exists():
        logger.error(
            f"Configuration template not found. Creating minimal config."
        )
        # Create minimal config without template
        minimal_config = f"""# Kopi-Docka Configuration
[kopia]
repository_path = /backup/kopia-repository
password = {generate_secure_password()}
cache_directory = /var/cache/kopi-docka

[backup]
base_path = /backup/kopi-docka
parallel_workers = auto
stop_timeout = 30
database_backup = true

[docker]
socket = /var/run/docker.sock
"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(minimal_config)
    else:
        # Read template and replace password
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Replace password placeholder if exists
        if 'CHANGE_ME' in template_content:
            password = generate_secure_password()
            config_content = template_content.replace('CHANGE_ME_TO_A_SECURE_PASSWORD', password)
        else:
            config_content = template_content
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(config_content)
    
    # Set secure permissions (readable only by owner)
    path.chmod(0o600)
    logger.info(f"Default configuration created at {path}")
    
    return path  # Return path for caller


class Config:
    """
    Manages application configuration.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration.
        """
        self._config = configparser.ConfigParser(interpolation=None)
        
        self.config_file = self._find_config_file(config_path)
        if not self.config_file.exists():
            logger.info(f"No configuration found. Creating default at {self.config_file}")
            create_default_config(self.config_file)
        
        self._load_config()
        self._ensure_required_values()

    @staticmethod
    def _get_defaults() -> Dict[str, Dict[str, Any]]:
        """
        Get default configuration values for a root-based installation.
        """
        return {
            'kopia': {
                'repository_path': '/var/lib/kopi-docka/repository',
                'password': 'SHOULD_BE_REPLACED',
                'cache_directory': '/var/cache/kopi-docka'
            },
            'backup': {
                'parallel_workers': 'auto',
                'stop_timeout': 30,
            },
            'docker': {
                'socket_path': '/var/run/docker.sock',
            },
            'logging': {
                'level': 'INFO',
                'log_file': '/var/log/kopi-docka.log',
            }
        }
        
    def _find_config_file(self, config_path: Optional[Path] = None) -> Path:
        """Find the configuration file."""
        if config_path:
            return Path(config_path).expanduser()
        
        # This tool is intended to run as root, so we primarily check root locations.
        if os.geteuid() == 0: 
            return Path(DEFAULT_CONFIG_PATHS["root"])
        else:
            # Fallback for user-based development, but warn the user.
            logger.warning("Running as non-root. Using user-specific config path.")
            user_path = Path(DEFAULT_CONFIG_PATHS["user"]).expanduser()
            user_path.parent.mkdir(parents=True, exist_ok=True)
            return user_path
            
    def _load_config(self):
        """Load configuration from the file."""
        try:
            self._config.read(self.config_file)
            logger.debug(f"Configuration loaded from {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    def _ensure_required_values(self):
        """Ensure critical configuration values are present."""
        if not self.get('kopia', 'password'):
            raise ValueError("Kopia password is not set.")
        if not self.get('kopia', 'repository_path'):
            raise ValueError("Kopia repository path is not set.")
    
    def get(self, section: str, option: str, fallback: Any = None) -> Any:
        """Get a configuration value."""
        value = self._config.get(section, option, fallback=None)
        if value is not None:
            return value
        
        defaults = self._get_defaults()
        if section in defaults and option in defaults[section]:
            return defaults[section][option]
        
        return fallback

    def getint(self, section: str, option: str, fallback: int = 0) -> int:
        """Get an integer configuration value."""
        value = self.get(section, option, str(fallback))
        if isinstance(value, str) and value.lower() == 'auto':
            return -1
        try:
            return int(value)
        except (ValueError, TypeError):
            return fallback

    def getboolean(self, section: str, option: str, fallback: bool = False) -> bool:
        """Get a boolean configuration value."""
        value = self.get(section, option, str(fallback))
        if isinstance(value, bool):
            return value
        return str(value).lower() in ('true', 'yes', '1', 'on')

    # --- Properties for easy access ---

    @property
    def kopia_repository_path(self) -> Path:
        return Path(self.get('kopia', 'repository_path')).expanduser()

    @property
    def kopia_password(self) -> str:
        return self.get('kopia', 'password')
        
    @property
    def kopia_cache_directory(self) -> Path:
        return Path(self.get('kopia', 'cache_directory')).expanduser()

    @property
    def log_file(self) -> Path:
        return Path(self.get('logging', 'log_file')).expanduser()

    @property
    def parallel_workers(self) -> int:
        workers = self.getint('backup', 'parallel_workers', -1)
        if workers == -1:
            from .system_utils import get_optimal_workers
            return get_optimal_workers()
        return workers

    @property
    def docker_socket(self) -> str:
        return self.get('docker', 'socket_path')