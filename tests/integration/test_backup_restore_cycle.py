"""
Integration tests for backup/restore cycle.

These tests require Docker to be running and test the actual backup/restore
functionality with real containers and volumes.

Skip these tests if Docker is not available.
"""

import json
import os
import subprocess
import tempfile
import time
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

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


# Check if running as root (required for some backup operations)
def is_root() -> bool:
    """Check if running as root."""
    return os.geteuid() == 0


# Skip all tests in this module if Docker is not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_docker,
    pytest.mark.skipif(
        not docker_available(),
        reason="Docker daemon not available"
    ),
]


# =============================================================================
# Docker Discovery Integration Tests
# =============================================================================


@pytest.mark.integration
class TestDockerDiscoveryIntegration:
    """Integration tests for DockerDiscovery with real Docker."""

    def test_discovers_running_containers(self):
        """Should discover actually running containers."""
        # Skip if not root (discovery needs Docker access)
        if not is_root():
            pytest.skip("Requires root for Docker access")

        from kopi_docka.cores.docker_discovery import DockerDiscovery

        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()

        # Just verify it doesn't crash and returns a list
        assert isinstance(units, list)

    def test_discovers_volumes(self):
        """Should discover Docker volumes."""
        if not is_root():
            pytest.skip("Requires root for Docker access")

        from kopi_docka.cores.docker_discovery import DockerDiscovery

        # Create a test volume
        vol_name = "kopi_docka_test_vol"
        try:
            subprocess.run(
                ["docker", "volume", "create", vol_name],
                capture_output=True,
                check=True,
            )

            discovery = DockerDiscovery()
            # Access the internal method to just get volumes
            volumes = discovery._discover_volumes()

            # Find our test volume
            test_vol = next((v for v in volumes if v.name == vol_name), None)
            assert test_vol is not None
            assert test_vol.driver == "local"

        finally:
            # Cleanup
            subprocess.run(
                ["docker", "volume", "rm", vol_name],
                capture_output=True,
            )


# =============================================================================
# Compose Stack Discovery Tests
# =============================================================================


@pytest.mark.integration
class TestComposeStackDiscovery:
    """Integration tests for discovering Compose stacks."""

    @pytest.fixture
    def compose_stack(self, tmp_path):
        """Create a temporary Compose stack for testing."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("""
services:
  web:
    image: alpine:latest
    command: ["sleep", "infinity"]
    volumes:
      - testdata:/data

volumes:
  testdata:
