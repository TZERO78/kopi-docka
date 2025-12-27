"""
Integration tests for stable staging directory functionality.

Tests verify that recipe and network backups use stable, reusable staging
directories instead of random temporary directories, enabling Kopia retention
policies to work correctly and preventing "ghost sessions" from accumulating.

Requires:
- Docker daemon running
- Root access (for backup operations)
- Kopia binary available
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from kopi_docka.cores.backup_manager import BackupManager
from kopi_docka.cores.repository_manager import KopiaRepository
from kopi_docka.helpers.config import Config
from kopi_docka.types import BackupUnit, ContainerInfo
from kopi_docka.helpers.constants import STAGING_BASE_DIR


# Check if Docker is available
def docker_available() -> bool:
    """Check if Docker daemon is running and accessible."""
    try:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


# Check if running as root
def is_root() -> bool:
    """Check if running as root."""
    return os.geteuid() == 0


# Check if Kopia is available
def kopia_available() -> bool:
    """Check if Kopia binary is available."""
    try:
        result = subprocess.run(
            ["kopia", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


# Skip all tests in this module if requirements not met
pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_docker,
    pytest.mark.slow,
    pytest.mark.skipif(not docker_available(), reason="Docker daemon not available"),
    pytest.mark.skipif(not is_root(), reason="Requires root for backup operations"),
    pytest.mark.skipif(not kopia_available(), reason="Kopia binary not available"),
]


# =============================================================================
# Stable Staging Integration Tests
# =============================================================================


@pytest.mark.integration
class TestStableStagingPaths:
    """Integration tests for stable staging directory functionality."""

    def test_staging_directory_created_with_stable_path(self, tmp_path):
        """
        Verify that staging directories are created with stable, predictable paths.

        Test flow:
        1. Create test container with compose file
        2. Run backup
        3. Verify staging directory exists at expected stable path
        4. Verify directory structure is correct
        """
        # Setup: Create temporary directories
        repo_path = tmp_path / "kopia-repo"
        repo_path.mkdir()
        cache_path = tmp_path / "kopia-cache"
        cache_path.mkdir()
        config_path = tmp_path / "config.json"
        compose_dir = tmp_path / "compose"
        compose_dir.mkdir()

        # Create test compose file
        compose_file = compose_dir / "docker-compose.yml"
        compose_file.write_text(
            """version: '3'
services:
  test:
    image: nginx:alpine
    volumes:
      - test_data:/data
volumes:
  test_data:
