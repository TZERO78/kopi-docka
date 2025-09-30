################################################################################
# KOPI-DOCKA
#
# @file:        config.py
# @module:      kopi_docka.config
# @description: Manages configuration discovery, defaults, validation, and persistence.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Searches DEFAULT_CONFIG_PATHS before creating a fresh config file
# - Generates ASCII-safe random passwords for Kopia on first run
# - Offers typed getters with sane defaults and environment overrides
################################################################################

"""
Configuration management for Kopi-Docka.

Handles reading, writing, and validating configuration files,
and creates default configurations when needed.
"""

import configparser
import secrets
import string
import tempfile
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
import os

from .constants import DEFAULT_CONFIG_PATHS, DEFAULT_BACKUP_BASE
from .logging import get_logger

logger = get_logger(__name__)


class Config:
    """
    Manages application configuration.

    Loads configuration from INI files, provides defaults and validation.

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
        # Interpolation off: avoid issues with % in passwords
        self._config = configparser.ConfigParser(interpolation=None)

        # Find or create configuration file
        self.config_file = self._find_config_file(config_path)

        # Create if not exists
        if not self.config_file.exists():
            logger.info(f"Creating default configuration at {self.config_file}")
            create_default_config(self.config_file)

        self._load_config()
        self._ensure_required_values()

    def _get_defaults(self) -> Dict[str, Dict[str, Any]]:
        """Default configuration values."""
        return {
            "kopia": {
                "repository_path": "/backup/kopia-repository",
                "password": None,  # will be generated on first run if needed
                "compression": "zstd",
                "encryption": "AES256-GCM-HMAC-SHA256",
                "cache_directory": "/var/cache/kopi-docka",
            },
            "backup": {
                "base_path": str(DEFAULT_BACKUP_BASE),
                "parallel_workers": "auto",
                "stop_timeout": 30,
                "start_timeout": 60,
                "update_recovery_bundle": "false",
                "recovery_bundle_path": "/backup/recovery",
                "recovery_bundle_retention": 3,
                "exclude_patterns": "",  # comma-separated
                "pre_backup_hook": "",
                "post_backup_hook": "",
            },
            "docker": {
                "socket": "/var/run/docker.sock",
                "compose_timeout": 300,
                "prune_stopped_containers": "false",
            },
            "retention": {"daily": 7, "weekly": 4, "monthly": 12, "yearly": 5},
            "logging": {
                "level": "INFO",
                "file": "/var/log/kopi-docka.log",
                "max_size_mb": 100,
                "backup_count": 5,
            },
        }

    def _find_config_file(self, config_path: Optional[Path] = None) -> Path:
        """Find or determine configuration file path."""
        if config_path:
            if isinstance(config_path, str):
                config_path = Path(config_path)
            config_path = config_path.expanduser().resolve()
            try:
                config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            except PermissionError as e:
                logger.error(
                    f"Cannot create config directory {config_path.parent}: {e}"
                )
                raise
            return config_path

        search_order = [DEFAULT_CONFIG_PATHS["user"], DEFAULT_CONFIG_PATHS["root"]]

        for location in search_order:
            p = Path(location).expanduser()
            if p.exists():
                if os.access(p, os.R_OK):
                    logger.debug(f"Using config file: {p}")
                    return p
                else:
                    logger.warning(f"Config file exists but not readable: {p}")

        path = Path(
            DEFAULT_CONFIG_PATHS["root"]
            if os.geteuid() == 0
            else DEFAULT_CONFIG_PATHS["user"]
        ).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        logger.debug(f"Using default config path: {path}")
        return path

    def _load_config(self):
        """Load configuration from file with UTF-8 encoding."""
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                self._config.read_file(f)
            logger.info(f"Configuration loaded from {self.config_file}")
        except UnicodeDecodeError as e:
            logger.error(f"Config file encoding error (expected UTF-8): {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    def _ensure_required_values(self):
        """
        Ensure critical values like passwords exist.
        Generate ONCE and persist them.
        """
        modified = False

        # Kopia password
        kopia_pass = self.get("kopia", "password")
        if not kopia_pass or kopia_pass == "CHANGE_ME_TO_A_SECURE_PASSWORD":
            new_password = generate_secure_password()
            self.set("kopia", "password", new_password)
            logger.warning(
                f"Generated new Kopia password and saved to {self.config_file}"
            )
            logger.warning(
                "⚠️  IMPORTANT: Save this password securely for disaster recovery!"
            )
            modified = True

        if modified:
            self.save()

    def get(self, section: str, option: str, fallback: Any = None) -> Any:
        """
        Get configuration value with environment override support.
        """
        if section == "kopia" and option == "password":
            env_password = os.environ.get("KOPIA_PASSWORD")
            if env_password:
                return env_password

        env_var = f"KOPI_DOCKA_{section.upper()}_{option.upper()}"
        env_value = os.environ.get(env_var)
        if env_value:
            logger.debug(f"Using environment override for {section}.{option}")
            return env_value

        try:
            value = self._config.get(section, option)
            if value and (
                "path" in option.lower()
                or "file" in option.lower()
                or "directory" in option.lower()
            ):
                if "://" not in value:
                    value = str(Path(value).expanduser())
            return value
        except (configparser.NoSectionError, configparser.NoOptionError):
            if section in self._defaults and option in self._defaults[section]:
                default_value = self._defaults[section][option]
                if default_value is not None:
                    if isinstance(default_value, str) and (
                        "path" in option.lower() or "file" in option.lower()
                    ):
                        if "://" not in default_value:
                            default_value = str(Path(default_value).expanduser())
                    return default_value
            return fallback

    def getint(self, section: str, option: str, fallback: int = 0) -> int:
        """Get integer configuration value."""
        value = self.get(section, option, fallback)
        if isinstance(value, str):
            if value.lower() == "auto":
                return -1
            try:
                return int(value)
            except ValueError:
                logger.warning(f"Invalid integer value for {section}.{option}: {value}")
                return fallback
        return int(value) if value is not None else fallback

    def getboolean(self, section: str, option: str, fallback: bool = False) -> bool:
        """Get boolean configuration value."""
        value = self.get(section, option, str(fallback))
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1", "on")
        return fallback

    def getlist(
        self, section: str, option: str, fallback: List[str] = None
    ) -> List[str]:
        """Get list configuration value (comma-separated)."""
        value = self.get(section, option)
        if value:
            items = [i.strip() for i in value.split(",") if i.strip()]
            return list(dict.fromkeys(items))
        return fallback or []

    def set(self, section: str, option: str, value: Any):
        """Set configuration value."""
        if not self._config.has_section(section):
            self._config.add_section(section)
        self._config.set(section, option, str(value))

    def save(self):
        """Save configuration to file atomically with proper permissions."""
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self.config_file.parent, prefix=".kopi-docka-config-", suffix=".tmp"
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                self._config.write(f)
            os.replace(temp_path, self.config_file)
            os.chmod(self.config_file, 0o600)
            logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass
            logger.error(f"Failed to save configuration: {e}")
            raise e

    def display(self):
        """Display current configuration (with sensitive values masked)."""
        print(f"Configuration file: {self.config_file}")
        print("=" * 60)
        sensitive_patterns = re.compile(
            r"(password|secret|key|token|credential|auth|api_key|client_secret|"
            r"access_key|private_key|webhook|smtp_pass)",
            re.IGNORECASE,
        )
        for section in self._config.sections():
            print(f"\n[{section}]")
            for option, value in self._config.items(section):
                if sensitive_patterns.search(option):
                    if value and len(value) > 3:
                        value = f"{value[:3]}***MASKED***"
                    else:
                        value = "***MASKED***"
                print(f"  {option} = {value}")

    def validate(self) -> List[str]:
        """Validate configuration ranges & paths."""
        errors = []
        warnings = []

        # Repository path
        repo_path = self.get("kopia", "repository_path")
        if repo_path and "://" not in repo_path:
            if repo_path.startswith("/"):
                repo_path = Path(repo_path).expanduser()
                parent = repo_path.parent
                if not parent.exists():
                    errors.append(
                        f"Repository parent directory does not exist: {parent}"
                    )
                elif not os.access(parent, os.W_OK):
                    errors.append(f"No write access to repository parent: {parent}")
            else:
                errors.append(f"Local repository path must be absolute: {repo_path}")
        elif repo_path and "://" in repo_path:
            valid_schemes = [
                "s3://",
                "b2://",
                "azure://",
                "gs://",
                "sftp://",
                "webdav://",
            ]
            if not any(repo_path.startswith(s) for s in valid_schemes):
                warnings.append(
                    f"Unusual repository scheme: {repo_path.split('://')[0]}://"
                )

        # Docker socket
        docker_socket_path = self.get("docker", "socket")
        docker_socket = Path(docker_socket_path).expanduser()
        if not docker_socket.exists():
            errors.append(f"Docker socket not found: {docker_socket}")
        else:
            if not os.access(docker_socket, os.R_OK):
                errors.append(f"No read access to Docker socket: {docker_socket}")
            if not os.access(docker_socket, os.W_OK):
                errors.append(f"No write access to Docker socket: {docker_socket}")
                if os.geteuid() != 0:
                    warnings.append(
                        "Hint: Add your user to the 'docker' group: sudo usermod -aG docker $USER"
                    )

        # Backup base path
        base_path_str = self.get("backup", "base_path")
        base_path = Path(base_path_str).expanduser()
        if not base_path.exists():
            try:
                base_path.mkdir(parents=True, exist_ok=True, mode=0o755)
                logger.info(f"Created backup base path: {base_path}")
            except PermissionError:
                errors.append(f"Cannot create backup base path: {base_path}")
        elif not os.access(base_path, os.W_OK):
            errors.append(f"No write access to backup base path: {base_path}")

        # Numeric ranges
        stop_timeout = self.getint("backup", "stop_timeout")
        if not 0 < stop_timeout <= 300:
            errors.append(f"stop_timeout out of range (1-300): {stop_timeout}")

        start_timeout = self.getint("backup", "start_timeout")
        if not 0 < start_timeout <= 600:
            errors.append(f"start_timeout out of range (1-600): {start_timeout}")

        compose_timeout = self.getint("docker", "compose_timeout")
        if not 0 < compose_timeout <= 3600:
            errors.append(f"compose_timeout out of range (1-3600): {compose_timeout}")

        parallel_workers = self.getint("backup", "parallel_workers")
        if parallel_workers != -1 and not 1 <= parallel_workers <= 32:
            errors.append(
                f"parallel_workers out of range (1-32 or 'auto'): {parallel_workers}"
            )

        retention = self.getint("backup", "recovery_bundle_retention")
        if not 0 < retention <= 100:
            errors.append(
                f"recovery_bundle_retention out of range (1-100): {retention}"
            )

        valid_compression = ["zstd", "gzip", "s2", "none"]
        compression = self.get("kopia", "compression")
        if compression not in valid_compression:
            errors.append(
                f"Invalid compression algorithm: {compression}. Valid: {', '.join(valid_compression)}"
            )

        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        log_level = self.get("logging", "level", "INFO").upper()
        if log_level not in valid_levels:
            errors.append(
                f"Invalid log level: {log_level}. Valid: {', '.join(valid_levels)}"
            )

        log_file_str = self.get("logging", "file")
        if log_file_str:
            log_file = Path(log_file_str).expanduser()
            log_dir = log_file.parent
            if not log_dir.exists():
                try:
                    log_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
                    logger.info(f"Created log directory: {log_dir}")
                except PermissionError:
                    warnings.append(f"Cannot create log directory: {log_dir}")
            elif not os.access(log_dir, os.W_OK):
                warnings.append(f"No write access to log directory: {log_dir}")

        for hook in ["pre_backup_hook", "post_backup_hook"]:
            hook_path = self.get("backup", hook)
            if hook_path:
                hook_file = Path(hook_path).expanduser()
                if not hook_file.exists():
                    errors.append(f"{hook} script not found: {hook_file}")
                elif not os.access(hook_file, os.X_OK):
                    errors.append(f"{hook} script not executable: {hook_file}")

        retention_settings = [
            ("daily", 1, 365),
            ("weekly", 0, 52),
            ("monthly", 0, 120),
            ("yearly", 0, 100),
        ]
        for setting, min_val, max_val in retention_settings:
            value = self.getint("retention", setting, -1)
            if value != -1 and not min_val <= value <= max_val:
                errors.append(
                    f"retention.{setting} out of range ({min_val}-{max_val}): {value}"
                )

        for warning in warnings:
            logger.warning(warning)

        return errors

    @property
    def kopia_repository_path(self) -> Union[str, Path]:
        """Get Kopia repository path."""
        path = self.get("kopia", "repository_path")
        if "://" in path:
            return path
        return Path(path).expanduser()

    @property
    def kopia_password(self) -> str:
        return self.get("kopia", "password")

    @property
    def backup_base_path(self) -> Path:
        path = self.get("backup", "base_path")
        return Path(path).expanduser()

    @property
    def parallel_workers(self) -> int:
        workers = self.getint("backup", "parallel_workers", -1)
        if workers == -1:
            from .system_utils import SystemUtils

            workers = SystemUtils().get_optimal_workers()
            logger.debug(f"Auto-detected {workers} parallel workers")
        return max(1, min(32, workers))

    @property
    def docker_socket(self) -> str:
        socket = self.get("docker", "socket", "/var/run/docker.sock")
        return str(Path(socket).expanduser())

    @property
    def retention_config(self) -> Dict[str, int]:
        return {
            "daily": self.getint("retention", "daily", 7),
            "weekly": self.getint("retention", "weekly", 4),
            "monthly": self.getint("retention", "monthly", 12),
            "yearly": self.getint("retention", "yearly", 5),
        }


def generate_secure_password(length: int = 32) -> str:
    """
    Generate a cryptographically secure password.
    Uses only alnum + _- to avoid INI/Shell issues.
    """
    if length < 12:
        length = 12
    alphabet = string.ascii_letters + string.digits + "_-"
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("_-"),
    ]
    for _ in range(length - 4):
        password.append(secrets.choice(alphabet))
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


def create_default_config(path: Optional[Path] = None, force: bool = False):
    """
    Create default configuration file.

    Args:
        path: Path where to create config file
        force: Overwrite existing file if True
    """
    if path is None:
        path = Path(
            DEFAULT_CONFIG_PATHS["root"]
            if os.geteuid() == 0
            else DEFAULT_CONFIG_PATHS["user"]
        )

    if isinstance(path, str):
        path = Path(path)
    path = path.expanduser()

    if path.exists() and not force:
        logger.warning(f"Configuration file already exists at {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)

    config = configparser.ConfigParser(interpolation=None)

    # Build defaults from _get_defaults()
    defaults = Config().__class__._get_defaults(
        Config()
    )  # call unbound on temp instance
    for section, options in defaults.items():
        config.add_section(section)
        for option, value in options.items():
            if value is not None:
                config.set(section, option, str(value))
            else:
                if option == "password":
                    config.set(section, option, "CHANGE_ME_TO_A_SECURE_PASSWORD")

    temp_fd, temp_path = tempfile.mkstemp(
        dir=path.parent, prefix=".kopi-docka-config-", suffix=".tmp"
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write("# Kopi-Docka Configuration File\n")
            f.write("# =============================\n")
            f.write("# Generated automatically\n")
            f.write("# Edit as needed\n")
            f.write("# Encoding: UTF-8\n")
            f.write("#\n")
            f.write("# Environment variable overrides:\n")
            f.write("#   KOPIA_PASSWORD - Override kopia.password\n")
            f.write("#   KOPI_DOCKA_<SECTION>_<OPTION> - Override any option\n")
            f.write("#\n")
            f.write("# Remote repository examples:\n")
            f.write("#   s3://bucket-name/path\n")
            f.write("#   b2://bucket-name/path\n")
            f.write("#   azure://container/path\n")
            f.write("#   gs://bucket-name/path\n\n")
            config.write(f)
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
        logger.info(f"Default configuration created at {path}")
    except Exception as e:
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except:
            pass
        logger.error(f"Failed to create default config: {e}")
        raise e
