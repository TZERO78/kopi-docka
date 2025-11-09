"""Helper modules and utilities for Kopi-Docka."""

from .config import Config, create_default_config, generate_secure_password
from .constants import VERSION, DEFAULT_CONFIG_PATHS
from .logging import get_logger, log_manager
from .system_utils import SystemUtils
from .file_operations import (
    check_file_conflicts,
    create_file_backup,
    copy_with_rollback,
)

__all__ = [
    'Config',
    'create_default_config',
    'generate_secure_password',
    'VERSION',
    'DEFAULT_CONFIG_PATHS',
    'get_logger',
    'log_manager',
    'SystemUtils',
    'check_file_conflicts',
    'create_file_backup',
    'copy_with_rollback',
]
