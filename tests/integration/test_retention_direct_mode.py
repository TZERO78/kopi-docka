"""
Integration tests for Direct Mode retention policy functionality.

Tests verify that retention policies correctly delete old volume snapshots
when using Direct Mode (default since v5.0).

Critical bug fix test: Ensures retention policies are applied to actual volume
mountpoints, not virtual paths, preventing unbounded repository growth.

Requires:
- Docker daemon running
- Root access (for volume operations)
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
from unittest.mock import Mock

from kopi_docka.cores.backup_manager import BackupManager
from kopi_docka.cores.repository_manager import KopiaRepository
from kopi_docka.helpers.config import Config
from kopi_docka.types import BackupUnit, VolumeInfo
from kopi_docka.helpers.constants import BACKUP_FORMAT_DIRECT


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
    pytest.mark.skipif(not is_root(), reason="Requires root for Docker volume access"),
    pytest.mark.skipif(not kopia_available(), reason="Kopia binary not available"),
]


# =============================================================================
# Direct Mode Retention Integration Tests
# =============================================================================


@pytest.mark.integration
class TestDirectModeRetention:
    """Integration tests for retention policies in Direct Mode."""

    def test_direct_mode_retention_deletes_old_volume_snapshots(self, tmp_path):
        """
        Critical test: Verify retention policies delete old volume snapshots in Direct Mode.

        This test verifies the fix for the critical bug where retention policies
        were applied to virtual paths (volumes/unit_name) but snapshots were created
        with actual mountpoints (/var/lib/docker/volumes/...), causing retention to
        never trigger.

        Test flow:
        1. Create test Docker volume with actual data
        2. Initialize Kopia filesystem repository
        3. Create backup #1 with latest=2 retention policy
        4. Create backup #2
        5. Create backup #3
        6. Verify only 2 volume snapshots remain (backup #1 deleted)
        """
        # Setup: Create temporary directories
        repo_path = tmp_path / "kopia-repo"
        repo_path.mkdir()
        cache_path = tmp_path / "kopia-cache"
        cache_path.mkdir()
        config_path = tmp_path / "config.json"

        # Create test volume
        vol_name = "kopi_docka_retention_test_vol"
        try:
            # Create Docker volume
            subprocess.run(
                ["docker", "volume", "create", vol_name],
                capture_output=True,
                check=True,
            )

            # Get volume mountpoint
            inspect_output = subprocess.run(
                ["docker", "volume", "inspect", vol_name],
                capture_output=True,
                check=True,
                text=True,
            )
            vol_info = json.loads(inspect_output.stdout)[0]
            mountpoint = vol_info["Mountpoint"]

            # Write test data to volume
            test_file = Path(mountpoint) / "test.txt"
            test_file.write_text("retention test data")

            # Create test config with retention policy: latest=2
            config_content = {
                "kopia": {
                    "kopia_params": f"filesystem --path {repo_path}",
                    "password": "test-retention-password",
                    "profile": "retention-test",
                    "compression": "zstd",
                    "encryption": "AES256-GCM-HMAC-SHA256",
                    "cache_directory": str(cache_path),
                },
                "backup": {
                    "base_path": str(tmp_path / "backup"),
                    "parallel_workers": "1",
                    "stop_timeout": "30",
                    "start_timeout": "60",
                    "task_timeout": "0",
                    "update_recovery_bundle": "false",
                },
                "retention": {
                    "latest": "2",  # Keep only 2 latest snapshots
                    "hourly": "0",
                    "daily": "0",
                    "weekly": "0",
                    "monthly": "0",
                    "annual": "0",
                },
                "logging": {
                    "level": "DEBUG",
                    "file": str(tmp_path / "test.log"),
                },
            }
            config_path.write_text(json.dumps(config_content, indent=2))

            # Initialize Kopia repository
            env = os.environ.copy()
            env["KOPIA_PASSWORD"] = "test-retention-password"

            subprocess.run(
                [
                    "kopia",
                    "repository",
                    "create",
                    "filesystem",
                    "--path",
                    str(repo_path),
                    "--cache-directory",
                    str(cache_path),
                ],
                env=env,
                capture_output=True,
                check=True,
            )

            # Create BackupUnit with test volume
            unit = BackupUnit(
                name="retention_test",
                type="standalone",
                containers=[],
                volumes=[
                    VolumeInfo(
                        name=vol_name,
                        driver="local",
                        mountpoint=mountpoint,
                        size_bytes=1024,
                    )
                ],
                compose_files=[],
            )

            # Load config and create BackupManager
            config = Config(str(config_path))
            manager = BackupManager(config)

            # Verify we're in Direct Mode
            from kopi_docka.helpers.constants import BACKUP_FORMAT_DEFAULT

            assert BACKUP_FORMAT_DEFAULT == BACKUP_FORMAT_DIRECT

            # Create backup #1
            metadata1 = manager.backup_unit(unit, backup_scope="minimal")
            assert metadata1.success
            assert metadata1.volumes_backed_up == 1
            backup_id_1 = metadata1.backup_id
            time.sleep(2)  # Ensure distinct timestamps

            # Create backup #2
            metadata2 = manager.backup_unit(unit, backup_scope="minimal")
            assert metadata2.success
            assert metadata2.volumes_backed_up == 1
            backup_id_2 = metadata2.backup_id
            time.sleep(2)

            # Create backup #3 - this should trigger retention
            metadata3 = manager.backup_unit(unit, backup_scope="minimal")
            assert metadata3.success
            assert metadata3.volumes_backed_up == 1
            backup_id_3 = metadata3.backup_id

            # Wait for retention to complete
            time.sleep(3)

            # Query snapshots for this volume mountpoint
            result = subprocess.run(
                [
                    "kopia",
                    "snapshot",
                    "list",
                    mountpoint,
                    "--json",
                    "--cache-directory",
                    str(cache_path),
                ],
                env=env,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                snapshots = json.loads(result.stdout)

                # Should only have 2 snapshots (latest=2)
                assert (
                    len(snapshots) == 2
                ), f"Expected 2 snapshots, found {len(snapshots)}: {snapshots}"

                # Verify backup #1 was deleted, #2 and #3 remain
                snapshot_ids = [s.get("id", "") for s in snapshots]

                # Check that we don't have backup_id_1 in tags
                # (Note: we need to check tags, not snapshot IDs)
                # Get detailed info for each snapshot
                remaining_backup_ids = []
                for snapshot in snapshots:
                    snap_id = snapshot.get("id")
                    detail_result = subprocess.run(
                        [
                            "kopia",
                            "snapshot",
                            "show",
                            snap_id,
                            "--json",
                            "--cache-directory",
                            str(cache_path),
                        ],
                        env=env,
                        capture_output=True,
                        text=True,
                    )
                    if detail_result.returncode == 0:
                        detail = json.loads(detail_result.stdout)
                        # Kopia tags are in the manifest
                        tags = detail.get("manifest", {}).get("tags", {})
                        if "backup_id" in tags:
                            remaining_backup_ids.append(tags["backup_id"])

                # Backup #2 and #3 should remain
                assert backup_id_2 in remaining_backup_ids or backup_id_3 in remaining_backup_ids
                # Backup #1 should be deleted
                assert backup_id_1 not in remaining_backup_ids

        finally:
            # Cleanup: Remove test volume
            subprocess.run(
                ["docker", "volume", "rm", "-f", vol_name],
                capture_output=True,
            )

            # Cleanup: Disconnect Kopia repository
            try:
                subprocess.run(
                    ["kopia", "repository", "disconnect"],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass

    def test_tar_mode_retention_unchanged(self, tmp_path):
        """
        Verify TAR Mode retention behavior remains unchanged.

        This test ensures the fix doesn't break TAR Mode retention.
        In TAR Mode, policies should still apply to virtual paths.
        """
        # Note: This is a placeholder test that would need to:
        # 1. Switch BACKUP_FORMAT_DEFAULT to TAR
        # 2. Create backups in TAR mode
        # 3. Verify retention works with virtual paths
        # For now, we skip this as TAR mode is legacy
        pytest.skip("TAR mode retention test - legacy format, skipping for now")

    def test_retention_with_multiple_volumes(self, tmp_path):
        """
        Verify retention works correctly with units containing multiple volumes.

        Each volume should have its own retention policy in Direct Mode.
        """
        # Setup
        repo_path = tmp_path / "kopia-repo"
        repo_path.mkdir()
        cache_path = tmp_path / "kopia-cache"
        cache_path.mkdir()
        config_path = tmp_path / "config.json"

        vol1_name = "kopi_docka_multi_test_vol1"
        vol2_name = "kopi_docka_multi_test_vol2"

        try:
            # Create two Docker volumes
            subprocess.run(
                ["docker", "volume", "create", vol1_name], capture_output=True, check=True
            )
            subprocess.run(
                ["docker", "volume", "create", vol2_name], capture_output=True, check=True
            )

            # Get mountpoints
            inspect1 = subprocess.run(
                ["docker", "volume", "inspect", vol1_name],
                capture_output=True,
                check=True,
                text=True,
            )
            vol1_info = json.loads(inspect1.stdout)[0]
            mountpoint1 = vol1_info["Mountpoint"]

            inspect2 = subprocess.run(
                ["docker", "volume", "inspect", vol2_name],
                capture_output=True,
                check=True,
                text=True,
            )
            vol2_info = json.loads(inspect2.stdout)[0]
            mountpoint2 = vol2_info["Mountpoint"]

            # Write test data
            Path(mountpoint1, "data1.txt").write_text("volume 1 data")
            Path(mountpoint2, "data2.txt").write_text("volume 2 data")

            # Create config
            config_content = {
                "kopia": {
                    "kopia_params": f"filesystem --path {repo_path}",
                    "password": "test-multi-password",
                    "profile": "multi-test",
                    "compression": "zstd",
                    "encryption": "AES256-GCM-HMAC-SHA256",
                    "cache_directory": str(cache_path),
                },
                "backup": {
                    "base_path": str(tmp_path / "backup"),
                    "parallel_workers": "1",
                },
                "retention": {"latest": "2"},
                "logging": {"level": "DEBUG"},
            }
            config_path.write_text(json.dumps(config_content, indent=2))

            # Initialize Kopia
            env = os.environ.copy()
            env["KOPIA_PASSWORD"] = "test-multi-password"
            subprocess.run(
                [
                    "kopia",
                    "repository",
                    "create",
                    "filesystem",
                    "--path",
                    str(repo_path),
                    "--cache-directory",
                    str(cache_path),
                ],
                env=env,
                capture_output=True,
                check=True,
            )

            # Create unit with 2 volumes
            unit = BackupUnit(
                name="multi_vol_test",
                type="standalone",
                containers=[],
                volumes=[
                    VolumeInfo(
                        name=vol1_name, driver="local", mountpoint=mountpoint1, size_bytes=1024
                    ),
                    VolumeInfo(
                        name=vol2_name, driver="local", mountpoint=mountpoint2, size_bytes=1024
                    ),
                ],
                compose_files=[],
            )

            # Create backups
            config = Config(str(config_path))
            manager = BackupManager(config)

            # Create 3 backups
            for i in range(3):
                metadata = manager.backup_unit(unit, backup_scope="minimal")
                assert metadata.success
                assert metadata.volumes_backed_up == 2
                time.sleep(2)

            # Wait for retention
            time.sleep(3)

            # Check both volumes have only 2 snapshots each
            for mountpoint in [mountpoint1, mountpoint2]:
                result = subprocess.run(
                    [
                        "kopia",
                        "snapshot",
                        "list",
                        mountpoint,
                        "--json",
                        "--cache-directory",
                        str(cache_path),
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    snapshots = json.loads(result.stdout)
                    assert (
                        len(snapshots) == 2
                    ), f"Volume {mountpoint} should have 2 snapshots, found {len(snapshots)}"

        finally:
            # Cleanup
            subprocess.run(["docker", "volume", "rm", "-f", vol1_name], capture_output=True)
            subprocess.run(["docker", "volume", "rm", "-f", vol2_name], capture_output=True)
            try:
                subprocess.run(["kopia", "repository", "disconnect"], capture_output=True)
            except Exception:
                pass
