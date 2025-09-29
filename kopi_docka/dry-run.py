"""
Dry run simulation module for Kopi-Docka.

This module provides functionality to simulate backup operations without
actually performing them, allowing users to preview what will happen.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from .types import BackupUnit
from .config import Config
from .system_utils import SystemUtils


logger = logging.getLogger(__name__)


class DryRunReport:
    """
    Generates dry run reports for backup operations.
    
    This class simulates backup operations and provides detailed reports
    about what would happen during an actual backup.
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
        print(f"Repository Path: {self.config.kopia_repository_path}")
        
        # Check disk space
        repo_space = self.utils.get_available_disk_space(
            str(self.config.kopia_repository_path.parent)
        )
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
        
        stacks = [u for u in units if u.type == 'stack']
        standalone = [u for u in units if u.type == 'standalone']
        
        print(f"  - Stacks: {len(stacks)}")
        print(f"  - Standalone Containers: {len(standalone)}")
        
        total_containers = sum(len(u.containers) for u in units)
        total_volumes = sum(len(u.volumes) for u in units)
        
        print(f"Total Containers: {total_containers}")
        print(f"Total Volumes: {total_volumes}")
        
        # Database containers
        db_containers = sum(len(u.get_database_containers()) for u in units)
        if db_containers > 0:
            print(f"Database Containers: {db_containers}")
    
    def _analyze_unit(self, unit: BackupUnit):
        """
        Analyze a single backup unit.
        
        Args:
            unit: Backup unit to analyze
        """
        print(f"\n### UNIT: {unit.name} ###")
        print(f"Type: {unit.type}")
        print(f"Containers: {len(unit.containers)}")
        
        # List containers
        for container in unit.containers:
            status = "Running" if container.is_running else "Stopped"
            db_info = f" [DB: {container.database_type}]" if container.is_database else ""
            print(f"  - {container.name} ({container.image}) - {status}{db_info}")
        
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
        
        # Estimated operations
        print("Operations:")
        print(f"  1. Stop {len(unit.running_containers)} containers")
        print(f"  2. Backup recipes (compose + inspect data)")
        print(f"  3. Backup {len(unit.volumes)} volumes")
        
        db_containers = unit.get_database_containers()
        if db_containers:
            print(f"  4. Backup {len(db_containers)} databases")
        
        print(f"  5. Start {len(unit.running_containers)} containers")
    
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
        estimated_time_per_unit = timedelta(minutes=5)  # Base time
        
        for unit in units:
            # Add time based on volume size
            volume_gb = unit.total_volume_size / (1024**3)
            volume_time = timedelta(minutes=volume_gb * 2)  # 2 min per GB
            
            # Add time for databases
            db_time = timedelta(minutes=len(unit.get_database_containers()) * 3)
            
            estimated_time_per_unit += volume_time + db_time
        
        total_time = estimated_time_per_unit.total_seconds() / len(units) if units else 0
        
        print(f"Estimated Total Time: {self.utils.format_duration(total_time * len(units))}")
        print(f"Estimated Downtime per Unit: ~30-60 seconds")
        
        # Disk space requirements
        compression_ratio = 0.5  # Assume 50% compression
        required_space = total_size * compression_ratio
        
        if required_space > 0:
            print(f"Estimated Repository Space Required: "
                  f"{self.utils.format_bytes(int(required_space))}")
        
        # Check if enough space
        available_space = self.utils.get_available_disk_space(
            str(self.config.kopia_repository_path.parent)
        )
        
        if required_space > 0 and available_space * (1024**3) < required_space:
            print("⚠️  WARNING: Insufficient disk space for backup!")
    
    def _print_config_review(self):
        """Print configuration review."""
        print("\n### CONFIGURATION REVIEW ###")
        
        config_items = [
            ("Repository Path", self.config.kopia_repository_path),
            ("Backup Base Path", self.config.backup_base_path),
            ("Parallel Workers", self.config.parallel_workers),
            ("Stop Timeout", f"{self.config.get('backup', 'stop_timeout')}s"),
            ("Start Timeout", f"{self.config.get('backup', 'start_timeout')}s"),
            ("Compression", self.config.get('kopia', 'compression')),
            ("Encryption", self.config.get('kopia', 'encryption')),
            ("Database Backup", self.config.getboolean('backup', 'database_backup')),
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
            update_recovery_bundle = self.config.getboolean('backup', 'update_recovery_bundle', fallback=False)
        
        if update_recovery_bundle:
            print("Recovery Bundle: WILL BE UPDATED")
            
            # Show bundle settings
            bundle_path = self.config.get('backup', 'recovery_bundle_path', fallback='/backup/recovery')
            retention = self.config.getint('backup', 'recovery_bundle_retention', fallback=3)
            
            print(f"  Location: {bundle_path}")
            print(f"  Retention: Keep last {retention} bundles")
            
            # Check existing bundles
            from pathlib import Path
            bundle_dir = Path(bundle_path)
            if bundle_dir.exists():
                existing_bundles = list(bundle_dir.glob('kopi-docka-recovery-*.tar.gz.enc'))
                print(f"  Existing Bundles: {len(existing_bundles)}")
                
                if existing_bundles:
                    # Show oldest and newest
                    sorted_bundles = sorted(existing_bundles)
                    oldest = sorted_bundles[0]
                    newest = sorted_bundles[-1]
                    
                    print(f"    Oldest: {oldest.name}")
                    print(f"    Newest: {newest.name}")
                    
                    # Calculate bundle sizes
                    total_size = sum(b.stat().st_size for b in existing_bundles)
                    print(f"    Total Size: {self.utils.format_bytes(total_size)}")
                    
                    # Warn if rotation would happen
                    if len(existing_bundles) >= retention:
                        print(f"  ⚠ Rotation: {len(existing_bundles) - retention + 1} old bundle(s) will be removed")
            else:
                print(f"  ⚠ Bundle directory does not exist: {bundle_dir}")
                print(f"    Will be created during backup")
            
            # Estimate bundle size
            print("\n  Estimated Bundle Contents:")
            print("    - Kopia repository configuration")
            print("    - Encryption passwords (secured)")
            print("    - Cloud storage credentials info")
            print("    - Recovery automation script")
            print("    - Current backup status")
            
            # Check for cloud repository
            repo_path = str(self.config.kopia_repository_path)
            if any(repo_path.startswith(prefix) for prefix in ['s3://', 'b2://', 'azure://', 'gs://']):
                print(f"\n  ✓ Cloud Repository Detected: {repo_path}")
                print("    Recovery bundle will include cloud reconnection info")
        else:
            print("Recovery Bundle: WILL NOT BE UPDATED")
            print("  To enable: --update-recovery or set update_recovery_bundle=true in config")
            
            # Show how to create manually
            print("\n  Manual Creation:")
            print("    kopi-docka disaster-recovery")
            print("    kopi-docka disaster-recovery --output /safe/location/")
    
    def estimate_backup_duration(self, unit: BackupUnit) -> float:
        """
        Estimate backup duration for a unit.
        
        Args:
            unit: Backup unit
            
        Returns:
            Estimated duration in seconds
        """
        base_time = 30  # Base overhead
        
        # Time for stopping/starting containers
        container_time = len(unit.containers) * 5
        
        # Time for volumes (estimate based on size)
        volume_time = 0
        for volume in unit.volumes:
            if volume.size_bytes:
                # Estimate 100 MB/s throughput
                volume_time += volume.size_bytes / (100 * 1024 * 1024)
        
        # Time for databases
        db_time = len(unit.get_database_containers()) * 60
        
        return base_time + container_time + volume_time + db_time