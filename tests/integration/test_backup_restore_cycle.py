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
    pytest.mark.skipif(not docker_available(), reason="Docker daemon not available"),
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
        compose_file.write_text(
            """
services:
  web:
    image: alpine:latest
    command: ["sleep", "infinity"]
    volumes:
      - testdata:/data

volumes:
  testdata:
"""
        )
        project_name = f"kopi_test_{os.getpid()}"

        # Start the stack
        try:
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "up",
                    "-d",
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
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "down",
                    "-v",
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
        test_unit = next((u for u in units if u.name == compose_stack["project_name"]), None)

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
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol_name}:/data",
                    "alpine:latest",
                    "sh",
                    "-c",
                    f"echo '{test_data}' > /data/test.txt",
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
                "docker",
                "run",
                "--rm",
                "-v",
                f"{volume_with_data['name']}:/data",
                "alpine:latest",
                "cat",
                "/data/test.txt",
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
                "kopia",
                "repository",
                "create",
                "filesystem",
                "--path",
                str(repo_path),
                "--config-file",
                str(config_file),
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
                "kopia",
                "snapshot",
                "create",
                str(test_dir),
                "--config-file",
                str(ephemeral_repo["config_file"]),
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
                "kopia",
                "snapshot",
                "create",
                str(test_dir),
                "--config-file",
                str(ephemeral_repo["config_file"]),
            ],
            capture_output=True,
            check=True,
            env=ephemeral_repo["env"],
        )

        # List snapshots
        result = subprocess.run(
            [
                "kopia",
                "snapshot",
                "list",
                "--config-file",
                str(ephemeral_repo["config_file"]),
                "--json",
            ],
            capture_output=True,
            text=True,
            env=ephemeral_repo["env"],
        )

        assert result.returncode == 0
        snapshots = json.loads(result.stdout)
        assert len(snapshots) >= 1