""")
        project_name = f"kopi_test_{os.getpid()}"

        # Start the stack
        try:
            subprocess.run(
                [
                    "docker", "compose",
                    "-f", str(compose_file),
                    "-p", project_name,
                    "up", "-d",
                ],
                capture_output=True,
                check=True,
                cwd=tmp_path,
            )
            # Wait for container to be running
            time.sleep(2)

            yield {
                "project_name": project_name,
                "compose_file": compose_file,
                "tmp_path": tmp_path,
            }

        finally:
            # Cleanup
            subprocess.run(
                [
                    "docker", "compose",
                    "-f", str(compose_file),
                    "-p", project_name,
                    "down", "-v",
                ],
                capture_output=True,
                cwd=tmp_path,
            )

    def test_discovers_compose_stack(self, compose_stack):
        """Should discover a Compose stack as a single BackupUnit."""
        if not is_root():
            pytest.skip("Requires root for Docker access")

        from kopi_docka.cores.docker_discovery import DockerDiscovery

        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()

        # Find our test stack
        test_unit = next(
            (u for u in units if u.name == compose_stack["project_name"]),
            None
        )

        assert test_unit is not None
        assert test_unit.type == "stack"
        assert len(test_unit.containers) >= 1
        # Should have found the testdata volume
        vol_names = [v.name for v in test_unit.volumes]
        assert any(compose_stack["project_name"] in v for v in vol_names)


# =============================================================================
# Volume Content Tests
# =============================================================================


@pytest.mark.integration
class TestVolumeContent:
    """Tests for backing up and verifying volume content."""

    @pytest.fixture
    def volume_with_data(self):
        """Create a volume with some test data."""
        vol_name = f"kopi_test_data_{os.getpid()}"

        try:
            # Create volume
            subprocess.run(
                ["docker", "volume", "create", vol_name],
                capture_output=True,
                check=True,
            )

            # Add some data to the volume using a temporary container
            test_data = "Hello from kopi-docka test!"
            subprocess.run(
                [
                    "docker", "run", "--rm",
                    "-v", f"{vol_name}:/data",
                    "alpine:latest",
                    "sh", "-c", f"echo '{test_data}' > /data/test.txt",
                ],
                capture_output=True,
                check=True,
            )

            yield {
                "name": vol_name,
                "test_data": test_data,
            }

        finally:
            # Cleanup
            subprocess.run(
                ["docker", "volume", "rm", vol_name],
                capture_output=True,
            )

    def test_volume_data_accessible(self, volume_with_data):
        """Verify test data was written to volume."""
        if not is_root():
            pytest.skip("Requires root for Docker access")

        # Read the data back
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{volume_with_data['name']}:/data",
                "alpine:latest",
                "cat", "/data/test.txt",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert volume_with_data["test_data"] in result.stdout


# =============================================================================
# Network Discovery Tests
# =============================================================================


@pytest.mark.integration
class TestNetworkDiscovery:
    """Tests for discovering Docker networks."""

    @pytest.fixture
    def custom_network(self):
        """Create a custom Docker network for testing."""
        net_name = f"kopi_test_net_{os.getpid()}"

        try:
            subprocess.run(
                ["docker", "network", "create", net_name],
                capture_output=True,
                check=True,
            )

            yield net_name

        finally:
            subprocess.run(
                ["docker", "network", "rm", net_name],
                capture_output=True,
            )

    def test_discovers_custom_network(self, custom_network):
        """Should detect custom networks used by containers."""
        if not is_root():
            pytest.skip("Requires root for Docker access")

        # List networks
        result = subprocess.run(
            ["docker", "network", "ls", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
        )

        assert custom_network in result.stdout


# =============================================================================
# Kopia Repository Tests (if Kopia is installed)
# =============================================================================


def kopia_available() -> bool:
    """Check if Kopia is installed."""
    try:
        result = subprocess.run(
            ["kopia", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not kopia_available(), reason="Kopia not installed")
class TestKopiaIntegration:
    """Integration tests with real Kopia (if available)."""

    @pytest.fixture
    def ephemeral_repo(self, tmp_path):
        """Create an ephemeral Kopia repository for testing."""
        repo_path = tmp_path / "kopia_repo"
        config_file = tmp_path / "kopia.config"
        password = "test-password-123"

        env = os.environ.copy()
        env["KOPIA_PASSWORD"] = password

        # Create repository
        subprocess.run(
            [
                "kopia", "repository", "create", "filesystem",
                "--path", str(repo_path),
                "--config-file", str(config_file),
            ],
            capture_output=True,
            check=True,
            env=env,
        )

        yield {
            "path": repo_path,
            "config_file": config_file,
            "password": password,
            "env": env,
        }

        # Cleanup is automatic via tmp_path

    def test_can_create_snapshot(self, ephemeral_repo, tmp_path):
        """Should be able to create a snapshot in the ephemeral repo."""
        # Create some test data
        test_dir = tmp_path / "data"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("Test content")

        # Create snapshot
        result = subprocess.run(
            [
                "kopia", "snapshot", "create", str(test_dir),
                "--config-file", str(ephemeral_repo["config_file"]),
                "--json",
            ],
            capture_output=True,
            text=True,
            env=ephemeral_repo["env"],
        )

        assert result.returncode == 0
        # Should get JSON output with snapshot ID
        output = json.loads(result.stdout)
        assert "snapshotID" in output or "id" in output

    def test_can_list_snapshots(self, ephemeral_repo, tmp_path):
        """Should be able to list snapshots."""
        # Create a snapshot first
        test_dir = tmp_path / "data"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("Test")

        subprocess.run(
            [
                "kopia", "snapshot", "create", str(test_dir),
                "--config-file", str(ephemeral_repo["config_file"]),
            ],
            capture_output=True,
            check=True,
            env=ephemeral_repo["env"],
        )

        # List snapshots
        result = subprocess.run(
            [
                "kopia", "snapshot", "list",
                "--config-file", str(ephemeral_repo["config_file"]),
                "--json",
            ],
            capture_output=True,
            text=True,
            env=ephemeral_repo["env"],
        )

        assert result.returncode == 0
        snapshots = json.loads(result.stdout)
        assert len(snapshots) >= 1
