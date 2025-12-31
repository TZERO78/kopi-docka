"""Helper modules and utilities for Kopi-Docka."""

from .config import (
    Config,
    create_default_config,
    generate_secure_password,
    detect_repository_type,
    extract_filesystem_path,
)
from .constants import VERSION, DEFAULT_CONFIG_PATHS
from .logging import get_logger, log_manager
from .system_utils import SystemUtils
from .file_operations import (
    check_file_conflicts,
    create_file_backup,
    copy_with_rollback,
)
from .ui_utils import run_command, SubprocessError
from .dependency_helper import DependencyHelper, ToolInfo
from .repo_helper import (
    detect_existing_filesystem_repo,
    detect_existing_cloud_repo,
    get_backend_type,
    is_cloud_backend,
)

__all__ = [
    "Config",
    "create_default_config",
    "generate_secure_password",
    "detect_repository_type",
    "extract_filesystem_path",
    "VERSION",
    "DEFAULT_CONFIG_PATHS",
    "get_logger",
    "log_manager",
    "SystemUtils",
    "check_file_conflicts",
    "create_file_backup",
    "copy_with_rollback",
    "run_command",
    "SubprocessError",
    "DependencyHelper",
    "ToolInfo",
    "detect_existing_filesystem_repo",
    "detect_existing_cloud_repo",
    "get_backend_type",
    "is_cloud_backend",
]
