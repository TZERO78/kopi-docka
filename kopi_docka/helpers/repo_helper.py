################################################################################
# KOPI-DOCKA
#
# @file:        repo_helper.py
# @module:      kopi_docka.helpers
# @description: Repository detection and validation helpers
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.5.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Repository detection and validation helpers.

Provides functions to detect existing Kopia repositories for both:
- Filesystem backends (local, NAS mounts)
- Cloud backends (S3, B2, Azure, GCS, SFTP)

Used by:
- repository_commands.py (repo init --reinit)
- config_commands.py (config new - after path input)
"""

import contextlib
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from . import get_logger

logger = get_logger(__name__)


def detect_existing_filesystem_repo(kopia_params: str) -> tuple[bool, Optional[Path]]:
    """
    Detect if a filesystem-based Kopia repository already exists.

    Parses kopia_params for 'filesystem --path <path>' pattern and checks
    if the path exists and is non-empty (contains Kopia repo files).

    Args:
        kopia_params: The kopia_params string from config (e.g., "filesystem --path /backup/repo")

    Returns:
        Tuple of (exists: bool, path: Path | None)
        - (True, Path) if repo exists and is non-empty
        - (False, Path) if path exists but is empty (no repo yet)
        - (False, None) if not a filesystem backend or path doesn't exist
    """
    # Only handle filesystem backend
    if not kopia_params.strip().startswith("filesystem"):
        return (False, None)

    # Parse --path argument from kopia_params
    # Matches: filesystem --path /some/path or filesystem --path="/some/path"
    path_match = re.search(r'--path[=\s]+["\']?([^"\'\s]+)["\']?', kopia_params)
    if not path_match:
        return (False, None)

    try:
        # Resolve symlinks and normalize path
        repo_path = Path(path_match.group(1)).expanduser().resolve()
    except (OSError, RuntimeError) as e:
        # Handle broken symlinks or permission issues during resolution
        logger.warning(f"Could not resolve path {path_match.group(1)}: {e}")
        return (False, None)

    # Path doesn't exist → no existing repo
    if not repo_path.exists():
        # Check if parent exists - if not, normal create flow will handle it
        return (False, None)

    # Check if it's a file (not directory) - this is an error state
    if repo_path.is_file():
        logger.warning(f"Path {repo_path} exists but is a file, not a directory")
        return (False, None)

    # Try to list directory contents - catch permission errors
    try:
        dir_contents = list(repo_path.iterdir())
    except PermissionError as e:
        logger.warning(f"Permission denied reading {repo_path}: {e}")
        # Treat as existing - user needs to fix permissions
        return (True, repo_path)
    except OSError as e:
        logger.warning(f"Could not read directory {repo_path}: {e}")
        return (False, None)

    # Path exists but is empty → no repo yet, normal create flow
    if not dir_contents:
        return (False, repo_path)

    # Check for Kopia repo markers (kopia.repository or p/ blob directory)
    kopia_markers = [
        repo_path / "kopia.repository",
        repo_path / "kopia.repository.f",
        repo_path / "p",  # Kopia blob storage directory
    ]

    if any(marker.exists() for marker in kopia_markers):
        return (True, repo_path)

    # Directory exists with content but no Kopia markers → not a Kopia repo
    # Treat as potential conflict - show wizard so user can decide
    logger.warning(f"Directory {repo_path} exists with content but no Kopia repo markers")
    return (False, repo_path)


def detect_existing_cloud_repo(kopia_params: str, password: str) -> tuple[bool, Optional[str]]:
    """
    Detect if a cloud-based Kopia repository already exists (S3, B2, Azure, GCS).

    Uses 'kopia repository status' with the given params to check if a repo exists.
    This requires valid credentials to be configured (env vars or in kopia_params).

    Args:
        kopia_params: The kopia_params string from config (e.g., "s3 --bucket my-bucket --prefix backup")
        password: Repository password for connection attempt

    Returns:
        Tuple of (exists: bool, location: str | None)
        - (True, location_string) if repo exists in cloud
        - (False, location_string) if bucket/container accessible but no repo
        - (False, None) if not a cloud backend or check failed
    """
    # Identify cloud backend type
    cloud_backends = {
        "s3": r"--bucket[=\s]+[\"']?([^\"\'\s]+)[\"']?",
        "b2": r"--bucket[=\s]+[\"']?([^\"\'\s]+)[\"']?",
        "azure": r"--container[=\s]+[\"']?([^\"\'\s]+)[\"']?",
        "gcs": r"--bucket[=\s]+[\"']?([^\"\'\s]+)[\"']?",
        "sftp": r"--path[=\s]+[\"']?([^\"\'\s]+)[\"']?",
    }

    backend_type = None
    location = None

    for backend, pattern in cloud_backends.items():
        if kopia_params.strip().startswith(backend):
            backend_type = backend
            match = re.search(pattern, kopia_params)
            if match:
                location = f"{backend}://{match.group(1)}"
            break

    if not backend_type:
        return (False, None)

    # Try to connect to check if repo exists
    # Use a temporary config file to avoid polluting the user's config
    with tempfile.NamedTemporaryFile(mode="w", suffix=".config", delete=False) as tmp_cfg:
        tmp_config_path = tmp_cfg.name

    try:
        env = os.environ.copy()
        env["KOPIA_PASSWORD"] = password

        # Try kopia repository connect (not create)
        cmd = [
            "kopia",
            "repository",
            "connect",
            *kopia_params.split(),
            "--config-file",
            tmp_config_path,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

        if result.returncode == 0:
            # Successfully connected → repo exists
            # Disconnect to clean up
            subprocess.run(
                ["kopia", "repository", "disconnect", "--config-file", tmp_config_path],
                capture_output=True,
                env=env,
                timeout=10,
            )
            return (True, location)

        # Check error message for clues
        stderr = result.stderr.lower()
        if "not found" in stderr or "does not exist" in stderr or "no such" in stderr:
            # Bucket/location exists but no repo
            return (False, location)
        elif "invalid password" in stderr or "password" in stderr:
            # Repo exists but wrong password
            return (True, location)
        elif "access denied" in stderr or "forbidden" in stderr or "unauthorized" in stderr:
            # Credential issue - can't determine
            logger.warning(f"Cloud access denied for {location}: {result.stderr}")
            return (False, None)
        else:
            # Other error - assume no repo
            logger.debug(f"Cloud repo check failed: {result.stderr}")
            return (False, location)

    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout checking cloud repo at {location}")
        return (False, None)
    except Exception as e:
        logger.warning(f"Error checking cloud repo: {e}")
        return (False, None)
    finally:
        # Clean up temp config
        with contextlib.suppress(OSError):
            Path(tmp_config_path).unlink()


def get_backend_type(kopia_params: str) -> str:
    """
    Extract the backend type from kopia_params.

    Args:
        kopia_params: The kopia_params string (e.g., "filesystem --path /backup")

    Returns:
        Backend type string (e.g., "filesystem", "s3", "b2", etc.) or "unknown"
    """
    params = kopia_params.strip().lower()
    known_backends = ["filesystem", "s3", "b2", "azure", "gcs", "sftp", "rclone", "tailscale"]

    for backend in known_backends:
        if params.startswith(backend):
            return backend

    return "unknown"


def is_cloud_backend(kopia_params: str) -> bool:
    """
    Check if the backend is a cloud/remote backend (not local filesystem).

    Args:
        kopia_params: The kopia_params string

    Returns:
        True if cloud backend (s3, b2, azure, gcs, sftp), False otherwise
    """
    backend_type = get_backend_type(kopia_params)
    return backend_type in ("s3", "b2", "azure", "gcs", "sftp")
