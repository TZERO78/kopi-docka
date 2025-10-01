################################################################################
# KOPI-DOCKA
#
# @file:        config.py
# @module:      kopi_docka.config
# @description: Configuration management with template support
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Configuration management for Kopi-Docka.

This module handles reading, writing, and validating configuration files,
as well as creating default configurations when needed.
"""

import configparser
import logging
import secrets
import shutil 
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


def create_default_config(path: Optional[Path] = None, force: bool = False) -> Path:
    """
    Create a default configuration file from the template.
    
    Args:
        path: Optional path where to create the config file. If None, uses default.
        force: Overwrite existing file if True.
        
    Returns:
        Path to the created config file
    """
    from datetime import datetime
    
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
        return path
    
    # Ensure the parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Find the template file - direct path
    template_name = 'config-template.conf'
    template_path = Path(__file__).parent.parent / "templates" / template_name
    
    if not template_path.exists():
        raise FileNotFoundError(
            f"Configuration template not found at {template_path}. "
            f"This indicates a broken installation. "
            f"Please reinstall kopi-docka or check package data."
        )
    
    # Read template and replace password
    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()
    
    generated_password = None
    
    # Replace password placeholder if exists
    if 'CHANGE_ME_TO_A_SECURE_PASSWORD' in template_content:
        generated_password = generate_secure_password()
        config_content = template_content.replace('CHANGE_ME_TO_A_SECURE_PASSWORD', generated_password)
        logger.info("Generated secure password for repository")
    else:
        config_content = template_content
    
    # Write config file
    with open(path, 'w', encoding='utf-8') as f:
        f.write(config_content)
    
    # Set secure permissions (readable only by owner)
    path.chmod(0o600)
    logger.info(f"Configuration created at {path}")
    
    # If password was generated, save it separately and display it
    if generated_password:
        # Save password file in systemd-creds compatible format
        password_file = path.parent / f".{path.stem}.password"
        
        # Create the password file content in a format ready for secrets
        with open(password_file, 'w') as f:
            # Just the password on first line (for easy piping to secret stores)
            f.write(f"{generated_password}\n")
        
        password_file.chmod(0o600)  # Only owner can read
        
        # Also create a info file for the user
        info_file = path.parent / f".{path.stem}.password.info"
        with open(info_file, 'w') as f:
            f.write(f"Kopi-Docka Repository Password Information\n")
            f.write(f"==========================================\n\n")
            f.write(f"Created: {datetime.now().isoformat()}\n")
            f.write(f"Config: {path}\n")
            f.write(f"Password file: {password_file}\n\n")
            f.write(f"IMPORTANT: This password is required for ALL restore operations!\n\n")
            f.write(f"Migration to secure storage:\n")
            f.write(f"----------------------------\n")
            f.write(f"# For systemd-creds (systemd 250+):\n")
            f.write(f"sudo systemd-creds encrypt --name=kopia_password {password_file} /etc/credstore/kopia_password\n\n")
            f.write(f"# For Docker secrets:\n")
            f.write(f"docker secret create kopia_password {password_file}\n\n")
            f.write(f"# For environment variable:\n")
            f.write(f"export KOPIA_PASSWORD=$(cat {password_file})\n\n")
            f.write(f"After migration, delete the password file:\n")
            f.write(f"shred -vzu {password_file}\n")
        
        info_file.chmod(0o600)
        
        # Display password prominently
        print("\n" + "="*70)
        print("🔐 REPOSITORY PASSWORD GENERATED")
        print("="*70)
        print(f"Password: {generated_password}")
        print("="*70)
        print(f"✓ Password saved to: {password_file}")
        print(f"✓ Migration guide: {info_file}")
        print("")
        
        # Check if systemd-creds is available
        if shutil.which('systemd-creds'):
            print("⚠️  MIGRATE TO SECURE STORAGE:")
            print(f"   sudo systemd-creds encrypt --name=kopia_password {password_file}")
            print("")
            print("⚠️  Then delete the plaintext file:")
            print(f"   shred -vzu {password_file}")
        else:
            print("💡 TIP: Install systemd 250+ for encrypted credential storage")
            print("   or use environment variable: export KOPIA_PASSWORD=$(cat {password_file})")
        
        print("="*70 + "\n")
    
    return path


class Config:
    """
    Manages application configuration.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Optional path to config file
        """
        self._config = configparser.ConfigParser(interpolation=None)
        
        self.config_file = self._find_config_file(config_path)
        if not self.config_file.exists():
            logger.info(f"No configuration found. Creating default at {self.config_file}")
            create_default_config(self.config_file)
        
        self._load_config()
        self._ensure_required_values()
        
    def _find_config_file(self, config_path: Optional[Path] = None) -> Path:
        """Find the configuration file."""
        if config_path:
            return Path(config_path).expanduser()
        
        # Check default locations
        if os.geteuid() == 0: 
            # Running as root
            return Path(DEFAULT_CONFIG_PATHS["root"])
        else:
            # Running as user (development mode)
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
        password = self.get('kopia', 'password')
        if not password or password == 'CHANGE_ME_TO_A_SECURE_PASSWORD':
            raise ValueError("Kopia password is not set or still has placeholder value.")
        
        if not self.get('kopia', 'repository_path'):
            raise ValueError("Kopia repository path is not set.")
    
    def get(self, section: str, option: str, fallback: Any = None) -> Any:
        """Get a configuration value."""
        try:
            if self._config.has_option(section, option):
                return self._config.get(section, option)
        except:
            pass
        
        return fallback

    def getint(self, section: str, option: str, fallback: int = 0) -> int:
        """Get an integer configuration value."""
        value = self.get(section, option, fallback)
        
        if isinstance(value, int):
            return value
            
        if isinstance(value, str):
            if value.lower() == 'auto':
                return -1
            try:
                return int(value)
            except (ValueError, TypeError):
                pass
                
        return fallback

    def getboolean(self, section: str, option: str, fallback: bool = False) -> bool:
        """Get a boolean configuration value."""
        value = self.get(section, option, fallback)
        
        if isinstance(value, bool):
            return value
            
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on')
            
        return fallback

    def getlist(self, section: str, option: str, fallback: Optional[List[str]] = None) -> List[str]:
        """Get a list from comma-separated configuration value."""
        value = self.get(section, option)
        
        if not value:
            return fallback or []
            
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
            
        return fallback or []

    # --- Properties for easy access ---

    @property
    def kopia_repository_path(self) -> Path:
        """Get Kopia repository path."""
        path = self.get('kopia', 'repository_path')
        # Don't expand path for remote repositories
        if '://' in str(path):
            return path
        return Path(path).expanduser()

    @property
    def kopia_password(self) -> str:
        """Get Kopia password."""
        # Check environment variable first
        env_password = os.environ.get('KOPIA_PASSWORD')
        if env_password:
            return env_password
        return self.get('kopia', 'password')
    
    @property
    def kopia_profile(self) -> str:
        """Get Kopia profile name."""
        return self.get('kopia', 'profile', 'kopi-docka')
        
    @property
    def kopia_cache_directory(self) -> Path:
        """Get Kopia cache directory."""
        return Path(self.get('kopia', 'cache_directory')).expanduser()
    
    @property
    def backup_base_path(self) -> Path:
        """Get backup base path."""
        return Path(self.get('backup', 'base_path')).expanduser()

    @property
    def log_file(self) -> Optional[Path]:
        """Get log file path."""
        file_path = self.get('logging', 'file')
        if file_path:
            return Path(file_path).expanduser()
        return None

    @property
    def parallel_workers(self) -> int:
        """Get number of parallel workers."""
        workers = self.getint('backup', 'parallel_workers', -1)
        if workers == -1:  # auto
            from .system_utils import SystemUtils
            return SystemUtils.get_optimal_workers()
        return workers

    @property
    def docker_socket(self) -> str:
        """Get Docker socket path."""
        return self.get('docker', 'socket', '/var/run/docker.sock')
    
    @property
    def database_backup_enabled(self) -> bool:
        """Check if database backup is enabled."""
        return self.getboolean('backup', 'database_backup', True)
    
    @property
    def exclude_patterns(self) -> List[str]:
        """Get exclude patterns for tar."""
        return self.getlist('backup', 'exclude_patterns', [])