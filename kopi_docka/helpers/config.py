#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        config.py
# @module:      kopi_docka.helpers.config
# @description: Configuration management with secure password handling
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------ 
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Configuration management for Kopi-Docka.

Handles loading, validation, and access to configuration settings.
Supports secure password storage via systemd-creds or password files.
"""

from __future__ import annotations

import configparser
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any

from .constants import DEFAULT_CONFIG_PATHS, VERSION
from .logging import get_logger

logger = get_logger(__name__)

def generate_secure_password(length: int = 32) -> str:
    """
    Generate a cryptographically secure random password.
    
    Args:
        length: Password length (default: 32)
        
    Returns:
        Random password string
    """
    import secrets
    import string
    
    # Alle sicheren Zeichen (keine Verwechslungsgefahr wie 0/O, 1/l)
    alphabet = string.ascii_letters + string.digits + "!@#$^&*()-_=+[]{}|;:,.<>?/"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

class Config:
    """
    Configuration manager for Kopi-Docka.
    
    Loads and validates configuration from INI files.
    Provides secure password handling with multiple sources.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Optional path to config file
        """
        # WICHTIG: Interpolation deaktivieren wegen % in Passwörtern
        self._config = configparser.ConfigParser(interpolation=None)
        
        self.config_file = self._find_config_file(config_path)
        if not self.config_file.exists():
            logger.info(f"No configuration found. Creating default at {self.config_file}")
            from . import create_default_config
            create_default_config(self.config_file)
        
        self._load_config()
        self._ensure_required_values()
    
    # --------------- Properties ---------------
    
    @property
    def kopia_repository_path(self) -> str:
        """Get kopia repository path."""
        return self.get('kopia', 'repository_path')
    
    @property
    def kopia_profile(self) -> str:
        """Get kopia profile name."""
        return self.get('kopia', 'profile', fallback='kopi-docka')
    
    @property
    def kopia_cache_directory(self) -> Optional[str]:
        """Get kopia cache directory."""
        return self.get('kopia', 'cache_directory', fallback=None)
    
    @property
    def kopia_password(self) -> str:
        """Get kopia password (deprecated, use get_password() instead)."""
        try:
            return self.get_password()
        except ValueError:
            return ''
    
    # --------------- Password Management ---------------
    
    def get_password(self) -> str:
        """
        Get repository password from config.
        
        Supports multiple password sources:
        1. Direct password in config (e.g., "kopia-docka")
        2. Reference to systemd-creds: ${CREDENTIALS_DIRECTORY}/name
        3. Reference to password file: password_file setting
        
        Returns:
            Repository password
            
        Raises:
            ValueError: If password not accessible
        """
        password = self.get('kopia', 'password', fallback='')
        
        # Check for systemd-creds reference
        if password.startswith('${CREDENTIALS_DIRECTORY}/'):
            cred_name = password.replace('${CREDENTIALS_DIRECTORY}/', '')
            # In systemd service: /run/credentials/kopi-docka.service/
            cred_path = Path(f"/run/credentials/kopi-docka.service/{cred_name}")
            
            if cred_path.exists():
                return cred_path.read_text().strip()
            else:
                # Fallback: Try credstore.encrypted (needs manual decrypt)
                encrypted_path = Path(f"/etc/credstore.encrypted/{cred_name}")
                if encrypted_path.exists():
                    raise ValueError(
                        f"Credential exists but not loaded: {encrypted_path}\n"
                        "Run as systemd service or manually decrypt with:\n"
                        f"  systemd-creds decrypt {encrypted_path}"
                    )
                raise ValueError(f"Credential not found: {cred_name}")
        
        # Check for password_file reference
        password_file_str = self.get('kopia', 'password_file', fallback='')
        if password_file_str:
            password_file = Path(password_file_str).expanduser()
            if password_file.exists():
                return password_file.read_text().strip()
            else:
                raise ValueError(f"Password file not found: {password_file}")
        
        # Direct password in config (including "kopia-docka")
        if password:
            return password
        
        raise ValueError(
            "No password configured.\n"
            "Options:\n"
            "  1. Use default: password = kopia-docka\n"
            "  2. Change with: kopi-docka change-password"
            )
    
    # --------------- Core Methods ---------------
    
    def get(self, section: str, option: str, fallback: Any = None) -> Any:
        """Get configuration value with fallback."""
        try:
            return self._config.get(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback
    
    def set(self, section: str, option: str, value: Any) -> None:
        """Set configuration value."""
        if not self._config.has_section(section):
            self._config.add_section(section)
        self._config.set(section, option, str(value))
    
    def save(self) -> None:
        """Save configuration to file atomically with proper permissions."""
        # Atomic save mit temp file
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self.config_file.parent,
            prefix='.kopi-docka-config-',
            suffix='.tmp'
        )
        
        try:
            # Schreibe mit UTF-8 encoding
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                self._config.write(f)
            
            # Atomic replace
            os.replace(temp_path, self.config_file)
            
            # WICHTIG: Setze Permissions NACH replace hart auf 0600
            os.chmod(self.config_file, 0o600)
            
            logger.info(f"Configuration saved to {self.config_file}")
            
        except Exception as e:
            # Cleanup bei Fehler
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass
            logger.error(f"Failed to save configuration: {e}")
            raise e
    
    def display(self) -> None:
        """Display current configuration (with sensitive values masked)."""
        print(f"Configuration file: {self.config_file}")
        print("=" * 60)
        
        # Erweiterte Masking-Patterns mit Regex
        sensitive_patterns = re.compile(
            r'(password|secret|key|token|credential|auth|api_key|client_secret|'
            r'access_key|private_key|webhook|smtp_pass)', 
            re.IGNORECASE
        )
        
        for section in self._config.sections():
            print(f"\n[{section}]")
            for option, value in self._config.items(section):
                # Check ob Option sensitiv ist
                if sensitive_patterns.search(option):
                    # Zeige erste 3 Zeichen für Debugging
                    if value and len(value) > 3:
                        value = f"{value[:3]}***MASKED***"
                    else:
                        value = '***MASKED***'
                
                print(f"  {option} = {value}")
    
    def validate(self) -> List[str]:
        """
        Validiere die Konfiguration mit sinnvollen Wertebereichen.
        
        Returns:
            Liste von Fehlermeldungen (leer wenn alles OK)
        """
        errors = []
        
        # Check repository path
        repo_path = self.get('kopia', 'repository_path')
        
        # Nur lokale Pfade validieren, keine Remote-Repos (s3://, b2://, etc.)
        if repo_path and '://' not in repo_path:
            path = Path(repo_path).expanduser()
            if not path.exists():
                errors.append(f"Repository path does not exist: {path}")
            elif not os.access(path, os.W_OK):
                errors.append(f"Repository path not writable: {path}")
        
        # Check password
        try:
            pwd = self.get_password()
            if not pwd:
                errors.append("No password configured")
            elif pwd == 'kopia-docka':
                logger.warning("Using default password - change after init!")
        except ValueError as e:
            errors.append(f"Password error: {e}")
        
        # Check numeric values
        parallel_workers = self.get('backup', 'parallel_workers', fallback='auto')
        if parallel_workers != 'auto':
            try:
                workers = int(parallel_workers)
                if workers < 1 or workers > 32:
                    errors.append(f"parallel_workers out of range (1-32): {workers}")
            except ValueError:
                errors.append(f"parallel_workers must be 'auto' or integer: {parallel_workers}")
        
        return errors
    
    # --------------- Private Methods ---------------
    
    @staticmethod
    def _get_default_config() -> Dict[str, Dict[str, Any]]:
        """
        Get default configuration structure.
        
        Returns:
            Dictionary of default configuration sections and values
        """
        return {
            'kopia': {
                'repository_path': '/backup/kopia-repository',
                'password': 'kopia-docka',  # Standard-Passwort
                'password_file': '',  # Leer = nicht verwendet
                'profile': 'kopi-docka',
                'compression': 'zstd',
                'encryption': 'AES256-GCM-HMAC-SHA256',
                'cache_directory': '/var/cache/kopi-docka',
            },
            'backup': {
                'base_path': '/backup/kopi-docka',
                'parallel_workers': 'auto',
                'stop_timeout': 30,
                'start_timeout': 60,
                'database_backup': 'true',
                'update_recovery_bundle': 'false',
                'recovery_bundle_path': '/backup/recovery',
                'recovery_bundle_retention': 3,
                'exclude_patterns': '',
                'pre_backup_hook': '',
                'post_backup_hook': ''
            },
            'docker': {
                'socket': '/var/run/docker.sock',
                'compose_timeout': 300,
                'prune_stopped_containers': 'false'
            },
            'retention': {
                'daily': 7,
                'weekly': 4,
                'monthly': 12,
                'yearly': 5
            },
            'logging': {
                'level': 'INFO',
                'file': '',
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
        # WICHTIG: Respektiere expliziten Pfad, auch wenn Datei noch nicht existiert
        if config_path:
            # Konvertiere zu Path falls string
            if isinstance(config_path, str):
                config_path = Path(config_path)
            
            # Expandiere ~ und mache absolut
            config_path = config_path.expanduser().resolve()
            
            # Stelle sicher dass Parent-Directory existiert
            try:
                config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            except PermissionError as e:
                logger.error(f"Cannot create config directory {config_path.parent}: {e}")
                raise
            
            return config_path
        
        # Check standard locations - USER FIRST (vermeidet Rechteprobleme)
        search_order = [
            DEFAULT_CONFIG_PATHS['user'],   # ~/.config/... zuerst
            DEFAULT_CONFIG_PATHS['root']    # /etc/... als Fallback
        ]
        
        for location in search_order:
            expanded_location = Path(location).expanduser()
            if expanded_location.exists():
                if os.access(expanded_location, os.R_OK):
                    logger.debug(f"Using config file: {expanded_location}")
                    return expanded_location
                else:
                    logger.warning(f"Config file exists but not readable: {expanded_location}")
        
        # Nichts gefunden - nutze Standard basierend auf Benutzer
        if os.geteuid() == 0:  # Running as root
            path = Path(DEFAULT_CONFIG_PATHS['root'])
        else:
            path = Path(DEFAULT_CONFIG_PATHS['user'])
        
        path = path.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        
        logger.debug(f"Using default config path: {path}")
        return path
    
    def _load_config(self) -> None:
        """Load configuration from file with UTF-8 encoding."""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self._config.read_file(f)
            logger.info(f"Configuration loaded from {self.config_file}")
        except UnicodeDecodeError as e:
            logger.error(f"Config file encoding error (expected UTF-8): {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def _ensure_required_values(self) -> None:
        """
        Stelle sicher dass kritische Werte existieren.
        Generiert Standard-Werte falls nötig.
        """
        # Für neue Configs mit Template werden keine Werte generiert
        # Das Template enthält bereits alle Defaults
        pass


def create_default_config(path: Optional[Path] = None, force: bool = False) -> Path:
    """
    Create default configuration from template.
    
    Args:
        path: Optional path where to create the config file
        force: Overwrite existing file if True
        
    Returns:
        Path to the created config file
    """
    from datetime import datetime
    
    if path is None:
        if os.geteuid() == 0:
            path = Path('/etc/kopi-docka.conf')
        else:
            path = Path.home() / '.config' / 'kopi-docka' / 'config.conf'
    else:
        path = Path(path).expanduser()
    
    if path.exists() and not force:
        logger.warning(f"Configuration file already exists at {path}")
        return path
    
    path.parent.mkdir(parents=True, exist_ok=True)

    # Copy template
    template_path = Path(__file__).parent.parent / "templates" / "config_template.conf"
    
    if not template_path.exists():
        raise FileNotFoundError(
            f"Configuration template not found at {template_path}. "
            f"Critical error: Template missing from package installation."
        )
    
    shutil.copy2(template_path, path)
    path.chmod(0o600)
    
    logger.info(f"Configuration created at {path}")
    print(f"\n✓ Configuration created: {path}")
    print("  Default password: kopia-docka")
    print("\n⚠️  IMPORTANT: Change the password after 'kopi-docka init':")
    print("  kopi-docka change-password\n")
    
    return path