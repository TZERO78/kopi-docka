################################################################################
# KOPI-DOCKA
#
# @file:        dry_run_manager.py
# @module:      kopi_docka.cores
# @description: Simulates cold backup sequences without touching running containers.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Reports planned stop/start order and estimated timing per unit
# - Respects recovery bundle update flag to mirror real execution
# - Helps operators validate scope before running actual backups
################################################################################

"""
Dry run simulation module for Kopi-Docka.

This module simulates *cold* backup operations (containers stopped,
recipes + volumes snapshotted, containers started) without actually
performing them, so users can preview what will happen.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from ..types import BackupUnit
from ..helpers.config import Config, extract_filesystem_path
from ..helpers.system_utils import SystemUtils

logger = logging.getLogger(__name__)


class DryRunReport:
    """
    Generates dry run reports for backup operations (cold backups).
    """

    def __init__(self, config: Config):
        """
        Initialize dry run reporter.

        Args:
            config: Application configuration
        """
        self.config = config
        self.utils = SystemUtils()

    def generate(self, units: List[BackupUnit], update_recovery_bundle: bool = None):
        """
        Generate and display dry run report.

        Args:
            units: List of backup units to analyze
            update_recovery_bundle: Whether recovery bundle would be updated
        """
        print("\n" + "=" * 70)
        print("KOPI-DOCKA DRY RUN REPORT")
        print("=" * 70)

        print(f"\nSimulation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Configuration File: {self.config.config_file}")

        # System information
        self._print_system_info()

        # Backup units summary
        self._print_units_summary(units)

        # Detailed unit analysis
        for unit in units:
            self._analyze_unit(unit)

        # Time and resource estimates
        self._print_estimates(units)

        # Configuration review
        self._print_config_review()

        # Recovery bundle info
        self._print_recovery_bundle_info(update_recovery_bundle)

        print("\n" + "=" * 70)
        print("END OF DRY RUN REPORT")
        print("=" * 70)
        print("\nNo changes were made. Run without --dry-run to perform actual backup.")

    def _print_system_info(self):
        """Print system information."""
        print("\n### SYSTEM INFORMATION ###")
        print(f"Available RAM: {self.utils.get_available_ram():.2f} GB")
        print(f"CPU Cores: {self.utils.get_cpu_count()}")
        print(f"Parallel Workers: {self.config.parallel_workers}")
        print(f"Backup Path: {self.config.backup_base_path}")
        # Show kopia_params
        kopia_params = self.config.get("kopia", "kopia_params", fallback="")
        print(f"Kopia Params: {kopia_params}")

        # Determine a local path to check space against
        repo_parent_path_str: Optional[str] = None

        # Extract filesystem path if available
        repo_path = extract_filesystem_path(kopia_params)
        if repo_path:
            from pathlib import Path

            repo_parent_path_str = str(Path(repo_path).parent)

        # Fallback: Use backup base path disk as proxy for remote repos
        if not repo_parent_path_str:
            repo_parent_path_str = str(self.config.backup_base_path)

        # Check disk space (approximation for remote repos)
        repo_space = self.utils.get_available_disk_space(repo_parent_path_str)
        print(f"Available Disk Space: {repo_space:.2f} GB")

        # Check dependencies
        print("\n### DEPENDENCY CHECK ###")
        checks = [
            ("Docker", self.utils.check_docker()),
            ("Kopia", self.utils.check_kopia()),
            ("Tar", self.utils.check_tar()),
        ]
        for name, available in checks:
            status = "✓ Available" if available else "✗ Missing"
            print(f"{name}: {status}")

        # Docker version
        docker_version = self.utils.get_docker_version()
        if docker_version:
            print(f"Docker Version: {'.'.join(map(str, docker_version))}")

        # Kopia version
        kopia_version = self.utils.get_kopia_version()
        if kopia_version:
            print(f"Kopia Version: {kopia_version}")

    def _print_units_summary(self, units: List[BackupUnit]):
        """
        Print summary of backup units.

        Args:
            units: List of backup units
        """
        print("\n### BACKUP UNITS SUMMARY ###")
        print(f"Total Units: {len(units)}")

        stacks = [u for u in units if u.type == "stack"]
        standalone = [u for u in units if u.type == "standalone"]

        print(f"  - Stacks: {len(stacks)}")
        print(f"  - Standalone Containers: {len(standalone)}")

        total_containers = sum(len(u.containers) for u in units)
        total_volumes = sum(len(u.volumes) for u in units)

        print(f"Total Containers: {total_containers}")
        print(f"Total Volumes: {total_volumes}")

    def _analyze_unit(self, unit: BackupUnit):
        """
        Analyze a single backup unit.

        Args:
            unit: Backup unit to analyze
        """
        print(f"\n### UNIT: {unit.name} ###")
        print(f"Type: {unit.type}")
        print(f"Containers: {len(unit.containers)}")

        # List containers (status only; DB specifics are irrelevant for cold backups)
        for container in unit.containers:
            status = "Running" if container.is_running else "Stopped"
            print(f"  - {container.name} ({container.image}) - {status}")

        # Compose file
        if unit.compose_file:
            print(f"Compose File: {unit.compose_file}")

        # Volumes
        if unit.volumes:
            print(f"Volumes: {len(unit.volumes)}")
            total_size = 0
            for volume in unit.volumes:
                size = volume.size_bytes or 0
                total_size += size
                size_str = self.utils.format_bytes(size) if size > 0 else "Unknown"
                print(f"  - {volume.name}: {size_str}")

            if total_size > 0:
                print(f"Total Volume Size: {self.utils.format_bytes(total_size)}")

        # Estimated operations (cold backup sequence)
        print("Operations:")
        print(f"  1. Stop {len(unit.running_containers)} containers")
        print(f"  2. Backup recipes (compose + inspect data)")
        print(f"  3. Backup {len(unit.volumes)} volumes")
        print(f"  4. Start {len(unit.running_containers)} containers")

    def _print_estimates(self, units: List[BackupUnit]):
        """
        Print time and resource estimates.

        Args:
            units: List of backup units
        """
        print("\n### TIME AND RESOURCE ESTIMATES ###")

        # Calculate total data size
        total_size = 0
        for unit in units:
            total_size += unit.total_volume_size

        if total_size > 0:
            print(f"Estimated Data Size: {self.utils.format_bytes(total_size)}")

        # Time estimates (rough approximations)
        # Base overhead per unit (stop+recipes+start), plus per-GB streaming estimate
        estimated_total = timedelta(0)
        for unit in units:
            base_time = timedelta(seconds=30)  # overhead per unit
            # Assume ~100 MB/s effective throughput per worker (conservative)
            volume_gb = unit.total_volume_size / (1024**3)
            stream_time = timedelta(seconds=max(0.0, volume_gb) * (1024 / 100))  # ~10.24 s per GB
            estimated_total += base_time + stream_time

        print(
            f"Estimated Total Time: {self.utils.format_duration(estimated_total.total_seconds())}"
        )
        print(f"Estimated Downtime per Unit: ~20–60 seconds")

        # Disk space requirements (compression estimate)
        compression_ratio = 0.5  # assume ~50% compression overall
        required_space = int(total_size * compression_ratio)

        if required_space > 0:
            print(f"Estimated Repository Space Required: {self.utils.format_bytes(required_space)}")

        # Check if enough local space (proxy for remote: use backup base path)
        # Get kopia_params
        kopia_params = self.config.get("kopia", "kopia_params", fallback="")

        # Extract filesystem path if available
        repo_parent_path_str = None
        repo_path = extract_filesystem_path(kopia_params)
        if repo_path:
            from pathlib import Path

            repo_parent_path_str = str(Path(repo_path).parent)

        if not repo_parent_path_str:
            repo_parent_path_str = str(self.config.backup_base_path)

        available_space_gb = self.utils.get_available_disk_space(repo_parent_path_str)
        if required_space > 0 and available_space_gb * (1024**3) < required_space:
            print("⚠️  WARNING: Insufficient disk space for estimated backup size!")

    def _print_config_review(self):
        """Print configuration review."""
        print("\n### CONFIGURATION REVIEW ###")

        # Get kopia_params from config
        kopia_params = self.config.get("kopia", "kopia_params", fallback="")

        config_items = [
            ("Kopia Params", kopia_params),
            ("Backup Base Path", self.config.backup_base_path),
            ("Parallel Workers", self.config.parallel_workers),
            ("Stop Timeout", f"{self.config.get('backup', 'stop_timeout')}s"),
            ("Start Timeout", f"{self.config.get('backup', 'start_timeout')}s"),
            ("Compression", self.config.get("kopia", "compression")),
            ("Encryption", self.config.get("kopia", "encryption")),
        ]

        for name, value in config_items:
            print(f"{name}: {value}")

    def _print_recovery_bundle_info(self, update_recovery_bundle: Optional[bool]):
        """
        Print disaster recovery bundle information.

        Args:
            update_recovery_bundle: Whether bundle would be updated
        """
        print("\n### DISASTER RECOVERY ###")

        # Determine if bundle would be updated
        if update_recovery_bundle is None:
            update_recovery_bundle = self.config.getboolean(
                "backup", "update_recovery_bundle", fallback=False
            )

        if update_recovery_bundle:
            print("Recovery Bundle: WILL BE UPDATED")

            # Show bundle settings
            bundle_path = self.config.get(
                "backup", "recovery_bundle_path", fallback="/backup/recovery"
            )
            retention = self.config.getint("backup", "recovery_bundle_retention", fallback=3)

            print(f"  Location: {bundle_path}")
            print(f"  Retention: Keep last {retention} bundles")

            from pathlib import Path

            bundle_dir = Path(bundle_path)
            if bundle_dir.exists():
                existing_bundles = list(bundle_dir.glob("kopi-docka-recovery-*.tar.gz.enc"))
                print(f"  Existing Bundles: {len(existing_bundles)}")

                if existing_bundles:
                    sorted_bundles = sorted(existing_bundles)
                    oldest = sorted_bundles[0]
                    newest = sorted_bundles[-1]

                    print(f"    Oldest: {oldest.name}")
                    print(f"    Newest: {newest.name}")

                    total_size = sum(b.stat().st_size for b in existing_bundles)
                    print(f"    Total Size: {self.utils.format_bytes(total_size)}")

                    if len(existing_bundles) >= retention:
                        will_remove = len(existing_bundles) - retention + 1
                        print(f"  ⚠ Rotation: {will_remove} old bundle(s) will be removed")
            else:
                print(f"  ⚠ Bundle directory does not exist: {bundle_dir}")
                print(f"    Will be created during backup")

            # Estimated bundle contents
            print("\n  Estimated Bundle Contents:")
            print("    - Kopia repository configuration")
            print("    - Encryption password (secured)")
            print("    - Cloud storage connection info (if applicable)")
            print("    - Recovery automation script")
            print("    - Current backup status")

            # Check for cloud repository (non-filesystem)
            kopia_params = self.config.get("kopia", "kopia_params", fallback="")

            # Check if it's a cloud backend (not filesystem)
            is_cloud = any(
                backend in kopia_params
                for backend in ("s3", "b2", "azure", "gcs", "sftp", "rclone")
            )

            if is_cloud:
                print(f"\n  ✓ Cloud Repository Detected")
                print("    Bundle will include reconnection guidance")
        else:
            print("Recovery Bundle: WILL NOT BE UPDATED")
            print("  To enable: --update-recovery or set update_recovery_bundle=true in config")

            print("\n  Manual Creation:")
            print("    kopi-docka disaster-recovery")
            print("    kopi-docka disaster-recovery --output /safe/location/")

    def estimate_backup_duration(self, unit: BackupUnit) -> float:
        """
        Estimate backup duration for a unit (seconds).

        Args:
            unit: Backup unit

        Returns:
            Estimated duration in seconds
        """
        base_time = 30  # Base overhead per unit (stop/recipes/start)
        container_time = len(unit.containers) * 5  # small per-container factor

        # Volume transfer time (assume ~100 MB/s effective throughput)
        volume_time = 0.0
        for volume in unit.volumes:
            if volume.size_bytes:
                volume_time += volume.size_bytes / (100 * 1024 * 1024)

        return base_time + container_time + volume_time
