"""
Unit tests for DryRunReport class.

Tests the dry run report generation, system info collection, unit analysis,
time estimation, config review, and recovery bundle information display.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
from datetime import timedelta

from kopi_docka.cores.dry_run_manager import DryRunReport
from kopi_docka.types import BackupUnit, ContainerInfo, VolumeInfo


def make_mock_config(tmp_path) -> Mock:
    """Create a mock Config object for dry run testing."""
    config = Mock()
    config.config_file = tmp_path / "test-config.json"
    config.backup_base_path = tmp_path / "backups"
    config.parallel_workers = 2

    # Mock config.get method
    def get_side_effect(section, key, fallback=None):
        values = {
            ("kopia", "kopia_params"): "filesystem --path /tmp/test-repo",
            ("kopia", "compression"): "zstd",
            ("kopia", "encryption"): "AES256-GCM-HMAC-SHA256",
            ("backup", "stop_timeout"): "30",
            ("backup", "start_timeout"): "60",
            ("backup", "recovery_bundle_path"): str(tmp_path / "recovery"),
            ("backup", "recovery_bundle_retention"): "3",
        }
        return values.get((section, key), fallback)

    config.get.side_effect = get_side_effect
    config.getint.return_value = 3
    config.getboolean.return_value = False

    return config


def make_mock_utils() -> Mock:
    """Create a mock SystemUtils object."""
    utils = Mock()
    utils.get_available_ram.return_value = 16.5
    utils.get_cpu_count.return_value = 8
    utils.get_available_disk_space.return_value = 500.0
    utils.check_docker.return_value = True
    utils.check_kopia.return_value = True
    utils.check_tar.return_value = True
    utils.get_docker_version.return_value = (24, 0, 5)
    utils.get_kopia_version.return_value = "0.15.0"
    utils.format_bytes.side_effect = lambda x: f"{x / (1024**3):.2f} GB" if x > 0 else "0 B"
    utils.format_duration.side_effect = lambda x: f"{int(x)}s"
    return utils


# =============================================================================
# DryRunReport Generation Tests
# =============================================================================


@pytest.mark.unit
class TestDryRunReport:
    """Tests for DryRunReport output generation."""

    def test_generate_produces_output(self, backup_unit_factory, tmp_path, capsys):
        """Generate prints formatted report."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory(name="teststack", containers=2, volumes=1)

        report.generate([unit], update_recovery_bundle=False)

        captured = capsys.readouterr()
        output = captured.out

        # Verify report header
        assert "KOPI-DOCKA DRY RUN REPORT" in output
        assert "=" * 70 in output

        # Verify footer
        assert "END OF DRY RUN REPORT" in output
        assert "No changes were made" in output

    def test_system_info_section(self, backup_unit_factory, tmp_path, capsys):
        """System info shows RAM, CPU, workers."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory()

        report.generate([unit])

        captured = capsys.readouterr()
        output = captured.out

        # Verify system info section
        assert "SYSTEM INFORMATION" in output
        assert "Available RAM: 16.50 GB" in output
        assert "CPU Cores: 8" in output
        assert "Parallel Workers: 2" in output
        assert "Backup Path:" in output

        # Verify dependency checks
        assert "DEPENDENCY CHECK" in output
        assert "Docker: ✓ Available" in output
        assert "Kopia: ✓ Available" in output
        assert "Tar: ✓ Available" in output

        # Verify versions
        assert "Docker Version: 24.0.5" in output
        assert "Kopia Version: 0.15.0" in output

    def test_units_summary_section(self, backup_unit_factory, tmp_path, capsys):
        """Units summary shows container/volume counts."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit1 = backup_unit_factory(name="stack1", containers=3, volumes=2)
        unit2 = backup_unit_factory(name="stack2", containers=2, volumes=1)

        report.generate([unit1, unit2])

        captured = capsys.readouterr()
        output = captured.out

        # Verify units summary
        assert "BACKUP UNITS SUMMARY" in output
        assert "Total Units: 2" in output
        assert "Total Containers: 5" in output
        assert "Total Volumes: 3" in output

    def test_unit_analysis_shows_stop_start_order(self, backup_unit_factory, tmp_path, capsys):
        """Each unit shows planned stop/start sequence."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory(name="mystack", containers=3, volumes=2)

        report.generate([unit])

        captured = capsys.readouterr()
        output = captured.out

        # Verify unit analysis
        assert "UNIT: mystack" in output
        assert "Type: stack" in output
        assert "Containers: 3" in output
        assert "Volumes: 2" in output

        # Verify operations sequence
        assert "Operations:" in output
        assert "1. Stop" in output
        assert "2. Backup recipes" in output
        assert "3. Backup" in output
        assert "4. Start" in output

    def test_time_estimates_calculated(self, backup_unit_factory, tmp_path, capsys):
        """Estimates based on volume sizes."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        # Create unit with volumes that have size
        unit = backup_unit_factory(name="bigstack", containers=2, volumes=1)
        unit.volumes[0].size_bytes = 10 * 1024**3  # 10 GB

        report.generate([unit])

        captured = capsys.readouterr()
        output = captured.out

        # Verify time and resource estimates
        assert "TIME AND RESOURCE ESTIMATES" in output
        assert "Estimated Data Size:" in output
        assert "Estimated Total Time:" in output
        assert "Estimated Downtime per Unit:" in output
        assert "Estimated Repository Space Required:" in output

    def test_config_review_section(self, backup_unit_factory, tmp_path, capsys):
        """Config review shows key settings."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory()

        report.generate([unit])

        captured = capsys.readouterr()
        output = captured.out

        # Verify configuration review
        assert "CONFIGURATION REVIEW" in output
        assert "Kopia Params:" in output
        assert "filesystem --path /tmp/test-repo" in output
        assert "Parallel Workers: 2" in output
        assert "Stop Timeout: 30s" in output
        assert "Start Timeout: 60s" in output
        assert "Compression: zstd" in output
        assert "Encryption: AES256-GCM-HMAC-SHA256" in output

    def test_recovery_bundle_info_shown(self, backup_unit_factory, tmp_path, capsys):
        """Recovery bundle section appears when enabled."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory()

        report.generate([unit], update_recovery_bundle=True)

        captured = capsys.readouterr()
        output = captured.out

        # Verify disaster recovery section
        assert "DISASTER RECOVERY" in output
        assert "Recovery Bundle: WILL BE UPDATED" in output
        assert "Location:" in output
        assert "Retention:" in output

        # Verify bundle contents
        assert "Estimated Bundle Contents:" in output
        assert "Kopia repository configuration" in output
        assert "Encryption password" in output
        assert "Recovery automation script" in output

    def test_recovery_bundle_disabled(self, backup_unit_factory, tmp_path, capsys):
        """Recovery bundle section shows disabled state."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory()

        report.generate([unit], update_recovery_bundle=False)

        captured = capsys.readouterr()
        output = captured.out

        # Verify disaster recovery section shows disabled
        assert "DISASTER RECOVERY" in output
        assert "Recovery Bundle: WILL NOT BE UPDATED" in output
        assert "To enable:" in output
        assert "Manual Creation:" in output

    def test_no_changes_message(self, backup_unit_factory, tmp_path, capsys):
        """Report ends with 'no changes made' message."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory()

        report.generate([unit])

        captured = capsys.readouterr()
        output = captured.out

        # Verify no changes message
        assert "No changes were made" in output
        assert "Run without --dry-run to perform actual backup" in output


