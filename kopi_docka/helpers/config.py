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
Supports secure password storage via password files or direct plaintext.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any

from .constants import DEFAULT_CONFIG_PATHS, VERSION
from .logging import get_logger

logger = get_logger(__name__)


def detect_repository_type(kopia_params: str) -> str:
    """
    Detect repository type from kopia_params string.

    Kopia repository types are determined by the first word of kopia_params:
    - filesystem --path /backup/...
    - rclone --remote-path gdrive:...
    - s3 --bucket ...
    - b2 --bucket ...
    - azure --container ...
    - gcs --bucket ...
    - sftp --path user@host:...
    - webdav --url ...

    Args:
        kopia_params: The kopia_params string from config

    Returns:
        Repository type string (filesystem, rclone, s3, etc.)
        Returns 'unknown' if type cannot be determined
    """
    if not kopia_params or not kopia_params.strip():
        return "unknown"

    # Split and get first word (the repository type)
    parts = kopia_params.strip().split()
    if not parts:
        return "unknown"

    repo_type = parts[0].lower()

    # Valid Kopia repository types
    valid_types = {"filesystem", "rclone", "s3", "b2", "azure", "gcs", "sftp", "webdav"}

    return repo_type if repo_type in valid_types else "unknown"


def extract_filesystem_path(kopia_params: str) -> Optional[str]:
    """
    Extract the repository path from filesystem kopia_params.

    Parses kopia_params like 'filesystem --path /backup/kopia' and returns
    the path value. Returns None for non-filesystem repositories or if
    path cannot be extracted.

    Args:
        kopia_params: The kopia_params string from config

    Returns:
        Path string if found, None otherwise

    Example:
        >>> extract_filesystem_path("filesystem --path /backup/kopia")
        '/backup/kopia'
        >>> extract_filesystem_path("rclone --remote-path=gdrive:backup")
        None
    """
    import shlex

    if not kopia_params:
        return None

    # Only works for filesystem repositories
    if detect_repository_type(kopia_params) != "filesystem":
        return None

    if "--path" not in kopia_params:
        return None

    try:
        parts = shlex.split(kopia_params)
        # Handle both --path /path and --path=/path formats
        for i, part in enumerate(parts):
            if part == "--path" and i + 1 < len(parts):
                return parts[i + 1]
            if part.startswith("--path="):
                return part.split("=", 1)[1]
    except ValueError:
        # shlex.split can raise ValueError on malformed strings
        pass

    return None


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
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Config:
    """
    Configuration manager for Kopi-Docka.

    Loads and validates configuration from JSON files.
    Provides secure password handling with multiple sources.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration.

        Args:
            config_path: Optional path to config file
        """
        self._config: Dict[str, Dict[str, Any]] = {}

        self.config_file = self._find_config_file(config_path)
        if not self.config_file.exists():
            logger.info(f"No configuration found. Creating default at {self.config_file}")
            from . import create_default_config

            create_default_config(self.config_file)

        self._load_config()
        self._ensure_required_values()

    # --------------- Properties ---------------

    @property
    def kopia_profile(self) -> str:
        """Get kopia profile name."""
        return self.get("kopia", "profile", fallback="kopi-docka")

    @property
    def kopia_cache_directory(self) -> Optional[str]:
        """Get kopia cache directory."""
        return self.get("kopia", "cache_directory", fallback=None)

    @property
    def kopia_cache_size_mb(self) -> int:
        """
        Get kopia content cache size limit in MB.

        Default: 500 MB - prevents unbounded cache growth on VPS systems.
        Set to 0 to disable cache limiting (not recommended).
        """
        return self.getint("kopia", "cache_size_mb", fallback=500)

    @property
    def kopia_password(self) -> str:
        """Get kopia password (deprecated, use get_password() instead)."""
        try:
            return self.get_password()
        except ValueError:
            return ""

    # Backup configuration properties

    @property
    def backup_base_path(self) -> Path:
        """Get backup base path as Path object."""
        path_str = self.get("backup", "base_path", fallback="/backup/kopi-docka")
        return Path(path_str).expanduser()

    @property
    def parallel_workers(self) -> int:
        """Get parallel workers setting (returns integer, auto-calculates if needed)."""
        value = self.get("backup", "parallel_workers", fallback="auto")

        if value == "auto":
            from .system_utils import SystemUtils

            return SystemUtils.get_optimal_workers()

        try:
            return int(value)
        except (ValueError, TypeError):
            return 4  # Fallback

    @property
    def stop_timeout(self) -> int:
        """Get container stop timeout in seconds."""
        return int(self.get("backup", "stop_timeout", fallback=30))

    @property
    def start_timeout(self) -> int:
        """Get container start timeout in seconds."""
        return int(self.get("backup", "start_timeout", fallback=60))

    @property
    def database_backup(self) -> bool:
        """Check if database backup is enabled."""
        val = self.get("backup", "database_backup", fallback="true")
        return val.lower() in ("true", "1", "yes", "on")

    @property
    def update_recovery_bundle(self) -> bool:
        """Check if recovery bundle should be updated."""
        val = self.get("backup", "update_recovery_bundle", fallback="false")
        return val.lower() in ("true", "1", "yes", "on")

    @property
    def recovery_bundle_path(self) -> str:
        """Get recovery bundle path."""
        return self.get("backup", "recovery_bundle_path", fallback="/backup/recovery")

    @property
    def recovery_bundle_retention(self) -> int:
        """Get recovery bundle retention count."""
        return int(self.get("backup", "recovery_bundle_retention", fallback=3))

    # Kopia settings properties

    @property
    def kopia_compression(self) -> str:
        """Get Kopia compression algorithm."""
        return self.get("kopia", "compression", fallback="zstd")

    @property
    def kopia_encryption(self) -> str:
        """Get Kopia encryption algorithm."""
        return self.get("kopia", "encryption", fallback="AES256-GCM-HMAC-SHA256")

    # --------------- Password Management ---------------

    def set_password(self, password: str, use_file: bool = False) -> None:
        """
        Set repository password in config.

        Args:
            password: The password to store
            use_file: If True, store in external file; if False, store directly in config
        """
        if use_file:
            # Store in external password file
            password_file = self.config_file.parent / f".{self.config_file.stem}.password"

            # Backup existing password file if present
            if password_file.exists():
                import shutil
                from datetime import datetime

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = (
                    self.config_file.parent
                    / f".{self.config_file.stem}.password.{timestamp}.backup"
                )
                shutil.copy2(password_file, backup_file)
                logger.info(f"Previous password backed up: {backup_file}")

            # Write new password
            password_file.write_text(password + "\n", encoding="utf-8")
            password_file.chmod(0o600)
            logger.info(f"Password stored in: {password_file}")

            # Update config to reference the file
            self.set("kopia", "password_file", str(password_file))
            self.set("kopia", "password", "")  # Clear direct password
        else:
            # Store directly in config (plaintext)
            self.set("kopia", "password", password)
            self.set("kopia", "password_file", "")  # Clear file reference
            logger.info("Password stored in config file")

        # Save config
        self.save()

    def get_password(self) -> str:
        """
        Get repository password from config.

        Supports two password sources (priority order):
        1. password_file - External file (für spätere Verschlüsselung)
        2. password - Direct plaintext in config (Standard)

        Returns:
            Repository password

        Raises:
            ValueError: If password not found or accessible
        """
        # PRIORITY 1: Check for password_file (für spätere Verschlüsselung)
        password_file_str = self.get("kopia", "password_file", fallback="")
        if password_file_str:
            password_file = Path(password_file_str).expanduser()
            if password_file.exists():
                try:
                    pwd = password_file.read_text(encoding="utf-8").strip()
                    if pwd:
                        logger.debug(f"Using password from file: {password_file}")
                        return pwd
                    else:
                        raise ValueError(f"Password file is empty: {password_file}")
                except Exception as e:
                    raise ValueError(f"Cannot read password file {password_file}: {e}")
            else:
                raise ValueError(
                    f"Password file not found: {password_file}\n"
                    f"Either create the file or remove 'password_file' setting."
                )

        # PRIORITY 2: Direct password in config (Plaintext - Standard)
        password = self.get("kopia", "password", fallback="")
        if password:
            logger.debug("Using password from config file")
            return password

        # No password configured at all
        raise ValueError(
            "No password configured.\n"
            "Options:\n"
            "  1. Set in config: password = your-secure-password\n"
            "  2. Use external file: password_file = /path/to/password\n"
            "  3. Run: kopi-docka change-password"
        )

    # --------------- Core Methods ---------------

    def get(self, section: str, option: str, fallback: Any = None) -> Any:
        """Get configuration value with fallback."""
        return self._config.get(section, {}).get(option, fallback)

    def getint(self, section: str, option: str, fallback: int = 0) -> int:
        """
        Get configuration value as integer.

        Args:
            section: Config section
            option: Config option
            fallback: Fallback value if not found

        Returns:
            Integer value
        """
        value = self.get(section, option, fallback=fallback)
        try:
            return int(value)
        except (ValueError, TypeError):
            return fallback

    def getboolean(self, section: str, option: str, fallback: bool = False) -> bool:
        """
        Get configuration value as boolean.

        Args:
            section: Config section
            option: Config option
            fallback: Fallback value if not found

        Returns:
            Boolean value
        """
        value = self.get(section, option, fallback=fallback)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return fallback

    def getlist(self, section: str, option: str, fallback: Any = None) -> List[str]:
        """
        Get configuration value as list (comma-separated).

        Args:
            section: Config section
            option: Config option
            fallback: Fallback value if not found

        Returns:
            List of strings
        """
        value = self.get(section, option, fallback=fallback)
        if not value:
            return []

        # Split by comma and strip whitespace
        return [item.strip() for item in str(value).split(",") if item.strip()]

    def set(self, section: str, option: str, value: Any) -> None:
        """Set configuration value."""
        if section not in self._config:
            self._config[section] = {}
        self._config[section][option] = value

    def save(self) -> None:
        """Save configuration to file atomically with proper permissions."""
        # Atomic save mit temp file
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self.config_file.parent, prefix=".kopi-docka-config-", suffix=".tmp"
        )

        try:
            # Schreibe mit UTF-8 encoding und schöner Formatierung
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
                f.write("\n")  # Trailing newline

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
            r"(password|secret|key|token|credential|auth|api_key|client_secret|"
            r"access_key|private_key|webhook|smtp_pass)",
            re.IGNORECASE,
        )

        for section, options in self._config.items():
            print(f"\n[{section}]")

            # Handle both dict and non-dict values
            if isinstance(options, dict):
                for option, value in options.items():
                    # Check ob Option sensitiv ist
                    if sensitive_patterns.search(option):
                        # Zeige erste 3 Zeichen für Debugging
                        if value and len(str(value)) > 3:
                            value = f"{str(value)[:3]}***MASKED***"
                        else:
                            value = "***MASKED***"

                    print(f"  {option} = {value}")
            else:
                # If section value is not a dict, display it directly
                print(f"  {options}")

    def validate(self) -> List[str]:
        """
        Validiere die Konfiguration mit sinnvollen Wertebereichen.

        Returns:
            Liste von Fehlermeldungen (leer wenn alles OK)
        """
        errors = []

        # Check kopia_params
        kopia_params = self.get("kopia", "kopia_params", fallback="")

        if not kopia_params:
            errors.append("Missing 'kopia_params' in config")

        # Check password
        try:
            pwd = self.get_password()
            if not pwd:
                errors.append("No password configured")
            elif pwd == "kopia-docka":
                logger.warning("Using default password - change after init!")
        except ValueError as e:
            errors.append(f"Password error: {e}")

        # Check numeric values
        parallel_workers = self.get("backup", "parallel_workers", fallback="auto")
        if parallel_workers != "auto":
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
            "kopia": {
                "kopia_params": "filesystem --path /backup/kopia-repository",
                "password": "kopia-docka",  # Standard-Passwort (ändern nach init!)
                "password_file": "",  # Optional: Pfad zu Passwort-Datei
                "profile": "kopi-docka",
                "compression": "zstd",
                "encryption": "AES256-GCM-HMAC-SHA256",
                "cache_directory": "/var/cache/kopi-docka",
            },
            "backup": {
                "base_path": "/backup/kopi-docka",
                "parallel_workers": "auto",
                "stop_timeout": 30,
                "start_timeout": 60,
                "database_backup": "true",
                "update_recovery_bundle": "false",
                "recovery_bundle_path": "/backup/recovery",
                "recovery_bundle_retention": 3,
                "exclude_patterns": "",
                "pre_backup_hook": "",
                "post_backup_hook": "",
            },
            "docker": {
                "socket": "/var/run/docker.sock",
                "compose_timeout": 300,
                "prune_stopped_containers": "false",
            },
            "retention": {"daily": 7, "weekly": 4, "monthly": 12, "yearly": 5},
            "logging": {"level": "INFO", "file": "", "max_size_mb": 100, "backup_count": 5},
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
            DEFAULT_CONFIG_PATHS["user"],  # ~/.config/... zuerst
            DEFAULT_CONFIG_PATHS["root"],  # /etc/... als Fallback
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
            path = Path(DEFAULT_CONFIG_PATHS["root"])
        else:
            path = Path(DEFAULT_CONFIG_PATHS["user"])

        path = path.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)

        logger.debug(f"Using default config path: {path}")
        return path

    def _load_config(self) -> None:
        """Load configuration from JSON file with UTF-8 encoding."""
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                self._config = json.load(f)
            logger.info(f"Configuration loaded from {self.config_file}")
        except json.JSONDecodeError as e:
            logger.error(f"Config file JSON parsing error: {e}")
            raise ValueError(f"Invalid JSON in config file {self.config_file}: {e}")
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
    Create default configuration from JSON template.

    Args:
        path: Optional path where to create the config file
        force: Overwrite existing file if True

    Returns:
        Path to the created config file
    """
    from datetime import datetime

    if path is None:
        if os.geteuid() == 0:
            path = Path("/etc/kopi-docka.json")
        else:
            path = Path.home() / ".config" / "kopi-docka" / "config.json"
    else:
        path = Path(path).expanduser()

    if path.exists() and not force:
        logger.warning(f"Configuration file already exists at {path}")
        return path

    path.parent.mkdir(parents=True, exist_ok=True)

    # Copy JSON template
    template_path = Path(__file__).parent.parent / "templates" / "config_template.json"

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
