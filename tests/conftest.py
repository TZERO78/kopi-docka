"""
Shared pytest fixtures for Kopi-Docka tests.

Provides common fixtures for mocking, temporary files, and test data.
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from typer.testing import CliRunner


@pytest.fixture
def cli_runner():
    """Typer CLI runner for testing commands."""
    return CliRunner()


@pytest.fixture
def tmp_config(tmp_path):
    """Create a temporary kopi-docka config file."""
    import json

    config_content = {
        "kopia": {
            "kopia_params": "filesystem --path /tmp/test-repo",
            "password": "test-password-123",
            "profile": "test-profile",
            "compression": "zstd",
            "encryption": "AES256-GCM-HMAC-SHA256",
            "cache_directory": "/tmp/kopia-cache",
        },
        "backup": {
            "base_path": "/tmp/kopi-test",
            "parallel_workers": "2",
            "stop_timeout": "30",
            "start_timeout": "60",
            "database_backup": "true",
            "task_timeout": "0",
            "update_recovery_bundle": "false",
            "recovery_bundle_path": "/tmp/recovery",
            "recovery_bundle_retention": "3",
            "exclude_patterns": "",
        },
        "docker": {
            "socket": "/var/run/docker.sock",
            "compose_timeout": "300",
            "prune_stopped_containers": "false",
        },
        "retention": {"daily": "7", "weekly": "4", "monthly": "12", "yearly": "5"},
        "logging": {
            "level": "INFO",
            "file": "/tmp/kopi-docka.log",
            "max_size_mb": "100",
            "backup_count": "5",
        },
    }

    config_file = tmp_path / "test-config.json"
    config_file.write_text(json.dumps(config_content, indent=2))
    return config_file


@pytest.fixture
def mock_root():
    """Mock os.geteuid() to return 0 (root)."""
    with patch("os.geteuid", return_value=0):
        yield


@pytest.fixture
def mock_non_root():
    """Mock os.geteuid() to return non-zero (not root)."""
    with patch("os.geteuid", return_value=1000):
        yield


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for external commands."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        yield mock_run


@pytest.fixture
def mock_docker_inspect():
    """Mock Docker inspect output for a container."""
    return {
        "Id": "abc123",
        "Name": "test-container",
        "State": {"Running": True},
        "Config": {"Image": "nginx:latest", "Labels": {}},
        "Mounts": [
            {
                "Type": "volume",
                "Name": "test-volume",
                "Source": "/var/lib/docker/volumes/test-volume/_data",
                "Destination": "/data",
            }
        ],
    }


@pytest.fixture
def mock_backup_unit():
    """Create a sample BackupUnit for testing."""
    from kopi_docka.types import BackupUnit, ContainerInfo, VolumeInfo

    container = ContainerInfo(
        id="abc123",
        name="test-container",
        image="nginx:latest",
        status="running",  # Fixed: use status instead of is_running
        labels={},
    )

    volume = VolumeInfo(
        name="test-volume",
        driver="local",
        mountpoint="/var/lib/docker/volumes/test-volume/_data",  # Fixed: mountpoint not mount_point
        size_bytes=1024 * 1024,  # 1 MB
    )

    unit = BackupUnit(
        name="test-unit",
        type="standalone",
        containers=[container],
        volumes=[volume],
        compose_files=[],
    )

    return unit


@pytest.fixture
def mock_kopia_connected():
    """Mock Kopia repository as connected."""
    with patch(
        "kopi_docka.cores.repository_manager.KopiaRepository.is_connected", return_value=True
    ):
        yield


@pytest.fixture
def mock_kopia_status():
    """Mock Kopia repository status output."""
    return {
        "config": {"hostname": "test-host", "username": "test-user"},
        "storage": {"type": "filesystem", "config": {"path": "/tmp/test-repo"}},
    }


@pytest.fixture
def mock_docker_client():
    """Mock Docker client for container operations."""
    mock_client = MagicMock()
    mock_client.containers.list.return_value = []
    mock_client.volumes.list.return_value = []

    with patch("docker.from_env", return_value=mock_client):
        yield mock_client


@pytest.fixture
def sample_snapshots():
    """Sample Kopia snapshots for testing."""
    return [
        {
            "id": "snap1",
            "source": {"host": "test-host", "userName": "root", "path": "/backup"},
            "startTime": "2025-01-01T00:00:00Z",
            "endTime": "2025-01-01T00:05:00Z",
            "tags": {"unit": "test-unit"},
        },
        {
            "id": "snap2",
            "source": {"host": "test-host", "userName": "root", "path": "/backup"},
            "startTime": "2025-01-02T00:00:00Z",
            "endTime": "2025-01-02T00:05:00Z",
            "tags": {"unit": "test-unit"},
        },
    ]


@pytest.fixture
def mock_ctx(tmp_config):
    """Create mock Typer context with config.

    Use this for direct function tests instead of cli_runner.invoke().
    """
    from kopi_docka.helpers.config import Config

    ctx = MagicMock()
    ctx.obj = {"config": Config(tmp_config)}
    return ctx


@pytest.fixture
def mock_backup_config(tmp_path):
    """Create a mock Config object for BackupManager testing."""
    config = Mock()
    config.parallel_workers = 2
    config.getint.return_value = 30  # Default timeout
    config.getlist.return_value = []  # No exclude patterns
    config.getboolean.return_value = False  # No DR bundle
    config.backup_base_path = tmp_path / "kopi-docka-test"
    return config


@pytest.fixture
def mock_kopia_config():
    """Create a mock Config object for KopiaRepository testing."""
    config = Mock()
    config.get.return_value = "filesystem --path /backup/repo"
    config.kopia_profile = "kopi-docka"
    config.get_password.return_value = "test-password"
    config.kopia_cache_directory = "/tmp/kopia-cache"
    config.kopia_cache_size_mb = 500
    return config


@pytest.fixture
def backup_unit_factory():
    """Factory fixture to create BackupUnit instances for testing.

    Usage:
        def test_something(backup_unit_factory):
            unit = backup_unit_factory(name="mystack", containers=2, volumes=1)
    """
    from kopi_docka.types import BackupUnit, ContainerInfo, VolumeInfo

    def _make_backup_unit(
        name: str = "mystack",
        containers: int = 2,
        volumes: int = 1,
        with_database: bool = False,
    ) -> BackupUnit:
        container_list = []
        for i in range(containers):
            c = ContainerInfo(
                id=f"container{i}",
                name=f"{name}_service{i}",
                image="nginx:latest" if not with_database or i > 0 else "postgres:15",
                status="running",
                database_type="postgres" if with_database and i == 0 else None,
                inspect_data={"NetworkSettings": {"Networks": {"mynet": {}}}},
            )
            container_list.append(c)

        volume_list = []
        for i in range(volumes):
            v = VolumeInfo(
                name=f"{name}_data{i}",
                driver="local",
                mountpoint=f"/var/lib/docker/volumes/{name}_data{i}/_data",
                size_bytes=1024 * 1024,
            )
            volume_list.append(v)

        return BackupUnit(
            name=name,
            type="stack",
            containers=container_list,
            volumes=volume_list,
            compose_files=[],
        )

    return _make_backup_unit