# =============================================================================
# Time and Resource Estimation Tests
# =============================================================================


@pytest.mark.unit
class TestDryRunEstimates:
    """Tests for time/resource estimation."""

    def test_estimate_with_no_volumes(self, tmp_path):
        """Estimate for unit with no volumes."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        # Create unit with no volumes
        unit = BackupUnit(
            name="empty-unit",
            type="standalone",
            containers=[ContainerInfo(id="c1", name="test", image="nginx", status="running")],
            volumes=[],
            compose_files=[],
        )

        duration = report.estimate_backup_duration(unit)

        # Should have base time + container time, no volume time
        assert duration >= 30  # Base time
        assert duration < 60  # No large volume overhead

    def test_estimate_scales_with_volume_size(self, backup_unit_factory, tmp_path):
        """Larger volumes get longer estimates."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        # Small volume
        small_unit = backup_unit_factory(volumes=1)
        small_unit.volumes[0].size_bytes = 100 * 1024**2  # 100 MB

        # Large volume
        large_unit = backup_unit_factory(volumes=1)
        large_unit.volumes[0].size_bytes = 10 * 1024**3  # 10 GB

        small_duration = report.estimate_backup_duration(small_unit)
        large_duration = report.estimate_backup_duration(large_unit)

        # Large volume should take significantly longer
        assert large_duration > small_duration
        assert large_duration > small_duration * 2  # At least 2x longer

    def test_parallel_workers_affect_estimate(self, backup_unit_factory, tmp_path, capsys):
        """More workers reduce estimated time (implicit in report generation)."""
        config = make_mock_config(tmp_path)
        config.parallel_workers = 4  # More workers

        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory(volumes=4)
        for vol in unit.volumes:
            vol.size_bytes = 1 * 1024**3  # 1 GB each

        report.generate([unit])

        captured = capsys.readouterr()
        output = captured.out

        # Verify parallel workers shown in config
        assert "Parallel Workers: 4" in output