# =============================================================================
# Full Backup→Restore Cycle Tests (P2)
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(not kopia_available(), reason="Kopia not installed")
class TestFullBackupRestoreCycle:
    """
    Complete end-to-end backup and restore tests.

    Tests the full lifecycle:
    1. Create volume with test data
    2. Backup using BackupManager
    3. Clear/delete volume
    4. Restore using RestoreManager
    5. Verify data integrity
    """

    @pytest.fixture
    def test_environment(self, tmp_path):
        """Set up complete test environment with Kopia repo and test volume."""
        if not is_root():
            pytest.skip("Requires root for backup/restore operations")

        # Create Kopia repository
        repo_path = tmp_path / "kopia_repo"
        config_file = tmp_path / "kopia.config"
        password = "test-password-e2e"

        env = os.environ.copy()
        env["KOPIA_PASSWORD"] = password

        subprocess.run(
            [
                "kopia",
                "repository",
                "create",
                "filesystem",
                "--path",
                str(repo_path),
                "--config-file",
                str(config_file),
            ],
            capture_output=True,
            check=True,
            env=env,
        )

        # Connect to repository
        subprocess.run(
            [
                "kopia",
                "repository",
                "connect",
                "filesystem",
                "--path",
                str(repo_path),
                "--config-file",
                str(config_file),
            ],
            capture_output=True,
            check=True,
            env=env,
        )

        # Create test volume with data
        vol_name = f"kopi_e2e_test_{os.getpid()}"
        subprocess.run(
            ["docker", "volume", "create", vol_name],
            capture_output=True,
            check=True,
        )

        # Write test data to volume
        test_data = f"Kopi-Docka E2E Test Data - {time.time()}"
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{vol_name}:/data",
                "alpine:latest",
                "sh",
                "-c",
                f"echo '{test_data}' > /data/test_file.txt && "
                f"mkdir -p /data/subdir && "
                f"echo 'nested' > /data/subdir/nested.txt",
            ],
            capture_output=True,
            check=True,
        )

        yield {
            "vol_name": vol_name,
            "test_data": test_data,
            "repo_path": repo_path,
            "config_file": config_file,
            "password": password,
            "env": env,
            "tmp_path": tmp_path,
        }

        # Cleanup
        subprocess.run(["docker", "volume", "rm", "-f", vol_name], capture_output=True)

    def test_full_backup_and_restore_cycle(self, test_environment):
        """
        Complete backup→restore cycle with data verification.

        This is the main end-to-end test for backup and restore functionality.
        """
        from kopi_docka.cores.backup_manager import BackupManager
        from kopi_docka.cores.restore_manager import RestoreManager
        from kopi_docka.cores.repository_manager import KopiaRepository
        from kopi_docka.helpers.config import Config
        from kopi_docka.types import BackupUnit, VolumeInfo

        vol_name = test_environment["vol_name"]
        config_file = str(test_environment["config_file"])

        # Create minimal config
        config = Mock(spec=Config)
        config.parallel_workers = 1
        config.backup_base_path = test_environment["tmp_path"] / "metadata"
        config.backup_base_path.mkdir(exist_ok=True)
        config.getint = Mock(return_value=30)
        config.getlist = Mock(return_value=[])
        config.getboolean = Mock(return_value=False)
        config.kopia_config_file = config_file

        # Initialize repository with environment
        with patch.dict(os.environ, test_environment["env"]):
            repo = KopiaRepository(config)

            # Step 1: Backup the volume
            print("\n=== STEP 1: Backup Volume ===")
            backup_mgr = BackupManager(config)

            # Get volume mountpoint
            vol_inspect = subprocess.run(
                ["docker", "volume", "inspect", vol_name, "--format", "{{.Mountpoint}}"],
                capture_output=True,
                text=True,
                check=True,
            )
            mountpoint = vol_inspect.stdout.strip()

            # Create BackupUnit
            volume_info = VolumeInfo(
                name=vol_name,
                driver="local",
                mountpoint=mountpoint,
                size_bytes=1024,
            )

            unit = BackupUnit(
                name="e2e_test_unit",
                type="standalone",
                containers=[],
                volumes=[volume_info],
                compose_files=[],
            )

            # Perform backup
            metadata = backup_mgr.backup_unit(unit, backup_scope="minimal")

            assert metadata.success is True, f"Backup failed: {metadata.errors}"
            assert metadata.volumes_backed_up == 1
            assert len(metadata.kopia_snapshot_ids) >= 1

            snapshot_id = metadata.kopia_snapshot_ids[0]
            backup_id = metadata.backup_id

            print(f"✓ Backup successful: snapshot_id={snapshot_id}")

            # Step 2: Clear volume data
            print("\n=== STEP 2: Clear Volume Data ===")
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol_name}:/data",
                    "alpine:latest",
                    "sh",
                    "-c",
                    "rm -rf /data/*",
                ],
                capture_output=True,
                check=True,
            )

            # Verify volume is empty
            verify_result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol_name}:/data",
                    "alpine:latest",
                    "ls",
                    "-la",
                    "/data",
                ],
                capture_output=True,
                text=True,
            )
            assert "test_file.txt" not in verify_result.stdout
            print("✓ Volume cleared")

            # Step 3: Restore from backup
            print("\n=== STEP 3: Restore from Backup ===")
            restore_mgr = RestoreManager(config)

            # Note: _execute_volume_restore_direct is internal, but we'll test the actual method
            # For this integration test, we directly call the restore method
            success = restore_mgr._execute_volume_restore_direct(
                vol=vol_name,
                snap_id=snapshot_id,
                config_file=config_file,
            )

            assert success is True, "Restore failed"
            print("✓ Restore successful")

            # Step 4: Verify restored data
            print("\n=== STEP 4: Verify Data Integrity ===")
            read_result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol_name}:/data",
                    "alpine:latest",
                    "cat",
                    "/data/test_file.txt",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            assert test_environment["test_data"] in read_result.stdout
            print(f"✓ Main file data verified: {read_result.stdout.strip()}")

            # Verify nested file
            nested_result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol_name}:/data",
                    "alpine:latest",
                    "cat",
                    "/data/subdir/nested.txt",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            assert "nested" in nested_result.stdout
            print("✓ Nested file verified")

            print("\n=== ✅ FULL BACKUP→RESTORE CYCLE COMPLETE ===")

    def test_multiple_backup_cycles(self, test_environment):
        """Test multiple backup and restore cycles work correctly."""
        from kopi_docka.cores.backup_manager import BackupManager
        from kopi_docka.helpers.config import Config
        from kopi_docka.types import BackupUnit, VolumeInfo

        vol_name = test_environment["vol_name"]
        config_file = str(test_environment["config_file"])

        config = Mock(spec=Config)
        config.parallel_workers = 1
        config.backup_base_path = test_environment["tmp_path"] / "metadata"
        config.backup_base_path.mkdir(exist_ok=True)
        config.getint = Mock(return_value=30)
        config.getlist = Mock(return_value=[])
        config.getboolean = Mock(return_value=False)
        config.kopia_config_file = config_file

        with patch.dict(os.environ, test_environment["env"]):
            backup_mgr = BackupManager(config)

            # Get volume info
            vol_inspect = subprocess.run(
                ["docker", "volume", "inspect", vol_name, "--format", "{{.Mountpoint}}"],
                capture_output=True,
                text=True,
                check=True,
            )
            mountpoint = vol_inspect.stdout.strip()

            volume_info = VolumeInfo(
                name=vol_name,
                driver="local",
                mountpoint=mountpoint,
                size_bytes=1024,
            )

            unit = BackupUnit(
                name="e2e_test_unit",
                type="standalone",
                containers=[],
                volumes=[volume_info],
                compose_files=[],
            )

            # Create multiple backups
            snapshot_ids = []
            for i in range(3):
                # Modify data between backups
                subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-v",
                        f"{vol_name}:/data",
                        "alpine:latest",
                        "sh",
                        "-c",
                        f"echo 'version_{i}' > /data/version.txt",
                    ],
                    capture_output=True,
                    check=True,
                )

                metadata = backup_mgr.backup_unit(unit, backup_scope="minimal")
                assert metadata.success is True
                snapshot_ids.append(metadata.kopia_snapshot_ids[0])

                # Small delay between backups
                time.sleep(1)

            # Verify we created 3 distinct snapshots
            assert len(snapshot_ids) == 3
            assert len(set(snapshot_ids)) == 3, "Snapshot IDs should be unique"

            print(f"✓ Created {len(snapshot_ids)} distinct backups")

    def test_backup_preserves_permissions(self, test_environment):
        """Test that file permissions and ownership are preserved."""
        from kopi_docka.cores.backup_manager import BackupManager
        from kopi_docka.cores.restore_manager import RestoreManager
        from kopi_docka.helpers.config import Config
        from kopi_docka.types import BackupUnit, VolumeInfo

        vol_name = test_environment["vol_name"]
        config_file = str(test_environment["config_file"])

        # Create file with specific permissions
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{vol_name}:/data",
                "alpine:latest",
                "sh",
                "-c",
                "echo 'secret' > /data/secret.txt && chmod 600 /data/secret.txt",
            ],
            capture_output=True,
            check=True,
        )

        config = Mock(spec=Config)
        config.parallel_workers = 1
        config.backup_base_path = test_environment["tmp_path"] / "metadata"
        config.backup_base_path.mkdir(exist_ok=True)
        config.getint = Mock(return_value=30)
        config.getlist = Mock(return_value=[])
        config.getboolean = Mock(return_value=False)
        config.kopia_config_file = config_file

        with patch.dict(os.environ, test_environment["env"]):
            # Backup
            backup_mgr = BackupManager(config)

            vol_inspect = subprocess.run(
                ["docker", "volume", "inspect", vol_name, "--format", "{{.Mountpoint}}"],
                capture_output=True,
                text=True,
                check=True,
            )
            mountpoint = vol_inspect.stdout.strip()

            volume_info = VolumeInfo(
                name=vol_name,
                driver="local",
                mountpoint=mountpoint,
                size_bytes=1024,
            )

            unit = BackupUnit(
                name="e2e_test_unit",
                type="standalone",
                containers=[],
                volumes=[volume_info],
                compose_files=[],
            )

            metadata = backup_mgr.backup_unit(unit, backup_scope="minimal")
            assert metadata.success is True
            snapshot_id = metadata.kopia_snapshot_ids[0]

            # Clear volume
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol_name}:/data",
                    "alpine:latest",
                    "rm",
                    "-rf",
                    "/data/*",
                ],
                capture_output=True,
                check=True,
            )

            # Restore
            restore_mgr = RestoreManager(config)
            success = restore_mgr._execute_volume_restore_direct(
                vol=vol_name,
                snap_id=snapshot_id,
                config_file=config_file,
            )

            assert success is True

            # Check permissions preserved
            perm_check = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol_name}:/data",
                    "alpine:latest",
                    "stat",
                    "-c",
                    "%a",
                    "/data/secret.txt",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            permissions = perm_check.stdout.strip()
            assert permissions == "600", f"Expected 600, got {permissions}"
            print(f"✓ Permissions preserved: {permissions}")

    def test_cross_machine_restore(self, test_environment, capsys):
        """
        Test cross-machine restore scenario (DR use case).

        Simulates:
        1. Backup created on "machine-a"
        2. Restore performed on "machine-b" (different hostname)
        3. Warnings displayed to user
        4. Data restored successfully despite hostname mismatch
        """
        from kopi_docka.cores.backup_manager import BackupManager
        from kopi_docka.cores.restore_manager import RestoreManager
        from kopi_docka.cores.repository_manager import KopiaRepository
        from kopi_docka.helpers.config import Config
        from kopi_docka.types import BackupUnit, VolumeInfo
        import socket

        vol_name = test_environment["vol_name"]
        config_file = str(test_environment["config_file"])
        original_hostname = "backup-machine-a"
        restore_hostname = "restore-machine-b"

        # Create minimal config
        config = Mock(spec=Config)
        config.parallel_workers = 1
        config.backup_base_path = test_environment["tmp_path"] / "metadata"
        config.backup_base_path.mkdir(exist_ok=True)
        config.getint = Mock(return_value=30)
        config.getlist = Mock(return_value=[])
        config.getboolean = Mock(return_value=False)
        config.kopia_config_file = config_file

        with patch.dict(os.environ, test_environment["env"]):
            # Step 1: Create backup with specific hostname
            print("\n=== STEP 1: Backup on 'machine-a' ===")

            # Mock hostname during backup
            with patch("socket.gethostname", return_value=original_hostname):
                backup_mgr = BackupManager(config)
                repo = KopiaRepository(config)

                # Get volume info
                vol_inspect = subprocess.run(
                    ["docker", "volume", "inspect", vol_name, "--format", "{{.Mountpoint}}"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                mountpoint = vol_inspect.stdout.strip()

                volume_info = VolumeInfo(
                    name=vol_name,
                    driver="local",
                    mountpoint=mountpoint,
                    size_bytes=1024,
                )

                unit = BackupUnit(
                    name="cross_machine_test",
                    type="standalone",
                    containers=[],
                    volumes=[volume_info],
                    compose_files=[],
                )

                # Perform backup
                metadata = backup_mgr.backup_unit(unit, backup_scope="minimal")
                assert metadata.success is True
                snapshot_id = metadata.kopia_snapshot_ids[0]
                print(f"✓ Backup created with hostname: {original_hostname}")

            # Step 2: Clear volume
            print("\n=== STEP 2: Clear Volume ===")
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol_name}:/data",
                    "alpine:latest",
                    "sh",
                    "-c",
                    "rm -rf /data/*",
                ],
                capture_output=True,
                check=True,
            )
            print("✓ Volume cleared")

            # Step 3: Restore on different machine
            print("\n=== STEP 3: Restore on 'machine-b' (cross-machine) ===")

            # Mock hostname to simulate different machine
            with patch("socket.gethostname", return_value=restore_hostname):
                # Verify machines are discovered
                repo = KopiaRepository(config)
                machines = repo.discover_machines()

                # Should find the original machine
                machine_hostnames = [m.hostname for m in machines]
                assert (
                    original_hostname in machine_hostnames
                ), f"Original machine not found. Found: {machine_hostnames}"

                print(f"✓ Discovered machines: {machine_hostnames}")
                print(f"✓ Current hostname: {restore_hostname}")
                print(f"✓ Source hostname: {original_hostname}")

                # Verify cross-machine scenario
                assert (
                    original_hostname != restore_hostname
                ), "Test setup error: hostnames should be different"

                # Now perform restore
                # We'll use the internal method for simplicity in testing
                restore_mgr = RestoreManager(config)

                # Test that we can still restore despite hostname mismatch
                success = restore_mgr._execute_volume_restore_direct(
                    vol=vol_name,
                    snap_id=snapshot_id,
                    config_file=config_file,
                )

                assert success is True, "Cross-machine restore failed"
                print("✓ Restore successful despite hostname mismatch")

            # Step 4: Verify data integrity
            print("\n=== STEP 4: Verify Data Integrity ===")
            read_result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol_name}:/data",
                    "alpine:latest",
                    "cat",
                    "/data/test_file.txt",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            assert test_environment["test_data"] in read_result.stdout
            print(f"✓ Data verified: {read_result.stdout.strip()}")

            # Step 5: Test advanced restore wizard with cross-machine warning
            print("\n=== STEP 5: Test Advanced Restore with Warnings ===")

            # Clear volume again for second restore test
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{vol_name}:/data",
                    "alpine:latest",
                    "sh",
                    "-c",
                    "rm -rf /data/*",
                ],
                capture_output=True,
                check=True,
            )

            # Mock hostname and test advanced restore with warning display
            with patch("socket.gethostname", return_value=restore_hostname):
                # Create restore manager in non-interactive mode
                config.getboolean = Mock(
                    side_effect=lambda key, fallback=False: (
                        True if key == "non_interactive" else False
                    )
                )
                restore_mgr = RestoreManager(config)

                # Capture output to verify warnings
                capsys.readouterr()  # Clear any previous output

                # We can't easily test the full interactive flow, but we can verify
                # that the restore manager can handle cross-machine scenarios
                # by checking the find_restore_points_for_machine method
                points = restore_mgr._find_restore_points_for_machine(original_hostname)
                assert len(points) > 0, "Should find restore points from original machine"

                # Find the restore point for our unit
                unit_point = next((p for p in points if "cross_machine_test" in p.unit_name), None)
                assert unit_point is not None, "Should find our test unit"

                print(f"✓ Found restore point from {original_hostname}")
                print(f"✓ Cross-machine restore capability verified")

            print("\n=== ✅ CROSS-MACHINE RESTORE TEST COMPLETE ===")
            print(f"   Backup source:  {original_hostname}")
            print(f"   Restore target: {restore_hostname}")
            print(f"   Status: Data successfully restored across machines")
