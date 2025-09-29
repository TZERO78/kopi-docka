"""
Configuration management for Kopi-Docka.

This module handles reading, writing, and validating configuration files,
as well as creating default configurations when needed.
"""

import configparser
import logging
import secrets
import string
from pathlib import Path
from typing import Optional, Dict, Any
import os

from .constants import DEFAULT_CONFIG_PATHS, DEFAULT_BACKUP_BASE


logger = logging.getLogger(__name__)


class Config:
    """
    Manages application configuration.
    
    This class handles loading configuration from INI files, providing
    default values, and validating settings.
    
    Attributes:
        config_file: Path to the configuration file
        _config: ConfigParser instance
        _defaults: Default configuration values
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Optional path to configuration file.
                        If not provided, searches standard locations.
        """
        self._defaults = self._get_defaults()
        self._config = configparser.ConfigParser()
        
        # Find or create configuration file
        self.config_file = self._find_config_file(config_path)
        if not self.config_file.exists():
            logger.info(f"Creating default configuration at {self.config_file}")
            create_default_config(self.config_file)
        
        self._load_config()
    
    def _get_defaults(self) -> Dict[str, Dict[str, Any]]:
        """
        Get default configuration values.
        
        Returns:
            Dictionary of default configuration sections and values
        """
        return {
            'kopia': {
                'repository_path': '/backup/kopia-repository',
                'password': generate_secure_password(),
                'compression': 'zstd',
                'encryption': 'AES256-GCM-HMAC-SHA256',
                'cache_directory': '/var/cache/kopi-docka'
            },
            'backup': {
                'base_path': DEFAULT_BACKUP_BASE,
                'parallel_workers': 'auto',
                'stop_timeout': 30,
                'start_timeout': 60,
                'database_backup': 'true'
            },
            'docker': {
                'socket': '/var/run/docker.sock',
                'compose_timeout': 300,
                'prune_stopped_containers': 'false'
            },
            'logging': {
                'level': 'INFO',
                'file': '/var/log/kopi-docka.log',
                'max_size_mb': 100,
                'backup_count': 5
            }
        }
    
    def _find_config_file(self, config_path: Optional[Path] = None) -> Path:
        """
        Find or determine configuration file path.
        
        Args:
            config_path: Explicitly provided configuration path
            
        Returns:
            Path to configuration file
        """
        if config_path and config_path.exists():
            return config_path
        
        # Check standard locations
        if os.geteuid() == 0:  # Running as root
            return DEFAULT_CONFIG_PATHS['root']
        else:
            path = DEFAULT_CONFIG_PATHS['user']
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
    
    def _load_config(self):
        """Load configuration from file."""
        try:
            self._config.read(self.config_file)
            logger.info(f"Configuration loaded from {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def get(self, section: str, option: str, fallback: Any = None) -> Any:
        """
        Get configuration value.
        
        Args:
            section: Configuration section
            option: Configuration option
            fallback: Fallback value if not found
            
        Returns:
            Configuration value or fallback
        """
        try:
            return self._config.get(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            # Try to get from defaults
            if section in self._defaults and option in self._defaults[section]:
                return self._defaults[section][option]
            return fallback
    
    def getint(self, section: str, option: str, fallback: int = 0) -> int:
        """
        Get integer configuration value.
        
        Args:
            section: Configuration section
            option: Configuration option
            fallback: Fallback value if not found
            
        Returns:
            Integer configuration value or fallback
        """
        value = self.get(section, option, fallback)
        if isinstance(value, str):
            if value.lower() == 'auto':
                return -1  # Special value for auto
            try:
                return int(value)
            except ValueError:
                return fallback
        return int(value)
    
    def getboolean(self, section: str, option: str, fallback: bool = False) -> bool:
        """
        Get boolean configuration value.
        
        Args:
            section: Configuration section
            option: Configuration option
            fallback: Fallback value if not found
            
        Returns:
            Boolean configuration value or fallback
        """
        value = self.get(section, option, str(fallback))
        if isinstance(value, bool):
            return value
        return value.lower() in ('true', 'yes', '1', 'on')
    
    def getlist(self, section: str, option: str, fallback: list = None) -> list:
        """
        Get list configuration value (comma-separated).
        
        Args:
            section: Configuration section
            option: Configuration option
            fallback: Fallback value if not found
            
        Returns:
            List of configuration values or fallback
        """
        value = self.get(section, option)
        if value:
            return [item.strip() for item in value.split(',')]
        return fallback or []
    
    def set(self, section: str, option: str, value: Any):
        """
        Set configuration value.
        
        Args:
            section: Configuration section
            option: Configuration option
            value: Value to set
        """
        if not self._config.has_section(section):
            self._config.add_section(section)
        self._config.set(section, option, str(value))
    
    def save(self):
        """Save configuration to file."""
        with open(self.config_file, 'w') as f:
            self._config.write(f)
        logger.info(f"Configuration saved to {self.config_file}")
    
    def display(self):
        """Display current configuration (with sensitive values masked)."""
        print(f"Configuration file: {self.config_file}")
        print("=" * 60)
        
        for section in self._config.sections():
            print(f"\n[{section}]")
            for option, value in self._config.items(section):
                # Mask sensitive values
                if 'password' in option.lower() or 'token' in option.lower():
                    value = '***MASKED***'
                print(f"  {option} = {value}")
    
    @property
    def kopia_repository_path(self) -> Path:
        """Get Kopia repository path."""
        return Path(self.get('kopia', 'repository_path'))
    
    @property
    def kopia_password(self) -> str:
        """Get Kopia password."""
        return self.get('kopia', 'password')
    
    @property
    def backup_base_path(self) -> Path:
        """Get backup base path."""
        return Path(self.get('backup', 'base_path'))
    
    @property
    def parallel_workers(self) -> int:
        """Get number of parallel workers."""
        workers = self.getint('backup', 'parallel_workers', -1)
        if workers == -1:  # auto
            from .system_utils import SystemUtils
            return SystemUtils().get_optimal_workers()
        return workers
    
    @property
    def docker_socket(self) -> str:
        """Get Docker socket path."""
        return self.get('docker', 'socket', '/var/run/docker.sock')


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
    Create default configuration file.
    
    Args:
        path: Path where to create config file
        force: Overwrite existing file if True
    """
    if path is None:
        if os.geteuid() == 0:
            path = DEFAULT_CONFIG_PATHS['root']
        else:
            path = DEFAULT_CONFIG_PATHS['user']
    
    if path.exists() and not force:
        logger.warning(f"Configuration file already exists at {path}")
        return
    
    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Copy template
    template_path = Path(__file__).parent.parent / 'config.template.ini'
    if template_path.exists():
        import shutil
        shutil.copy(template_path, path)
    else:
        # Generate from defaults
        config = Config(path)
        config.save()
    
    # Set secure permissions
    path.chmod(0o600)
    logger.info(f"Default configuration created at {path}")