"""
        )

        # Create test container
        container_name = "kopi_docka_staging_test"
        try:
            # Start container
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    "--label",
                    f"com.docker.compose.project=staging_test",
                    "--label",
                    f"com.docker.compose.project.config_files={compose_file}",
                    "nginx:alpine",
                ],
                capture_output=True,
                check=True,
            )

            # Create test config
            config_content = {
                "kopia": {
                    "kopia_params": f"filesystem --path {repo_path}",
                    "password": "test-staging-password",
                    "profile": "staging-test",
                    "compression": "zstd",
                    "encryption": "AES256-GCM-HMAC-SHA256",
                    "cache_directory": str(cache_path),
                },
                "backup": {
                    "base_path": str(tmp_path / "backup"),
                    "parallel_workers": "1",
                    "stop_timeout": "30",
                    "start_timeout": "60",
                    "backup_scope": "minimal",  # Only recipes, no volumes
                },
                "retention": {
                    "keep_latest": "3",
                },
            }
            config_path.write_text(json.dumps(config_content, indent=2))

            # Initialize config and repository
            config = Config(str(config_path))
            repo = KopiaRepository(config)

            # Initialize Kopia repository
            subprocess.run(
                [
                    "kopia",
                    "repository",
                    "create",
                    "filesystem",
                    "--path",
                    str(repo_path),
                    "--password",
                    "test-staging-password",
                    "--cache-directory",
                    str(cache_path),
                ],
                capture_output=True,
                check=True,
            )

            # Connect to repository
            repo.connect()

            # Create backup manager
            manager = BackupManager(config)

            # Create backup unit manually
            unit = BackupUnit(
                name="staging_test",
                type="stack",
                compose_files=[compose_file],
                containers=[
                    ContainerInfo(
                        id=container_name,
                        name=container_name,
                        image="nginx:alpine",
                        status="running",
                        compose_files=[compose_file],
                    )
                ],
                volumes=[],
            )

            # Mock staging base dir to use temp path for testing
            staging_base = tmp_path / "staging"
            with patch("kopi_docka.cores.backup_manager.STAGING_BASE_DIR", staging_base):
                # Run backup
                manager._backup_recipes(unit, "test-backup-1")

                # Verify staging directory was created with stable path
                expected_staging_dir = staging_base / "recipes" / "staging_test"
                assert expected_staging_dir.exists(), "Staging directory should exist"
                assert expected_staging_dir.is_dir(), "Staging path should be a directory"

                # Verify compose file was copied to staging directory
                staged_compose = expected_staging_dir / "docker-compose.yml"
                assert staged_compose.exists(), "Compose file should be in staging directory"

        finally:
            # Cleanup
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
            )
            # Disconnect from repository
            try:
                subprocess.run(
                    ["kopia", "repository", "disconnect"],
                    capture_output=True,
                )
            except Exception:
                pass

    def test_staging_directory_reused_across_backups(self, tmp_path):
        """
        Verify that the same staging directory is reused for multiple backups.

        Test flow:
        1. Run first backup → staging dir created
        2. Capture staging dir path and inode
        3. Run second backup → same dir reused (not recreated)
        4. Verify directory contents were cleared and refreshed
        """
        # Setup: Create temporary directories
        repo_path = tmp_path / "kopia-repo"
        repo_path.mkdir()
        cache_path = tmp_path / "kopia-cache"
        cache_path.mkdir()
        config_path = tmp_path / "config.json"
        compose_dir = tmp_path / "compose"
        compose_dir.mkdir()

        # Create test compose file
        compose_file = compose_dir / "docker-compose.yml"
        compose_file.write_text("version: '3'\nservices:\n  app:\n    image: alpine\n")

        # Create test container
        container_name = "kopi_docka_reuse_test"
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    "--label",
                    f"com.docker.compose.project=reuse_test",
                    "--label",
                    f"com.docker.compose.project.config_files={compose_file}",
                    "alpine",
                    "sleep",
                    "300",
                ],
                capture_output=True,
                check=True,
            )

            # Create test config
            config_content = {
                "kopia": {
                    "kopia_params": f"filesystem --path {repo_path}",
                    "password": "test-reuse-password",
                    "profile": "reuse-test",
                    "compression": "zstd",
                    "encryption": "AES256-GCM-HMAC-SHA256",
                    "cache_directory": str(cache_path),
                },
                "backup": {
                    "base_path": str(tmp_path / "backup"),
                    "parallel_workers": "1",
                    "stop_timeout": "30",
                    "start_timeout": "60",
                    "backup_scope": "minimal",
                },
                "retention": {"keep_latest": "3"},
            }
            config_path.write_text(json.dumps(config_content, indent=2))

            # Initialize repository
            subprocess.run(
                [
                    "kopia",
                    "repository",
                    "create",
                    "filesystem",
                    "--path",
                    str(repo_path),
                    "--password",
                    "test-reuse-password",
                    "--cache-directory",
                    str(cache_path),
                ],
                capture_output=True,
                check=True,
            )

            # Initialize config and manager
            config = Config(str(config_path))
            repo = KopiaRepository(config)
            repo.connect()
            manager = BackupManager(config)

            # Create backup unit
            unit = BackupUnit(
                name="reuse_test",
                type="stack",
                compose_files=[compose_file],
                containers=[
                    ContainerInfo(
                        id=container_name,
                        name=container_name,
                        image="alpine",
                        status="running",
                        compose_files=[compose_file],
                    )
                ],
                volumes=[],
            )

            # Mock staging base dir
            staging_base = tmp_path / "staging"
            expected_staging_dir = staging_base / "recipes" / "reuse_test"

            with patch("kopi_docka.cores.backup_manager.STAGING_BASE_DIR", staging_base):
                # First backup
                manager._backup_recipes(unit, "backup-1")
                assert expected_staging_dir.exists()

                # Record directory inode (to verify it's the same directory)
                inode_1 = expected_staging_dir.stat().st_ino

                # Modify compose file to create different content
                compose_file.write_text(
                    "version: '3'\nservices:\n  app:\n    image: alpine:latest\n"
                )

                # Second backup
                time.sleep(0.5)  # Small delay to ensure timestamp difference
                manager._backup_recipes(unit, "backup-2")

                # Verify same directory used (same inode)
                assert expected_staging_dir.exists()
                inode_2 = expected_staging_dir.stat().st_ino
                assert inode_1 == inode_2, "Same directory should be reused (same inode)"

                # Verify new content was staged
                staged_compose = expected_staging_dir / "docker-compose.yml"
                content = staged_compose.read_text()
                assert (
                    "alpine:latest" in content
                ), "Updated compose file should be in staging directory"

        finally:
            # Cleanup
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
            try:
                subprocess.run(["kopia", "repository", "disconnect"], capture_output=True)
            except Exception:
                pass

    def test_snapshots_have_consistent_source_paths(self, tmp_path):
        """
        Verify that snapshots from multiple backups have consistent source paths.

        This is critical for retention policies to work - Kopia must see all
        backups as coming from the same source path.

        Test flow:
        1. Run backup #1
        2. Run backup #2
        3. List snapshots
        4. Verify both snapshots have identical source paths (stable staging dir)
        """
        # Setup
        repo_path = tmp_path / "kopia-repo"
        repo_path.mkdir()
        cache_path = tmp_path / "kopia-cache"
        cache_path.mkdir()
        config_path = tmp_path / "config.json"
        compose_dir = tmp_path / "compose"
        compose_dir.mkdir()

        # Create compose file
        compose_file = compose_dir / "docker-compose.yml"
        compose_file.write_text("version: '3'\nservices:\n  web:\n    image: nginx:alpine\n")

        container_name = "kopi_docka_path_test"
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    "--label",
                    "com.docker.compose.project=path_test",
                    "--label",
                    f"com.docker.compose.project.config_files={compose_file}",
                    "nginx:alpine",
                ],
                capture_output=True,
                check=True,
            )

            # Create config
            config_content = {
                "kopia": {
                    "kopia_params": f"filesystem --path {repo_path}",
                    "password": "test-path-password",
                    "profile": "path-test",
                    "compression": "zstd",
                    "encryption": "AES256-GCM-HMAC-SHA256",
                    "cache_directory": str(cache_path),
                },
                "backup": {
                    "base_path": str(tmp_path / "backup"),
                    "parallel_workers": "1",
                    "stop_timeout": "30",
                    "start_timeout": "60",
                    "backup_scope": "minimal",
                },
                "retention": {"keep_latest": "5"},
            }
            config_path.write_text(json.dumps(config_content, indent=2))

            # Initialize repository
            subprocess.run(
                [
                    "kopia",
                    "repository",
                    "create",
                    "filesystem",
                    "--path",
                    str(repo_path),
                    "--password",
                    "test-path-password",
                    "--cache-directory",
                    str(cache_path),
                ],
                capture_output=True,
                check=True,
            )

            # Setup config and manager
            config = Config(str(config_path))
            repo = KopiaRepository(config)
            repo.connect()
            manager = BackupManager(config)

            unit = BackupUnit(
                name="path_test",
                type="stack",
                compose_files=[compose_file],
                containers=[
                    ContainerInfo(
                        id=container_name,
                        name=container_name,
                        image="nginx:alpine",
                        status="running",
                        compose_files=[compose_file],
                    )
                ],
                volumes=[],
            )

            staging_base = tmp_path / "staging"
            expected_path = str(staging_base / "recipes" / "path_test")

            with patch("kopi_docka.cores.backup_manager.STAGING_BASE_DIR", staging_base):
                # Create two backups
                snapshot_id_1 = manager._backup_recipes(unit, "backup-1")
                time.sleep(1)
                snapshot_id_2 = manager._backup_recipes(unit, "backup-2")

                assert snapshot_id_1 is not None, "First snapshot should be created"
                assert snapshot_id_2 is not None, "Second snapshot should be created"

                # List all snapshots
                result = subprocess.run(
                    ["kopia", "snapshot", "list", "--json"],
                    capture_output=True,
                    check=True,
                    text=True,
                )

                snapshots = json.loads(result.stdout)

                # Find our snapshots by tags
                our_snapshots = [
                    s for s in snapshots if s.get("tags", {}).get("unit") == "path_test"
                ]

                assert len(our_snapshots) >= 2, "Should have at least 2 snapshots"

                # Extract source paths
                paths = [s["source"]["path"] for s in our_snapshots]

                # Verify all paths are identical
                assert (
                    len(set(paths)) == 1
                ), f"All snapshots should have same source path, got: {set(paths)}"
                assert (
                    paths[0] == expected_path
                ), f"Source path should be stable staging dir: {expected_path}"

        finally:
            # Cleanup
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
            try:
                subprocess.run(["kopia", "repository", "disconnect"], capture_output=True)
            except Exception:
                pass