# =============================================================================
# System Information Tests
# =============================================================================


@pytest.mark.unit
class TestSystemInformation:
    """Tests for system information display."""

    def test_missing_dependencies_shown(self, backup_unit_factory, tmp_path, capsys):
        """Missing dependencies are flagged with X."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)

        # Mock missing dependencies
        utils = make_mock_utils()
        utils.check_kopia.return_value = False  # Kopia missing
        report.utils = utils

        unit = backup_unit_factory()

        report.generate([unit])

        captured = capsys.readouterr()
        output = captured.out

        # Verify missing dependency shown
        assert "Docker: ✓ Available" in output
        assert "Kopia: ✗ Missing" in output
        assert "Tar: ✓ Available" in output

    def test_disk_space_warning(self, backup_unit_factory, tmp_path, capsys):
        """Warning shown when disk space insufficient."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)

        # Mock low disk space
        utils = make_mock_utils()
        utils.get_available_disk_space.return_value = 0.1  # Only 0.1 GB available
        report.utils = utils

        # Create large volume
        unit = backup_unit_factory(volumes=1)
        unit.volumes[0].size_bytes = 100 * 1024**3  # 100 GB (very large)

        report.generate([unit])

        captured = capsys.readouterr()
        output = captured.out

        # Verify warning shown
        assert "⚠️" in output or "WARNING" in output.upper()

    def test_docker_version_not_available(self, backup_unit_factory, tmp_path, capsys):
        """Report handles missing Docker version gracefully."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)

        # Mock no Docker version
        utils = make_mock_utils()
        utils.get_docker_version.return_value = None
        report.utils = utils

        unit = backup_unit_factory()

        report.generate([unit])

        captured = capsys.readouterr()
        output = captured.out

        # Should still generate report without Docker version
        assert "SYSTEM INFORMATION" in output
        # Docker version line should not appear
        assert "Docker Version:" not in output


# =============================================================================
# Recovery Bundle Tests
# =============================================================================


@pytest.mark.unit
class TestRecoveryBundleInfo:
    """Tests for disaster recovery bundle information."""

    def test_cloud_repository_detected(self, backup_unit_factory, tmp_path, capsys):
        """Cloud repository triggers special bundle message."""
        config = make_mock_config(tmp_path)

        # Override to return S3 params
        def get_s3(section, key, fallback=None):
            if section == "kopia" and key == "kopia_params":
                return "s3 --bucket my-bucket --region us-east-1"
            return make_mock_config(tmp_path).get(section, key, fallback)

        config.get.side_effect = get_s3

        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory()

        report.generate([unit], update_recovery_bundle=True)

        captured = capsys.readouterr()
        output = captured.out

        # Verify cloud detection message
        assert "Cloud Repository Detected" in output
        assert "reconnection guidance" in output

    def test_existing_bundles_listed(self, backup_unit_factory, tmp_path, capsys):
        """Existing recovery bundles are listed."""
        bundle_dir = tmp_path / "recovery"
        bundle_dir.mkdir()

        # Create fake bundle files
        (bundle_dir / "kopi-docka-recovery-20251201.tar.gz.enc").touch()
        (bundle_dir / "kopi-docka-recovery-20251210.tar.gz.enc").touch()
        (bundle_dir / "kopi-docka-recovery-20251220.tar.gz.enc").touch()

        config = make_mock_config(tmp_path)
        config.get.side_effect = lambda s, k, fallback=None: (
            str(bundle_dir)
            if s == "backup" and k == "recovery_bundle_path"
            else make_mock_config(tmp_path).get(s, k, fallback)
        )

        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory()

        report.generate([unit], update_recovery_bundle=True)

        captured = capsys.readouterr()
        output = captured.out

        # Verify existing bundles shown
        assert "Existing Bundles: 3" in output
        assert "Oldest:" in output
        assert "Newest:" in output

    def test_bundle_rotation_warning(self, backup_unit_factory, tmp_path, capsys):
        """Warning shown when bundles will be rotated."""
        bundle_dir = tmp_path / "recovery"
        bundle_dir.mkdir()

        # Create 5 bundle files (retention is 3, so 2 will be removed)
        for i in range(5):
            (bundle_dir / f"kopi-docka-recovery-2025120{i}.tar.gz.enc").touch()

        config = make_mock_config(tmp_path)
        config.get.side_effect = lambda s, k, fallback=None: (
            str(bundle_dir)
            if s == "backup" and k == "recovery_bundle_path"
            else make_mock_config(tmp_path).get(s, k, fallback)
        )
        config.getint.return_value = 3  # Retention: 3

        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory()

        report.generate([unit], update_recovery_bundle=True)

        captured = capsys.readouterr()
        output = captured.out

        # Verify rotation warning
        assert "Rotation:" in output
        assert "will be removed" in output

    def test_bundle_directory_not_exists(self, backup_unit_factory, tmp_path, capsys):
        """Message shown when bundle directory doesn't exist."""
        bundle_dir = tmp_path / "recovery_nonexistent"

        config = make_mock_config(tmp_path)
        config.get.side_effect = lambda s, k, fallback=None: (
            str(bundle_dir)
            if s == "backup" and k == "recovery_bundle_path"
            else make_mock_config(tmp_path).get(s, k, fallback)
        )

        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory()

        report.generate([unit], update_recovery_bundle=True)

        captured = capsys.readouterr()
        output = captured.out

        # Verify directory warning
        assert "does not exist" in output
        assert "Will be created" in output


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================


