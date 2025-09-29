"""
Backup management module for Kopi-Docka.

This module handles the actual backup operations, including stopping containers,
backing up volumes and databases, and restarting containers.
"""

import json
import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .types import BackupUnit, ContainerInfo, VolumeInfo, BackupMetadata
from .config import Config
from .repository import KopiaRepository
from .backup_db import DatabaseBackupManager
from .constants import (
    CONTAINER_STOP_TIMEOUT,
    CONTAINER_START_TIMEOUT,
    RECIPE_BACKUP_DIR,
    VOLUME_BACKUP_DIR,
    DATABASE_BACKUP_DIR
)


logger = logging.getLogger(__name__)


class BackupManager:
    """
    Manages backup operations for Docker backup units.
    
    This class orchestrates the backup process, including stopping containers,
    backing up data, and restarting containers.
    """
    
    def __init__(self, config: Config):
        """
        Initialize backup manager.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.repo = KopiaRepository(config)
        self.db_manager = DatabaseBackupManager()
        self.max_workers = config.parallel_workers
    
    def backup_unit(self, unit: BackupUnit, update_recovery_bundle: bool = None) -> BackupMetadata:
        """
        Perform complete backup of a backup unit.
        
        This implements the sequential "Cold Backup" strategy:
        1. Stop containers
        2. Backup recipes (compose files, inspect data)
        3. Backup volumes
        4. Backup databases
        5. Start containers
        6. Optionally update disaster recovery bundle
        
        Args:
            unit: Backup unit to backup
            update_recovery_bundle: Update recovery bundle after backup
                                  (None = use config, True/False = override)
            
        Returns:
            Backup metadata with results
        """
        logger.info(f"Starting backup of unit: {unit.name}")
        start_time = time.time()
        metadata = BackupMetadata(
            unit_name=unit.name,
            timestamp=datetime.now(),
            duration_seconds=0
        )
        
        try:
            # Step 1: Stop containers
            logger.info(f"Stopping {len(unit.containers)} containers...")
            self._stop_containers(unit.containers)
            
            # Step 2: Backup recipes
            logger.info("Backing up recipes...")
            recipe_snapshot = self._backup_recipes(unit)
            if recipe_snapshot:
                metadata.kopia_snapshot_ids.append(recipe_snapshot)
            
            # Step 3 & 4: Backup volumes and databases in parallel
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                
                # Submit volume backup tasks
                for volume in unit.volumes:
                    future = executor.submit(self._backup_volume, volume, unit)
                    futures.append(('volume', volume.name, future))
                
                # Submit database backup tasks
                for container in unit.get_database_containers():
                    future = executor.submit(self._backup_database, container, unit)
                    futures.append(('database', container.name, future))
                
                # Wait for all backups to complete
                for backup_type, name, future in futures:
                    try:
                        snapshot_id = future.result(timeout=3600)
                        if snapshot_id:
                            metadata.kopia_snapshot_ids.append(snapshot_id)
                            if backup_type == 'volume':
                                metadata.volumes_backed_up += 1
                            else:
                                metadata.databases_backed_up += 1
                            logger.info(f"Backed up {backup_type}: {name}")
                    except Exception as e:
                        logger.error(f"Failed to backup {backup_type} {name}: {e}")
                        metadata.success = False
                        metadata.error_message = str(e)
            
            # Step 5: Start containers
            logger.info(f"Starting {len(unit.containers)} containers...")
            self._start_containers(unit.containers)
            
        except Exception as e:
            logger.error(f"Backup failed for unit {unit.name}: {e}")
            metadata.success = False
            metadata.error_message = str(e)
            
            # Try to restart containers even if backup failed
            try:
                self._start_containers(unit.containers)
            except Exception as restart_error:
                logger.error(f"Failed to restart containers: {restart_error}")
        
        finally:
            metadata.duration_seconds = time.time() - start_time
            logger.info(f"Backup of {unit.name} completed in {metadata.duration_seconds:.2f}s")
            
            # Save metadata
            self._save_metadata(metadata)
        
        # Step 6: Update recovery bundle if configured
        if update_recovery_bundle is None:
            update_recovery_bundle = self.config.getboolean('backup', 'update_recovery_bundle', fallback=False)
        
        if update_recovery_bundle and metadata.success:
            self._update_recovery_bundle()
        
        return metadata
    
    def _update_recovery_bundle(self):
        """Update disaster recovery bundle after successful backup."""
        try:
            logger.info("Updating disaster recovery bundle...")
            
            from .disaster_recovery import DisasterRecoveryManager
            from pathlib import Path
            
            # Get recovery bundle location from config
            recovery_path = self.config.get('backup', 'recovery_bundle_path')
            if not recovery_path:
                recovery_path = '/backup/recovery'
            
            recovery_path = Path(recovery_path)
            recovery_path.mkdir(parents=True, exist_ok=True)
            
            # Create new bundle
            dr_manager = DisasterRecoveryManager(self.config)
            bundle_path = dr_manager.create_recovery_bundle(recovery_path)
            
            # Keep only the latest N bundles (rotation)
            max_bundles = self.config.getint('backup', 'recovery_bundle_retention', fallback=3)
            self._rotate_recovery_bundles(recovery_path, max_bundles)
            
            logger.info(f"Recovery bundle updated: {bundle_path}")
            
        except Exception as e:
            # Don't fail the backup if recovery bundle fails
            logger.error(f"Failed to update recovery bundle: {e}")
    
    def _rotate_recovery_bundles(self, recovery_path: Path, max_bundles: int):
        """
        Rotate recovery bundles, keeping only the latest N.
        
        Args:
            recovery_path: Path where bundles are stored
            max_bundles: Maximum number of bundles to keep
        """
        try:
            # Find all recovery bundles
            bundles = sorted(recovery_path.glob('kopi-docka-recovery-*.tar.gz.enc'))
            
            if len(bundles) > max_bundles:
                # Remove oldest bundles
                for bundle in bundles[:-max_bundles]:
                    logger.info(f"Removing old recovery bundle: {bundle}")
                    bundle.unlink()
                    
                    # Also remove companion files
                    for suffix in ['.README', '.PASSWORD']:
                        companion = Path(str(bundle) + suffix)
                        if companion.exists():
                            companion.unlink()
                            
        except Exception as e:
            logger.error(f"Failed to rotate recovery bundles: {e}")
    
    def _stop_containers(self, containers: List[ContainerInfo]):
        """
        Stop Docker containers.
        
        Args:
            containers: List of containers to stop
        """
        for container in containers:
            if not container.is_running:
                logger.debug(f"Container {container.name} already stopped")
                continue
            
            try:
                subprocess.run(
                    ['docker', 'stop', '-t', str(CONTAINER_STOP_TIMEOUT), container.id],
                    check=True,
                    capture_output=True
                )
                logger.debug(f"Stopped container: {container.name}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to stop container {container.name}: {e}")
                raise
    
    def _start_containers(self, containers: List[ContainerInfo]):
        """
        Start Docker containers.
        
        Args:
            containers: List of containers to start
        """
        for container in containers:
            try:
                subprocess.run(
                    ['docker', 'start', container.id],
                    check=True,
                    capture_output=True
                )
                logger.debug(f"Started container: {container.name}")
                
                # Wait a moment for container to initialize
                time.sleep(2)
                
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to start container {container.name}: {e}")
                # Continue with other containers even if one fails
    
    def _backup_recipes(self, unit: BackupUnit) -> Optional[str]:
        """
        Backup recipes (compose files and container inspect data).
        
        Args:
            unit: Backup unit
            
        Returns:
            Kopia snapshot ID or None
        """
        backup_path = self.config.backup_base_path / RECIPE_BACKUP_DIR / unit.name
        backup_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # Backup docker-compose file if it exists
            if unit.compose_file and unit.compose_file.exists():
                compose_backup = backup_path / 'docker-compose.yml'
                with open(unit.compose_file, 'r') as src:
                    content = src.read()
                with open(compose_backup, 'w') as dst:
                    dst.write(content)
                logger.debug(f"Backed up compose file: {unit.compose_file}")
            
            # Backup container inspect data
            for container in unit.containers:
                inspect_file = backup_path / f"{container.name}_inspect.json"
                with open(inspect_file, 'w') as f:
                    json.dump(container.inspect_data, f, indent=2)
                logger.debug(f"Backed up inspect data for: {container.name}")
            
            # Create Kopia snapshot
            snapshot_id = self.repo.create_snapshot(
                str(backup_path),
                tags={
                    'type': 'recipe',
                    'unit': unit.name,
                    'timestamp': datetime.now().isoformat()
                }
            )
            
            return snapshot_id
            
        except Exception as e:
            logger.error(f"Failed to backup recipes for {unit.name}: {e}")
            return None
    
    def _backup_volume(self, volume: VolumeInfo, unit: BackupUnit) -> Optional[str]:
        """
        Backup a Docker volume.
        
        Args:
            volume: Volume to backup
            unit: Backup unit this volume belongs to
            
        Returns:
            Kopia snapshot ID or None
        """
        try:
            logger.debug(f"Backing up volume: {volume.name}")
            
            # Create tar of volume and pipe to Kopia
            tar_cmd = [
                'tar', '-czf', '-',
                '-C', volume.mountpoint,
                '.'
            ]
            
            tar_process = subprocess.Popen(
                tar_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            snapshot_id = self.repo.create_snapshot_from_stdin(
                tar_process.stdout,
                path=f"{VOLUME_BACKUP_DIR}/{unit.name}/{volume.name}",
                tags={
                    'type': 'volume',
                    'unit': unit.name,
                    'volume': volume.name,
                    'timestamp': datetime.now().isoformat()
                }
            )
            
            tar_process.wait()
            if tar_process.returncode != 0:
                stderr = tar_process.stderr.read().decode()
                logger.error(f"Tar failed for volume {volume.name}: {stderr}")
                return None
            
            return snapshot_id
            
        except Exception as e:
            logger.error(f"Failed to backup volume {volume.name}: {e}")
            return None
    
    def _backup_database(self, container: ContainerInfo, unit: BackupUnit) -> Optional[str]:
        """
        Backup a database container.
        
        Args:
            container: Database container
            unit: Backup unit this container belongs to
            
        Returns:
            Kopia snapshot ID or None
        """
        if not container.database_type or not self.config.getboolean('backup', 'database_backup'):
            return None
        
        try:
            logger.debug(f"Backing up database: {container.name} ({container.database_type})")
            
            # Use the new DatabaseBackupManager
            dump_process, metadata = self.db_manager.backup_database(container)
            
            if not dump_process:
                logger.warning(f"Could not create backup for database {container.name}")
                return None
            
            # Create snapshot from dump output with metadata
            snapshot_id = self.repo.create_snapshot_from_stdin(
                dump_process.stdout,
                path=f"{DATABASE_BACKUP_DIR}/{unit.name}/{container.name}",
                tags={
                    'type': 'database',
                    'database_type': container.database_type,
                    'unit': unit.name,
                    'container': container.name,
                    'timestamp': datetime.now().isoformat(),
                    'metadata': metadata if metadata else ''
                }
            )
            
            # Wait for dump process to complete
            dump_process.wait()
            if dump_process.returncode != 0:
                stderr = dump_process.stderr.read().decode()
                logger.error(f"Database dump failed for {container.name}: {stderr}")
                return None
            
            return snapshot_id
            
        except Exception as e:
            logger.error(f"Failed to backup database {container.name}: {e}")
            return None
    
    def _save_metadata(self, metadata: BackupMetadata):
        """
        Save backup metadata.
        
        Args:
            metadata: Backup metadata to save
        """
        metadata_dir = self.config.backup_base_path / 'metadata'
        metadata_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{metadata.unit_name}_{metadata.timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        metadata_file = metadata_dir / filename
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata.to_dict(), f, indent=2)
        
        logger.debug(f"Saved metadata to {metadata_file}")