@pytest.mark.unit
class TestDryRunEdgeCases:
    """Tests for edge cases in dry run reporting."""

    def test_empty_units_list(self, tmp_path, capsys):
        """Handle empty units list gracefully."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        report.generate([])

        captured = capsys.readouterr()
        output = captured.out

        # Should still produce report
        assert "KOPI-DOCKA DRY RUN REPORT" in output
        assert "Total Units: 0" in output

    def test_unit_with_no_running_containers(self, tmp_path, capsys):
        """Handle unit with all stopped containers."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = BackupUnit(
            name="stopped-unit",
            type="standalone",
            containers=[ContainerInfo(id="c1", name="stopped", image="nginx", status="exited")],
            volumes=[],
            compose_files=[],
        )

        report.generate([unit])

        captured = capsys.readouterr()
        output = captured.out

        # Verify stopped container shown
        assert "UNIT: stopped-unit" in output
        assert "Stopped" in output or "exited" in output.lower()

    def test_unit_with_compose_file(self, backup_unit_factory, tmp_path, capsys):
        """Unit with compose file shows file path."""
        from pathlib import Path

        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        unit = backup_unit_factory()
        unit.compose_files = [Path("/opt/mystack/docker-compose.yml")]

        report.generate([unit])

        captured = capsys.readouterr()
        output = captured.out

        # Verify compose file shown
        assert "Compose File:" in output
        assert "/opt/mystack/docker-compose.yml" in output

    def test_multiple_units_different_types(self, tmp_path, capsys):
        """Multiple units with different types shown correctly."""
        config = make_mock_config(tmp_path)
        report = DryRunReport(config)
        report.utils = make_mock_utils()

        stack = BackupUnit(
            name="mystack",
            type="stack",
            containers=[ContainerInfo(id="c1", name="web", image="nginx", status="running")],
            volumes=[],
            compose_files=[],
        )

        standalone = BackupUnit(
            name="standalone",
            type="standalone",
            containers=[ContainerInfo(id="c2", name="redis", image="redis", status="running")],
            volumes=[],
            compose_files=[],
        )

        report.generate([stack, standalone])

        captured = capsys.readouterr()
        output = captured.out

        # Verify units summary shows both types
        assert "Stacks: 1" in output
        assert "Standalone Containers: 1" in output
